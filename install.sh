#!/usr/bin/env bash
# install.sh — Install the Window Move & Resize GNOME Shell extension.
#
# Copies the extension into the target user's local GNOME Shell extensions
# directory, compiles its gsettings schema, applies the move/resize keybinding
# defaults, frees GNOME's conflicting <Alt><Super>E toggle-maximized binding,
# and enables the extension. Runs sudo-free as the desktop user, and also works
# through sudo (deriving the target from SUDO_USER) for the clean-install chain.
#
# Functions:
#   run_as_target           - run a command in the target user's session env.
#   append_strv_value       - add a value to a gsettings string-array key.
#   remove_strv_value       - drop a value from a gsettings string-array key.
#   enable_shell_extension  - add the extension uuid to enabled-extensions.
#   main                    - orchestrate the full installation.
#
# Usage:
#   bash install.sh         # sudo-free, run as the desktop user
#   sudo bash install.sh    # also supported (clean-install chain)
set -euo pipefail

EXTENSION_ID="window-move-resize@local"
SCHEMA_ID="org.gnome.shell.extensions.window-move-resize"
WM_SCHEMA="org.gnome.desktop.wm.keybindings"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# GNOME default bindings that collide with this extension's chords and must be
# released so the extension owns them. Format: "key:accelerator".
WM_UNBINDINGS=(
  "toggle-maximized:<Alt><Super>E"
)

# Run a command inside the target user's session environment (HOME, D-Bus,
# display, runtime dir). Executes directly when already that user, otherwise
# re-enters through `sudo -H -u`.
# Arguments: $@ - the command and its arguments to execute.
# Returns: the wrapped command's exit status.
run_as_target() {
  local -a environment=(
    "HOME=$TARGET_HOME"
    "USER=$TARGET_USER"
    "LOGNAME=$TARGET_USER"
    "XDG_RUNTIME_DIR=$RUNTIME_DIR"
    "DBUS_SESSION_BUS_ADDRESS=$USER_BUS"
    "DISPLAY=$DISPLAY_VALUE"
  )

  if [[ "$(id -u)" -eq "$TARGET_UID" ]]; then
    env "${environment[@]}" "$@"
  else
    sudo -H -u "$TARGET_USER" env "${environment[@]}" "$@"
  fi
}

# Add a value to a gsettings string-array key, de-duplicating existing entries.
# Arguments: $1 - schema, $2 - key, $3 - value to ensure present.
# Returns: 0.
append_strv_value() {
  local schema="$1" key="$2" value="$3" current new_value
  current="$(run_as_target gsettings get "$schema" "$key" 2>/dev/null || printf '[]')"
  new_value="$(CURRENT="$current" VALUE="$value" python3 - <<'PY'
import ast, os
raw = os.environ.get("CURRENT", "").strip()
if raw.startswith("@as "):
    raw = raw[4:].strip()
try:
    current = ast.literal_eval(raw) if raw else []
except Exception:
    current = []
if not isinstance(current, list):
    current = []
current = list(dict.fromkeys(str(item) for item in current))
value = os.environ.get("VALUE", "")
if value and value not in current:
    current.append(value)
print("[" + ", ".join(repr(str(item)) for item in current) + "]")
PY
)"
  run_as_target gsettings set "$schema" "$key" "$new_value"
}

# Drop a value from a gsettings string-array key.
# Arguments: $1 - schema, $2 - key, $3 - value to remove.
# Returns: 0.
remove_strv_value() {
  local schema="$1" key="$2" value="$3" current new_value
  current="$(run_as_target gsettings get "$schema" "$key" 2>/dev/null || printf '[]')"
  new_value="$(CURRENT="$current" VALUE="$value" python3 - <<'PY'
import ast, os
raw = os.environ.get("CURRENT", "").strip()
if raw.startswith("@as "):
    raw = raw[4:].strip()
try:
    current = ast.literal_eval(raw) if raw else []
except Exception:
    current = []
if not isinstance(current, list):
    current = []
value = os.environ.get("VALUE", "")
current = [str(item) for item in current if str(item) != value]
print("[" + ", ".join(repr(str(item)) for item in current) + "]")
PY
)"
  run_as_target gsettings set "$schema" "$key" "$new_value"
}

# Add the extension uuid to org.gnome.shell enabled-extensions.
# Arguments: none (uses EXTENSION_ID).
# Returns: 0.
enable_shell_extension() {
  run_as_target gsettings set org.gnome.shell disable-user-extensions false
  append_strv_value org.gnome.shell enabled-extensions "$EXTENSION_ID"
  run_as_target gnome-extensions enable "$EXTENSION_ID" 2>/dev/null || true
}

# Orchestrate the installation: resolve the target user, copy extension files,
# compile the schema, apply binding defaults, free conflicting bindings, and
# enable the extension.
# Arguments: none.
# Returns: 0 on success; 1 on environment errors.
main() {
  TARGET_USER="${SUDO_USER:-${TARGET_USER:-$USER}}"
  if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
    printf 'Set TARGET_USER or run through sudo from the desktop user.\n' >&2
    return 1
  fi

  TARGET_UID="$(id -u "$TARGET_USER")"
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
  RUNTIME_DIR="/run/user/$TARGET_UID"
  USER_BUS="unix:path=$RUNTIME_DIR/bus"
  DISPLAY_VALUE="${DISPLAY:-:0}"
  local target_dir="$TARGET_HOME/.local/share/gnome-shell/extensions/$EXTENSION_ID"

  command -v glib-compile-schemas >/dev/null 2>&1 || {
    printf 'glib-compile-schemas is required (package: libglib2.0-bin).\n' >&2
    return 1
  }

  install -d "$target_dir/schemas"
  install -m 0644 \
    "$SCRIPT_DIR/extension.js" \
    "$SCRIPT_DIR/metadata.json" \
    "$target_dir/"
  install -m 0644 \
    "$SCRIPT_DIR/schemas/org.gnome.shell.extensions.window-move-resize.gschema.xml" \
    "$target_dir/schemas/"
  glib-compile-schemas --strict "$target_dir/schemas"
  if [[ "$(id -u)" -eq 0 ]]; then
    chown -R "$TARGET_USER:$TARGET_USER" "$target_dir"
  fi

  # Apply the extension's own keybinding defaults (Alt+Super+W move,
  # Alt+Super+E resize) from the freshly compiled schema.
  run_as_target gsettings --schemadir "$target_dir/schemas" reset-recursively "$SCHEMA_ID"

  # Free GNOME defaults that would otherwise shadow our chords.
  local entry key value
  for entry in "${WM_UNBINDINGS[@]}"; do
    key="${entry%%:*}"
    value="${entry#*:}"
    remove_strv_value "$WM_SCHEMA" "$key" "$value"
  done

  enable_shell_extension
  printf 'Installed %s (Alt+Super+W move, Alt+Super+E resize).\n' "$EXTENSION_ID"
  printf 'Log out and back in if GNOME Shell has not loaded the extension.\n'
}

main "$@"

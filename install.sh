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

# shellcheck source=lib/bash_logging.sh
source "$SCRIPT_DIR/lib/bash_logging.sh"

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
    install_log_info "run_as_target direct: $*"
    env "${environment[@]}" "$@"
  else
    install_log_info "run_as_target sudo as $TARGET_USER: $*"
    sudo -H -u "$TARGET_USER" env "${environment[@]}" "$@"
  fi
}

# Add a value to a gsettings string-array key, de-duplicating existing entries.
# Arguments: $1 - schema, $2 - key, $3 - value to ensure present.
# Returns: 0.
append_strv_value() {
  local schema="$1" key="$2" value="$3" current new_value
  install_log_info "ensuring gsettings value '$value' is present at $schema $key"
  current="$(run_as_target gsettings get "$schema" "$key" 2>/dev/null || printf '[]')"
  new_value="$(CURRENT="$current" python3 "$SCRIPT_DIR/lib/gsettings_strv.py" append "$value")"
  run_as_target gsettings set "$schema" "$key" "$new_value"
}

# Drop a value from a gsettings string-array key.
# Arguments: $1 - schema, $2 - key, $3 - value to remove.
# Returns: 0.
remove_strv_value() {
  local schema="$1" key="$2" value="$3" current new_value
  install_log_info "ensuring gsettings value '$value' is absent at $schema $key"
  current="$(run_as_target gsettings get "$schema" "$key" 2>/dev/null || printf '[]')"
  new_value="$(CURRENT="$current" python3 "$SCRIPT_DIR/lib/gsettings_strv.py" remove "$value")"
  run_as_target gsettings set "$schema" "$key" "$new_value"
}

# Add the extension uuid to org.gnome.shell enabled-extensions.
# Arguments: none (uses EXTENSION_ID).
# Returns: 0.
enable_shell_extension() {
  install_log_info "enabling extension $EXTENSION_ID"
  run_as_target gsettings set org.gnome.shell disable-user-extensions false
  append_strv_value org.gnome.shell enabled-extensions "$EXTENSION_ID"
  if ! run_as_target gnome-extensions enable "$EXTENSION_ID" 2>/dev/null; then
    install_log_warn "gnome-extensions enable failed or extension is not visible yet: $EXTENSION_ID"
  fi
}

# Orchestrate the installation: resolve the target user, copy extension files,
# compile the schema, apply binding defaults, free conflicting bindings, and
# enable the extension.
# Arguments: none.
# Returns: 0 on success; 1 on environment errors.
main() {
  TARGET_USER="${SUDO_USER:-${TARGET_USER:-$USER}}"
  install_log_info "starting install for target user '$TARGET_USER'"
  if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
    install_log_error "target user is missing or root; refusing user-level install"
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
    install_log_error "glib-compile-schemas command is missing"
    printf 'glib-compile-schemas is required (package: libglib2.0-bin).\n' >&2
    return 1
  }

  install_log_info "installing extension files to $target_dir"
  install -d "$target_dir/schemas"
  install -m 0644 \
    "$SCRIPT_DIR/extension.js" \
    "$SCRIPT_DIR/windowUtils.js" \
    "$SCRIPT_DIR/logger.js" \
    "$SCRIPT_DIR/metadata.json" \
    "$target_dir/"
  install -m 0644 \
    "$SCRIPT_DIR/schemas/org.gnome.shell.extensions.window-move-resize.gschema.xml" \
    "$target_dir/schemas/"
  glib-compile-schemas --strict "$target_dir/schemas"
  if [[ "$(id -u)" -eq 0 ]]; then
    install_log_info "fixing ownership of $target_dir for $TARGET_USER"
    chown -R "$TARGET_USER:$TARGET_USER" "$target_dir"
  fi

  # Apply the extension's own keybinding defaults (Alt+Super+W move,
  # Alt+Super+E resize) from the freshly compiled schema.
  install_log_info "resetting extension gsettings schema $SCHEMA_ID"
  run_as_target gsettings --schemadir "$target_dir/schemas" reset-recursively "$SCHEMA_ID"

  # Free GNOME defaults that would otherwise shadow our chords.
  local entry key value
  for entry in "${WM_UNBINDINGS[@]}"; do
    key="${entry%%:*}"
    value="${entry#*:}"
    remove_strv_value "$WM_SCHEMA" "$key" "$value"
  done

  enable_shell_extension
  install_log_info "installed $EXTENSION_ID successfully"
  printf 'Installed %s (Alt+Super+W move, Alt+Super+E resize).\n' "$EXTENSION_ID"
  printf 'Log out and back in if GNOME Shell has not loaded the extension.\n'
}

main "$@"

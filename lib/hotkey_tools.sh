#!/usr/bin/env bash
# hotkey_tools.sh - install library for the window move/resize extension.
#
# Sourced by install.sh after the shared component framework + install helpers
# are loaded (it relies on run_as_target/msg from installer_helpers.sh and the
# install_log_* helpers from lib/bash_logging.sh). Defines the always-installed
# extension core plus one configure_* function per selectable hotkey component.
#
# The extension itself is the core: it installs and is enabled no matter which
# hotkeys the user selects, so the program works on its own. Each hotkey is an
# optional, fully customizable module — the user picks the accelerator (friendly
# "control+t" / "alt+super+w" syntax) and only the GNOME defaults that collide
# with the chosen accelerator are released.
#
# Functions:
#   hotkey_tools_set_strv_value    - set an extension schema key to one accelerator.
#   remove_strv_value              - drop a value from a gsettings string-array key.
#   install_extension_core         - copy/compile/enable the extension (always).
#   resolve_hotkey_spec            - choose a friendly hotkey spec (env/prompt/default).
#   release_conflicting_bindings   - free GNOME defaults that shadow an accelerator.
#   apply_hotkey                   - resolve, convert, set, and de-conflict one hotkey.
#   configure_move_hotkey          - install the pointer move hotkey component.
#   configure_resize_hotkey        - install the pointer resize hotkey component.
#   install_open_kitty_sort_script - deploy the open-kitty-and-sort helper script.
#   configure_open_kitty_sort_hotkey - bind the launch-kitty-and-sort custom keybinding.
#   detect_open_kitty_sort_hotkey  - report whether the custom keybinding is registered.
#   uninstall_open_kitty_sort_hotkey - remove the custom keybinding and helper script.

EXTENSION_ID="window-move-resize@local"
SCHEMA_ID="org.gnome.shell.extensions.window-move-resize"
GSCHEMA_FILE="org.gnome.shell.extensions.window-move-resize.gschema.xml"

# Directory holding this library and the Python helpers it shells out to.
HOTKEY_TOOLS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Populated by install_extension_core: the installed extension directory and the
# compiled schema directory the configure_* functions point gsettings at.
EXTENSION_TARGET_DIR=""
EXTENSION_SCHEMA_DIR=""

# GNOME schemas scanned for accelerators that would shadow a user-selected
# hotkey. The extension's own schema is intentionally excluded so we never strip
# the binding we are setting.
GNOME_KEYBINDING_SCHEMAS=(
  "org.gnome.desktop.wm.keybindings"
  "org.gnome.shell.keybindings"
  "org.gnome.mutter.keybindings"
  "org.gnome.mutter.wayland.keybindings"
  "org.gnome.settings-daemon.plugins.media-keys"
)

# GNOME custom-keybinding owned by the open-kitty-and-sort component. Unlike
# the hold-to-act pointer gestures, this is a one-shot "launch kitty then sort"
# command: it is bound as a stock GNOME custom keybinding (a relocatable
# media-keys schema instance) that runs the helper script, NOT as a key on this
# extension's schema. The component (re)registers it when selected; the
# component's uninstall_* function removes it (see hwt_clear_custom_keybinding).
MEDIAKEYS_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
MEDIAKEYS_CUSTOM_KEY="custom-keybindings"
CUSTOM_KEYBINDING_REL_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
OPEN_KITTY_SORT_CUSTOM_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/open-kitty-sort/"
OPEN_KITTY_SORT_CUSTOM_NAME="Open kitty and sort windows"
OPEN_KITTY_SORT_SCRIPT_NAME="open-kitty-and-sort.sh"
# Runtime helper source (repo root /scripts); installed to ~/.local/bin/ by
# install_open_kitty_sort_script. Resolved lazily so the path is correct whether
# the library is sourced from a checkout or a copied tree.
OPEN_KITTY_SORT_SCRIPT_SRC="$HOTKEY_TOOLS_LIB_DIR/../scripts/$OPEN_KITTY_SORT_SCRIPT_NAME"
# Populated by install_open_kitty_sort_script: the deployed helper path the
# custom keybinding's command points at.
OPEN_KITTY_SORT_SCRIPT_TARGET=""

# Set one extension schema key to a single-element accelerator array, using the
# freshly compiled schema directory so the key resolves before GNOME reloads.
# Arguments: $1 - key name; $2 - GTK accelerator (e.g. "<Alt><Super>w").
# Returns: 0.
hotkey_tools_set_strv_value() {
  local key="$1" accel="$2"
  install_log_info "setting $SCHEMA_ID $key to '$accel'"
  run_as_target gsettings --schemadir "$EXTENSION_SCHEMA_DIR" \
    set "$SCHEMA_ID" "$key" "['${accel//\'/\\\'}']"
}

# Drop a value from a gsettings string-array key, keeping re-runs idempotent.
# Arguments: $1 - schema; $2 - key; $3 - value to remove.
# Returns: 0.
remove_strv_value() {
  local schema="$1" key="$2" value="$3" current new_value
  install_log_info "ensuring gsettings value '$value' is absent at $schema $key"
  current="$(run_as_target gsettings get "$schema" "$key" 2>/dev/null || printf '[]')"
  new_value="$(CURRENT="$current" hwt_bin gsettings-strv remove "$value")"
  run_as_target gsettings set "$schema" "$key" "$new_value"
}

# Add a value to a gsettings string-array key, de-duplicating existing entries.
# Arguments: $1 - schema; $2 - key; $3 - value to ensure present.
# Returns: 0.
append_strv_value() {
  local schema="$1" key="$2" value="$3" current new_value
  install_log_info "ensuring gsettings value '$value' is present at $schema $key"
  current="$(run_as_target gsettings get "$schema" "$key" 2>/dev/null || printf '[]')"
  new_value="$(CURRENT="$current" hwt_bin gsettings-strv append "$value")"
  run_as_target gsettings set "$schema" "$key" "$new_value"
}

# Install the extension files, compile its schema, and enable it. This is the
# always-run core: it does not depend on any selected hotkey component, so the
# extension is present and active even when the user deselects every hotkey.
# Arguments: none. Returns: 0 on success; 1 when glib-compile-schemas is absent.
install_extension_core() {
  local source_dir
  source_dir="$(cd "$HOTKEY_TOOLS_LIB_DIR/.." && pwd)"
  EXTENSION_TARGET_DIR="$TARGET_HOME/.local/share/gnome-shell/extensions/$EXTENSION_ID"
  EXTENSION_SCHEMA_DIR="$EXTENSION_TARGET_DIR/schemas"

  if ! need_cmd glib-compile-schemas; then
    install_log_error "glib-compile-schemas command is missing"
    msg "glib-compile-schemas is required (package: libglib2.0-bin)."
    return 1
  fi

  install_log_info "installing extension files to $EXTENSION_TARGET_DIR"
  msg "Installing $EXTENSION_ID extension core"
  install -d "$EXTENSION_SCHEMA_DIR"
  install -m 0644 \
    "$source_dir/extension.js" \
    "$source_dir/windowUtils.js" \
    "$source_dir/logger.js" \
    "$source_dir/metadata.json" \
    "$EXTENSION_TARGET_DIR/"
  install -m 0644 "$source_dir/schemas/$GSCHEMA_FILE" "$EXTENSION_SCHEMA_DIR/"
  glib-compile-schemas --strict "$EXTENSION_SCHEMA_DIR"
  if is_root; then
    install_log_info "fixing ownership of $EXTENSION_TARGET_DIR for $TARGET_USER"
    chown -R "$TARGET_USER:$TARGET_USER" "$EXTENSION_TARGET_DIR"
  fi

  install_log_info "enabling extension $EXTENSION_ID"
  run_as_target gsettings set org.gnome.shell disable-user-extensions false
  append_strv_value org.gnome.shell enabled-extensions "$EXTENSION_ID"
  # Best-effort in-place enable, dispatched in the BACKGROUND so it can never
  # block the installer. `gnome-extensions enable` is a synchronous D-Bus call
  # into GNOME Shell that can hang for minutes on a fresh install or an
  # unresponsive session. The extension is already persisted in
  # enabled-extensions above (a live Shell auto-loads it; otherwise it activates
  # on next login), so fire the live enable detached and time-boxed, with stdio
  # redirected so it never holds the installer's pipe open.
  install_log_info "dispatching background in-place enable for $EXTENSION_ID (applies live if the Shell is responsive, otherwise on next login)"
  run_as_target sh -c 'timeout 5 gnome-extensions enable "$1" >/dev/null 2>&1 </dev/null &' _ "$EXTENSION_ID" || true
  install_log_info "extension core installed"
}

# hwt_clear_custom_keybinding - remove a GNOME custom keybinding registration.
# Called from the component's uninstall_* function only: install runs must never
# clear bindings of components they were not asked to touch. Drops the path from
# the media-keys custom-keybindings list and resets the relocatable
# name/command/binding keys. Best-effort: ignores failures when nothing is set.
# Arguments: $1 - custom-keybinding settings path. Returns: 0.
hwt_clear_custom_keybinding() {
  local path="$1"
  install_log_info "clearing custom keybinding at $path"
  remove_strv_value "$MEDIAKEYS_SCHEMA" "$MEDIAKEYS_CUSTOM_KEY" "$path" 2>/dev/null || true
  run_as_target gsettings reset "$CUSTOM_KEYBINDING_REL_SCHEMA:$path" name 2>/dev/null || true
  run_as_target gsettings reset "$CUSTOM_KEYBINDING_REL_SCHEMA:$path" command 2>/dev/null || true
  run_as_target gsettings reset "$CUSTOM_KEYBINDING_REL_SCHEMA:$path" binding 2>/dev/null || true
}

# Choose the friendly hotkey spec for a component. An explicit environment
# variable wins (used by the master installer / automated runs); otherwise an
# interactive terminal is prompted, with the documented "control+t" syntax;
# otherwise the built-in default is used so piped/non-interactive runs never
# block. Prints the chosen friendly spec to stdout.
# Arguments: $1 - env var name; $2 - default friendly spec; $3 - human label.
# Returns: 0.
resolve_hotkey_spec() {
  local env_var="$1" default_spec="$2" label="$3" chosen=""

  if [[ -n "${!env_var:-}" ]]; then
    chosen="${!env_var}"
    install_log_info "using $env_var='$chosen' for $label"
  elif [[ -t 0 && -t 1 ]]; then
    printf 'Hotkey for %s.\n' "$label" >&2
    printf '  Syntax: modifier+key joined with "+", e.g. control+t, super+u, alt+super+w.\n' >&2
    printf '  Press Enter to keep the default [%s]: ' "$default_spec" >&2
    IFS= read -r chosen || chosen=""
    chosen="${chosen## }"
    chosen="${chosen%% }"
    [[ -z "$chosen" ]] && chosen="$default_spec"
    install_log_info "interactive hotkey for $label: '$chosen'"
  else
    chosen="$default_spec"
    install_log_info "defaulting $label hotkey to '$chosen' (non-interactive)"
  fi

  printf '%s' "$chosen"
}

# Remove an accelerator from every GNOME default keybinding key that currently
# holds it, so a user-selected hotkey is never shadowed by a stock binding. Only
# the schemas in GNOME_KEYBINDING_SCHEMAS are touched; the extension's own
# schema is never scanned. Conflicts are released solely for accelerators the
# user actually assigns.
# Arguments: $1 - GTK accelerator (e.g. "<Alt><Super>e"). Returns: 0.
release_conflicting_bindings() {
  local accel="$1" schema key stored escaped
  for schema in "${GNOME_KEYBINDING_SCHEMAS[@]}"; do
    # list-recursively rows are "<schema> <key> <value>"; strip the leading
    # "<schema> " so the normalizing conflict finder sees "<key> <value>". It
    # prints "key<TAB>stored" for each genuine collision (order/case aware).
    escaped="${schema//./\\.}"
    while IFS=$'\t' read -r key stored; do
      [[ -z "$key" ]] && continue
      install_log_info "releasing GNOME default $schema $key='$stored' (collides with '$accel')"
      msg "Freeing GNOME default $schema/$key which collides with $accel"
      remove_strv_value "$schema" "$key" "$stored"
    done < <(run_as_target gsettings list-recursively "$schema" 2>/dev/null \
              | sed -E "s/^${escaped} //" \
              | hwt_bin conflicts "$accel" 2>/dev/null)
  done
}

# Resolve, convert, set, and de-conflict a single hotkey component.
# Arguments: $1 - schema key; $2 - env var; $3 - default friendly spec;
#            $4 - human label. Returns: 0 on success; 1 on an invalid spec.
# hwt_conflict_candidates — print "schema key<TAB>accelerator" candidate lines
# for the shared capture UI's real-time conflict warnings, covering the GNOME
# default keybinding schemas this component de-conflicts against.
hwt_conflict_candidates() {
  local schema
  for schema in "${GNOME_KEYBINDING_SCHEMAS[@]}"; do
    run_as_target gsettings list-recursively "$schema" 2>/dev/null
  done | hwt_bin conflict-candidates 2>/dev/null || true
}

apply_hotkey() {
  local key="$1" env_var="$2" default_spec="$3" label="$4" spec accel

  # Prefer the shared interactive press-to-capture engine (returns a GTK
  # accelerator directly, converting friendly env/default specs). Fall back to
  # the friendly text prompt + accelerator.py when the shared helper is absent.
  if declare -F isc_capture_hotkey >/dev/null 2>&1; then
    accel="$(ISC_HOTKEY_CONFLICTS_FN=hwt_conflict_candidates \
      isc_capture_hotkey "$env_var" "$default_spec" "$label")"
    if [[ -z "$accel" ]]; then
      install_log_error "empty hotkey for $label"
      msg "No hotkey captured for $label; not binding this component."
      return 1
    fi
  else
    spec="$(resolve_hotkey_spec "$env_var" "$default_spec" "$label")"
    if ! accel="$(hwt_bin accelerator "$spec" 2>/dev/null)"; then
      install_log_error "invalid hotkey spec '$spec' for $label"
      msg "Invalid hotkey '$spec' for $label; not binding this component."
      return 1
    fi
  fi

  msg "Binding $label to $accel"
  hotkey_tools_set_strv_value "$key" "$accel"
  release_conflicting_bindings "$accel"
}

# configure_move_hotkey - install the pointer-driven window move hotkey.
# Customizable via MOVE_HOTKEY (friendly syntax); defaults to alt+super+w.
# Returns: the apply_hotkey status.
configure_move_hotkey() {
  apply_hotkey "drag-active-window-with-pointer" "MOVE_HOTKEY" \
    "${MOVE_HOTKEY:-alt+super+w}" "move active window with pointer"
}

# configure_resize_hotkey - install the pointer-driven window resize hotkey.
# Customizable via RESIZE_HOTKEY (friendly syntax); defaults to alt+super+e.
# Returns: the apply_hotkey status.
configure_resize_hotkey() {
  apply_hotkey "scale-active-window-from-center" "RESIZE_HOTKEY" \
    "${RESIZE_HOTKEY:-alt+super+e}" "resize active window from center"
}

###############################################################################
# Detection and uninstall (component lifecycle)
###############################################################################
# Each hotkey writes one accelerator key on the bundled extension's GSettings
# schema. A hotkey is "installed" when that schema is present (so the binding
# applies); uninstalling clears the accelerator (empty list) so the pointer
# action no longer has a shortcut. The mandatory extension deploy is core and is
# never removed by a component uninstall.

# hwt_schema_dir: resolve the deployed extension schema dir without relying on
# globals that are only set during the core install pass.
hwt_schema_dir() {
  printf '%s\n' "${TARGET_HOME:-$HOME}/.local/share/gnome-shell/extensions/$EXTENSION_ID/schemas"
}

# hwt_key_set: true when the extension schema key holds a non-empty accelerator.
hwt_key_set() {
  local key="$1" val
  val="$(run_as_target gsettings --schemadir "$(hwt_schema_dir)" \
    get "$SCHEMA_ID" "$key" 2>/dev/null || printf '[]')"
  [[ -n "$val" && "$val" != "[]" && "$val" != "@as []" ]]
}

# hwt_clear_key: clear an extension accelerator key (set to empty list).
hwt_clear_key() {
  run_as_target gsettings --schemadir "$(hwt_schema_dir)" \
    set "$SCHEMA_ID" "$1" "[]" 2>/dev/null || true
}

detect_move_hotkey()   { hwt_key_set "drag-active-window-with-pointer"; }
detect_resize_hotkey() { hwt_key_set "scale-active-window-from-center"; }

uninstall_move_hotkey()   { msg "Clearing move-window hotkey";   hwt_clear_key "drag-active-window-with-pointer"; }
uninstall_resize_hotkey() { msg "Clearing resize-window hotkey"; hwt_clear_key "scale-active-window-from-center"; }

###############################################################################
# Open kitty and sort windows (GNOME custom keybinding component)
###############################################################################
# Unlike the pointer move/resize hotkeys, this is a one-shot command: it opens
# kitty, waits briefly for the new window to map, then triggers the window-sort
# (automatic-window-tiling) hotkey so the terminal is tiled with the other kitty
# windows. It is bound as a stock GNOME custom keybinding that runs the helper
# script scripts/open-kitty-and-sort.sh, NOT as a key on this extension's
# schema, so it needs no GNOME Shell reload. The custom keybinding is
# (re)registered here when the component is selected; detect/uninstall remove
# it on demand.

# install_open_kitty_sort_script - copy the helper script to the target user's
# ~/.local/bin so the custom keybinding's command can run it. Sets
# OPEN_KITTY_SORT_SCRIPT_TARGET to the deployed path. Returns: 0 on success;
# 1 when the source script is missing.
install_open_kitty_sort_script() {
  local target="$TARGET_HOME/.local/bin/$OPEN_KITTY_SORT_SCRIPT_NAME"
  local lib_target="$TARGET_HOME/.local/share/linux_hotkey_window_tools/lib"
  if [[ ! -f "$OPEN_KITTY_SORT_SCRIPT_SRC" ]]; then
    install_log_error "open-kitty-and-sort source missing at $OPEN_KITTY_SORT_SCRIPT_SRC"
    msg "open-kitty-and-sort helper source missing; skipping component."
    return 1
  fi
  install_log_info "installing open-kitty-and-sort helper to $target"
  msg "Installing open-kitty-and-sort helper script"
  install -d "$(dirname "$target")"
  if is_root; then
    install -D -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" "$OPEN_KITTY_SORT_SCRIPT_SRC" "$target"
  else
    install -D -m 0755 "$OPEN_KITTY_SORT_SCRIPT_SRC" "$target"
  fi
  install_log_info "installing automatic-window-tiling shared helpers to $lib_target"
  install -d "$lib_target"
  ensure_hwt_bin || return 1
  if [[ ! -f "$HOTKEY_TOOLS_LIB_DIR/automatic_window_tiling.sh" ]]; then
    install_log_error "shared helper missing at $HOTKEY_TOOLS_LIB_DIR/automatic_window_tiling.sh"
    msg "automatic-window-tiling helper source missing; skipping component."
    return 1
  fi
  if is_root; then
    install -m 0644 -o "$TARGET_USER" -g "$TARGET_USER" \
      "$HOTKEY_TOOLS_LIB_DIR/automatic_window_tiling.sh" "$lib_target/automatic_window_tiling.sh"
    install -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" "$HWT_BIN" "$lib_target/hwt-tools"
  else
    install -m 0644 "$HOTKEY_TOOLS_LIB_DIR/automatic_window_tiling.sh" "$lib_target/automatic_window_tiling.sh"
    install -m 0755 "$HWT_BIN" "$lib_target/hwt-tools"
  fi
  chmod 0755 "$lib_target/automatic_window_tiling.sh" 2>/dev/null || true
  rm -f "$lib_target/automatic_window_tiling.py" "$lib_target/log_utils.py" "$lib_target/gsettings_strv.py"
  OPEN_KITTY_SORT_SCRIPT_TARGET="$target"
}

# configure_open_kitty_sort_hotkey - install the helper script and bind the
# launch-kitty-and-sort GNOME custom keybinding. The accelerator is resolved the
# same way as the pointer hotkeys (shared capture engine or friendly prompt +
# accelerator.py); default is super+less (the "<" key, left of Z on Nordic
# layouts). Only GNOME defaults that collide with the chosen accelerator are
# freed. Customizable via OPEN_KITTY_SORT_HOTKEY (friendly syntax).
# Returns: 0 on success; 1 when the hotkey is empty/invalid or the script is
# missing.
configure_open_kitty_sort_hotkey() {
  install_open_kitty_sort_script || return 1

  local accel spec
  # Prefer the shared interactive press-to-capture engine (returns a GTK
  # accelerator directly, converting friendly env/default specs). Fall back to
  # the friendly text prompt + accelerator.py when the shared helper is absent —
  # the same resolution flow apply_hotkey uses for the pointer hotkeys.
  if declare -F isc_capture_hotkey >/dev/null 2>&1; then
    accel="$(ISC_HOTKEY_CONFLICTS_FN=hwt_conflict_candidates \
      isc_capture_hotkey OPEN_KITTY_SORT_HOTKEY super+less "open kitty and sort windows")"
    if [[ -z "$accel" ]]; then
      install_log_error "empty hotkey for open kitty and sort windows"
      msg "No hotkey captured for open kitty and sort windows; not binding this component."
      return 1
    fi
  else
    spec="$(resolve_hotkey_spec OPEN_KITTY_SORT_HOTKEY super+less "open kitty and sort windows")"
    if ! accel="$(hwt_bin accelerator "$spec" 2>/dev/null)"; then
      install_log_error "invalid hotkey spec '$spec' for open kitty and sort windows"
      msg "Invalid hotkey '$spec' for open kitty and sort windows; not binding this component."
      return 1
    fi
  fi

  msg "Binding open kitty and sort windows to $accel"
  # Register the GNOME custom keybinding: list its path among the active
  # custom-keybindings, then set the relocatable name/command/binding keys. The
  # command points at the freshly installed helper script.
  append_strv_value "$MEDIAKEYS_SCHEMA" "$MEDIAKEYS_CUSTOM_KEY" "$OPEN_KITTY_SORT_CUSTOM_PATH"
  run_as_target gsettings set "$CUSTOM_KEYBINDING_REL_SCHEMA:$OPEN_KITTY_SORT_CUSTOM_PATH" \
    name "'$OPEN_KITTY_SORT_CUSTOM_NAME'"
  run_as_target gsettings set "$CUSTOM_KEYBINDING_REL_SCHEMA:$OPEN_KITTY_SORT_CUSTOM_PATH" \
    command "'$OPEN_KITTY_SORT_SCRIPT_TARGET'"
  run_as_target gsettings set "$CUSTOM_KEYBINDING_REL_SCHEMA:$OPEN_KITTY_SORT_CUSTOM_PATH" \
    binding "'$accel'"
  release_conflicting_bindings "$accel"

  # Informational (non-fatal): the helper script simulates the sort hotkey via
  # xdotool, which is not present on a clean install. Note it so the user knows
  # the auto-sort needs a key simulator while kitty still opens regardless.
  if ! need_cmd xdotool; then
    msg "Note: xdotool not found; open-kitty-and-sort will open kitty but skip the auto-sort until a key simulator is available."
  fi
}

# detect_open_kitty_sort_hotkey - true when the custom keybinding path is listed
# among the active media-keys custom-keybindings.
detect_open_kitty_sort_hotkey() {
  local current
  current="$(run_as_target gsettings get "$MEDIAKEYS_SCHEMA" "$MEDIAKEYS_CUSTOM_KEY" 2>/dev/null || printf '[]')"
  printf '%s' "$current" | grep -Fq "$OPEN_KITTY_SORT_CUSTOM_PATH"
}

# uninstall_open_kitty_sort_hotkey - remove the custom keybinding registration
# (path + relocatable keys) and delete the helper script (best-effort).
uninstall_open_kitty_sort_hotkey() {
  msg "Removing open-kitty-and-sort custom keybinding"
  hwt_clear_custom_keybinding "$OPEN_KITTY_SORT_CUSTOM_PATH"
  rm -f "$TARGET_HOME/.local/bin/$OPEN_KITTY_SORT_SCRIPT_NAME" 2>/dev/null || true
}

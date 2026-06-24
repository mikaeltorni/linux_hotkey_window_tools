#!/usr/bin/env bash
# install.sh — Install the Window Move & Resize GNOME Shell extension.
#
# The extension is the always-installed core: its files and compiled gsettings
# schema are copied into the target user's local GNOME Shell extensions
# directory and the extension is enabled, so the program works no matter which
# hotkeys the user picks. Each hotkey (move, resize) is an optional, default-on,
# fully customizable component routed through the shared component framework. A
# selected hotkey's accelerator is taken from its environment variable
# (MOVE_HOTKEY / RESIZE_HOTKEY), or prompted on a terminal, or defaulted; only
# the GNOME default bindings that collide with a chosen accelerator are freed.
#
# Runs sudo-free as the desktop user, and also through sudo (deriving the target
# from SUDO_USER) for the clean-install chain.
#
# Components:
#   - main(): install the extension core, then apply the selected hotkeys.
#
# Usage:
#   bash install.sh                    # interactive on a TTY, else default-on set
#   bash install.sh --default          # all default-on components, no prompts
#   bash install.sh --all              # every component, no prompts
#   bash install.sh --select a,b       # exactly these component ids
#   bash install.sh --list-components  # id<TAB>label<TAB>default (side-effect free)
#   MOVE_HOTKEY=control+t bash install.sh --default   # customize accelerators
#   sudo bash install.sh               # also supported (clean-install chain)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/bash_logging.sh
source "$SCRIPT_DIR/lib/bash_logging.sh"

# Load the shared component framework + install-time helpers (single source of
# truth in linux_installation_scripts_functions) before the hotkey library,
# which uses run_as_target/msg/need_cmd. No vendored copy: resolve a sibling
# checkout or download on demand so the installer still works standalone.
for __isc_d in "${ISC_FUNCTIONS_DIR:-}" \
               "$SCRIPT_DIR/../linux_installation_scripts_functions" \
               "$HOME/projects/linux_installation_scripts_functions"; do
  [ -n "$__isc_d" ] && [ -f "$__isc_d/component_loader.sh" ] && { source "$__isc_d/component_loader.sh"; break; }
done
if ! declare -F isc_load_helpers >/dev/null 2>&1; then
  __isc_loader_url="https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/${ISC_FUNCTIONS_REF:-master}/component_loader.sh"
  __isc_loader_tmp="$(mktemp)"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$__isc_loader_url" -o "$__isc_loader_tmp"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$__isc_loader_tmp" "$__isc_loader_url"
  else
    printf 'ERROR: curl or wget is required to download the shared installer framework.\n' >&2
    exit 1
  fi
  source "$__isc_loader_tmp"
  rm -f "$__isc_loader_tmp"
fi
isc_load_helpers
isc_activate_components

# shellcheck source=lib/hotkey_tools.sh
source "$SCRIPT_DIR/lib/hotkey_tools.sh"
# shellcheck source=installer/components.sh
source "$SCRIPT_DIR/installer/components.sh"

# Populate the target user's desktop-session environment for run_as_target.
# Component discovery/help is handled before this function runs so those
# side-effect-free modes do not depend on the caller's desktop user.
initialize_target_user() {
  TARGET_USER="${SUDO_USER:-${TARGET_USER:-$USER}}"
  if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
    install_log_error "target user is missing or root; refusing user-level install"
    printf 'Set TARGET_USER or run through sudo from the desktop user.\n' >&2
    return 1
  fi
  TARGET_UID="$(id -u "$TARGET_USER")"
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
  RUNTIME_DIR="/run/user/$TARGET_UID"
  USER_BUS="unix:path=$RUNTIME_DIR/bus"
  DISPLAY_VAL="${DISPLAY:-:0}"
}

# Orchestrate the install: always install the extension core, then route the
# selected hotkey components through the framework.
main() {
  initialize_target_user
  install_log_info "starting install for target user '$TARGET_USER'"
  install_extension_core
  clear_component_hotkeys
  component_main "$@"
  install_log_info "installed $EXTENSION_ID successfully"
  msg "Installed $EXTENSION_ID. Log out and back in if GNOME Shell has not loaded the extension."
}

# Listing/help must print only their own output (the master installer parses
# --list-components) and stay side-effect free: handle them before the core
# install runs.
case "${1:-}" in
  --list-components|--help|-h) component_main "$@"; exit $? ;;
esac

main "$@"

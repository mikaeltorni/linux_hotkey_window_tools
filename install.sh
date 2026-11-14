#!/usr/bin/env bash
# install.sh — Install the Window Move & Resize GNOME Shell extension.
#
# The extension is the always-installed core: its files and compiled gsettings
# schema are copied into the target user's local GNOME Shell extensions
# directory and the extension is enabled, so the program works no matter which
# hotkeys the user picks. Each hotkey is an optional, default-on, fully
# customizable component routed through the shared component framework. The
# pointer move/resize hotkeys are keys on the extension's schema; the
# open-kitty-and-sort hotkey is a GNOME custom keybinding that runs a helper
# script (no Shell reload needed). A selected hotkey's accelerator is taken from
# its environment variable (MOVE_HOTKEY / RESIZE_HOTKEY / OPEN_KITTY_SORT_HOTKEY),
# or prompted on a terminal, or defaulted; only the GNOME default bindings that
# collide with a chosen accelerator are freed.
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

# Load the generated, licensed support package before the hotkey library,
# which uses run_as_target/msg/need_cmd. The framework source of truth is
# linux_installation_scripts_functions; the packaged copy works standalone.
source "$SCRIPT_DIR/.installer-support/bootstrap.sh"
isc_load_helpers
isc_activate_components

# shellcheck source=lib/hwt_bin.sh
source "$SCRIPT_DIR/lib/hwt_bin.sh"
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

# Plan the selection before core installation; removal and cancellation skip the core.
# Parameters: $@ - already parsed installer arguments. Returns: zero on completion.
main() {
  printf 'arguments=%s\n' "$*" >&2
  isc_plan_install
  if [[ "$ISC_PLAN_ACTION" == cancel ]]; then printf '0\n' >&2; return 0; fi
  initialize_target_user
  if [[ "$ISC_PLAN_ACTION" == install ]]; then
    install_log_info "starting install for target user '$TARGET_USER'"
    install_extension_core
  fi
  _isc_apply_plan "$ISC_ARGUMENT_ORIGIN"
  install_log_info "completed component changes for $EXTENSION_ID"
  printf '0\n' >&2
  return 0
}

# Best-effort target-user context for the --detect / --uninstall routing below,
# which bypasses main() (and therefore initialize_target_user()). Without this,
# the detect_*/uninstall_* helpers' run_as_target calls run with an empty
# TARGET_USER and silently report every component as absent (or no-op). This
# never fails and emits no stdout, so --list-components / --help stay
# side-effect free; main() re-derives and validates the same values
# authoritatively inside initialize_target_user().
: "${TARGET_USER:=${SUDO_USER:-$USER}}"
: "${TARGET_HOME:=$(getent passwd "$TARGET_USER" 2>/dev/null | cut -d: -f6)}"
if [[ -z "${TARGET_HOME:-}" ]]; then TARGET_HOME="$HOME"; fi
: "${TARGET_UID:=$(id -u "$TARGET_USER" 2>/dev/null || id -u)}"
: "${RUNTIME_DIR:=/run/user/$TARGET_UID}"
: "${USER_BUS:=unix:path=$RUNTIME_DIR/bus}"
: "${DISPLAY_VAL:=${DISPLAY:-:0}}"

# Listing/help must print only their own output (the master installer parses
# --list-components) and stay side-effect free: handle them before the core
# install runs.
if isc_route_readonly_args "$@"; then exit $?; fi

main "$@"

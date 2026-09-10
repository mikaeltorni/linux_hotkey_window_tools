#!/usr/bin/env bash
# automatic_window_tiling.sh - shared Super+T resolve/trigger for tiling extension.
#
# Sourced by open-kitty-and-sort.sh and deployed beside hwt-tools so shell
# callers share one resolution path.

# Directory holding this library (override before sourcing when copied elsewhere).
AUTOMATIC_WINDOW_TILING_LIB_DIR="${AUTOMATIC_WINDOW_TILING_LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
HWT_TOOLS_BIN="${HWT_TOOLS_BIN:-$AUTOMATIC_WINDOW_TILING_LIB_DIR/hwt-tools}"

# _hwt_tiling — Run hwt-tools tiling subcommand, building from a checkout if needed.
_hwt_tiling() {
  if [ -x "$HWT_TOOLS_BIN" ]; then
    "$HWT_TOOLS_BIN" tiling "$@"
    return
  fi
  if [ -x "$AUTOMATIC_WINDOW_TILING_LIB_DIR/../dist/hwt-tools" ]; then
    "$AUTOMATIC_WINDOW_TILING_LIB_DIR/../dist/hwt-tools" tiling "$@"
    return
  fi
  if [ -x "$AUTOMATIC_WINDOW_TILING_LIB_DIR/../scripts/build_hwt_tools.sh" ]; then
    local bin
    bin="$(bash "$AUTOMATIC_WINDOW_TILING_LIB_DIR/../scripts/build_hwt_tools.sh" --print)" || return 1
    "$bin" tiling "$@"
    return
  fi
  printf 'hwt-tools is missing next to %s\n' "$AUTOMATIC_WINDOW_TILING_LIB_DIR" >&2
  return 1
}

# Resolve the GTK accelerator for the automatic-window-tiling sort action.
# Prints the accelerator to stdout. Honors OPEN_KITTY_SORT_HOTKEY when set.
resolve_sort_accel() {
  _hwt_tiling resolve
}

# Simulate the configured automatic-window-tiling hotkey via xdotool.
trigger_automatic_window_tiling() {
  _hwt_tiling trigger
}

#!/usr/bin/env bash
# automatic_window_tiling.sh - shared Super+T resolve/trigger for tiling extension.
#
# Sourced by open-kitty-and-sort.sh and deployed beside automatic_window_tiling.py
# so shell and Python callers share one resolution path. Resolution and triggering
# delegate to the Python module; conversion can run inline when Python is absent.

# Directory holding this library (override before sourcing when copied elsewhere).
AUTOMATIC_WINDOW_TILING_LIB_DIR="${AUTOMATIC_WINDOW_TILING_LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
AUTOMATIC_WINDOW_TILING_PY="$AUTOMATIC_WINDOW_TILING_LIB_DIR/automatic_window_tiling.py"

# Resolve the GTK accelerator for the automatic-window-tiling sort action.
# Prints the accelerator to stdout. Honors OPEN_KITTY_SORT_HOTKEY when set.
resolve_sort_accel() {
  python3 "$AUTOMATIC_WINDOW_TILING_PY" resolve
}

# Convert a GTK accelerator ("<Super>t") into an xdotool key spec ("super+t").
gtk_to_xdotool() {
  local accelerator="$1"
  if command -v python3 >/dev/null 2>&1 && [[ -f "$AUTOMATIC_WINDOW_TILING_PY" ]]; then
    python3 "$AUTOMATIC_WINDOW_TILING_PY" convert "$accelerator"
    return
  fi
  local value="$accelerator"
  value="${value//<Primary>/ctrl+}"
  value="${value//<Control>/ctrl+}"
  value="${value//<Alt>/alt+}"
  value="${value//<Meta>/alt+}"
  value="${value//<Super>/super+}"
  value="${value//<Shift>/shift+}"
  printf '%s' "$value"
}

# Simulate the configured automatic-window-tiling hotkey via xdotool.
trigger_automatic_window_tiling() {
  python3 "$AUTOMATIC_WINDOW_TILING_PY" trigger
}
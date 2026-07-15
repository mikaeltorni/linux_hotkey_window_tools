#!/usr/bin/env bash
# open-kitty-and-sort.sh — launch kitty, pin it to the active workspace, then
# trigger the window-sort (tiling) hotkey so the new terminal is tiled with the
# other kitty windows instead of having to be focused from the taskbar.
#
# Bound as a GNOME custom keybinding by the linux_hotkey_window_tools installer
# (component: open_kitty_sort_hotkey). It is deliberately self-contained and
# degrades gracefully: kitty always opens; the sort step is skipped (with a
# stderr message) when no key simulator is available — for example a Wayland
# session without a uinput-capable ydotool, or an X11 session without xdotool.
#
# The new kitty window is pinned to the workspace that was active when the
# hotkey fired (GNOME or an app-to-workspace rule may otherwise place it on a
# different workspace). On X11 this uses xdotool's EWMH workspace commands.
#
# Environment:
#   OPEN_KITTY_SORT_HOTKEY  - accelerator to simulate as the "sort" trigger
#                             (friendly "super+t" or GTK "<Super>t"). When unset
#                             the automatic-window-tiling extension's configured
#                             binding is read, falling back to "<Super>t".
#   OPEN_KITTY_SORT_DELAY   - maximum seconds to wait for the new kitty window
#                             to map before triggering the sort (default 2).
#                             With xdotool the sort fires the instant the window
#                             appears; this is only the upper bound.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$HOME/.local/share/linux_hotkey_window_tools/lib/automatic_window_tiling.sh" ]]; then
  AUTOMATIC_WINDOW_TILING_LIB_DIR="$HOME/.local/share/linux_hotkey_window_tools/lib"
elif [[ -f "$SCRIPT_DIR/../lib/automatic_window_tiling.sh" ]]; then
  AUTOMATIC_WINDOW_TILING_LIB_DIR="$SCRIPT_DIR/../lib"
else
  AUTOMATIC_WINDOW_TILING_LIB_DIR=""
fi
if [[ -n "$AUTOMATIC_WINDOW_TILING_LIB_DIR" ]]; then
  # shellcheck source=../lib/automatic_window_tiling.sh
  source "$AUTOMATIC_WINDOW_TILING_LIB_DIR/automatic_window_tiling.sh"
fi

# Capture the workspace that is active WHEN the hotkey fires, so the new kitty
# window can be pinned to it. On X11 xdotool reads the EWMH _NET_CURRENT_DESKTOP
# property that GNOME Shell maintains. Without xdotool this is unavailable and
# the window lands wherever the WM places it.
active_workspace=""
if command -v xdotool >/dev/null 2>&1; then
  active_workspace="$(xdotool get_desktop 2>/dev/null || true)"
fi

# Record the kitty windows that already exist BEFORE launching, so the wait
# loop below can detect the freshly-mapped window instead of matching a
# pre-existing one. Only meaningful when xdotool is available (X11).
preexisting_kitty_wids=""
if command -v xdotool >/dev/null 2>&1; then
  preexisting_kitty_wids="$(xdotool search --class kitty 2>/dev/null | sort || true)"
fi

# Launch kitty detached so this command returns immediately and the script can
# continue to the sort step. Redirect kitty's stdio to /dev/null and background
# it inside a subshell so it never holds the launcher's stdout/stderr pipe open
# (which would keep a pipe-reading parent waiting for EOF). A missing kitty is
# reported and the hotkey exits cleanly (no point sorting if no terminal opened).
if ! command -v kitty >/dev/null 2>&1; then
  printf 'open-kitty-and-sort: kitty not found on PATH; nothing to sort.\n' >&2
  exit 0
fi
( kitty >/dev/null 2>&1 & )

# Wait for the new kitty window to map, then pin it to the active workspace
# before sorting. With xdotool (X11) we poll for a NEW kitty window and act the
# instant it appears — no wasted blind waiting. Without xdotool we fall back to
# a fixed sleep. The maximum wait is OPEN_KITTY_SORT_DELAY seconds (default 2);
# if the window appears sooner, we act sooner.
sort_timeout="${OPEN_KITTY_SORT_DELAY:-2}"
new_wid=""

if command -v xdotool >/dev/null 2>&1; then
  # Smart wait: poll every 100ms for a kitty window ID that was not in the
  # pre-launch list. The new window is detected the moment it is mapped.
  iterations="$(python3 -c "print(max(1, int(float('${sort_timeout}') * 10)))" 2>/dev/null || echo 20)"
  for ((i = 0; i < iterations; i++)); do
    current="$(xdotool search --class kitty 2>/dev/null | sort || true)"
    if [ "$current" != "$preexisting_kitty_wids" ]; then
      # New kitty window mapped. Find its window ID (the first ID in the
      # current list that was not in the pre-launch list) so we can pin it to
      # the active workspace below.
      while IFS= read -r wid; do
        [ -z "$wid" ] && continue
        if ! printf '%s\n' "$preexisting_kitty_wids" | grep -qxF -- "$wid"; then
          new_wid="$wid"
          break
        fi
      done <<< "$current"
      break
    fi
    sleep 0.1 2>/dev/null || break
  done

  # Pin the new window to the workspace that was active when the hotkey fired.
  # GNOME (or an app-to-workspace rule such as app-rules/auto-move-windows) may
  # have placed the new window on a different workspace; move it back to the
  # active workspace, switch the view there, and focus the window so the tiler
  # sorts the focused application on the right workspace. Best-effort: failures
  # are ignored so the sort still runs.
  if [ -n "$new_wid" ] && [ -n "$active_workspace" ]; then
    xdotool set_desktop_for_window "$new_wid" "$active_workspace" 2>/dev/null || true
    xdotool set_desktop "$active_workspace" 2>/dev/null || true
    xdotool windowactivate "$new_wid" 2>/dev/null || true
    # Brief settle so GNOME Shell finishes the move/focus before the tiler runs.
    sleep 0.1 2>/dev/null || true
  fi

  # Pin the new window to the monitor the pointer is on, so it doesn't land on a
  # different display when the active workspace is crowded. This calls the
  # helper installed by linux_configuration_setup (component:
  # active_monitor_placement). Best-effort: if the helper is not installed the
  # sort still runs; kitty just may be on a different monitor.
  #
  # A settle delay is needed here because the window manager places new windows
  # asynchronously: the poll loop detects the window the instant it enters the X
  # tree, but the WM may not have moved it to its final (possibly wrong) monitor
  # yet. Without this wait the helper would see the window at an intermediate
  # position, conclude it is already on the right monitor, and exit — then the
  # WM would finish placing it on the wrong display.
  if [ -n "$new_wid" ] && [ -x "$HOME/.local/bin/pin-window-to-active-monitor.sh" ]; then
    sleep 0.3 2>/dev/null || true
    "$HOME/.local/bin/pin-window-to-active-monitor.sh" "$new_wid" 2>/dev/null || true
  fi
else
  # No window-detection tool available; give the window a fixed moment to map.
  if command -v sleep >/dev/null 2>&1; then
    sleep "$sort_timeout" 2>/dev/null || sleep "${sort_timeout%.*}" 2>/dev/null || true
  fi
fi

if declare -F trigger_automatic_window_tiling >/dev/null 2>&1; then
  if trigger_automatic_window_tiling; then
    exit 0
  fi
  accel="$(resolve_sort_accel 2>/dev/null || printf '<Super>t')"
  printf 'open-kitty-and-sort: automatic window tiling trigger failed (accel=%s).\n' "$accel" >&2
  exit 0
fi

# Fallback when the shared helper is not deployed (dev checkout without lib path).
accel="${OPEN_KITTY_SORT_HOTKEY:-<Super>t}"
if command -v xdotool >/dev/null 2>&1; then
  spec="${accel//<Super>/super+}"
  spec="${spec//<Control>/ctrl+}"
  spec="${spec//<Alt>/alt+}"
  spec="${spec//<Shift>/shift+}"
  xdotool key "$spec" 2>/dev/null || true
  exit 0
fi
printf 'open-kitty-and-sort: no key simulator (xdotool) found; kitty opened, sort skipped (accel=%s).\n' "$accel" >&2
exit 0

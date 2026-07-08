#!/usr/bin/env bash
# components.sh - Component manifest for linux_hotkey_window_tools.
#
# Sourced by install.sh after lib/hotkey_tools.sh, then executed through
# component_main from the shared component framework. The extension core
# (extension.js + schema, enabled in gsettings) is installed unconditionally by
# install.sh, so the program works regardless of selection. Each entry here is
# an optional, default-on, individually customizable hotkey.
#
# Entry format: "id|label|default(on/off)|function".
#
# Customize the accelerators non-interactively with the MOVE_HOTKEY,
# RESIZE_HOTKEY, and OPEN_KITTY_SORT_HOTKEY environment variables (friendly
# "control+t" / "alt+super+w" / "super+less" syntax); on a terminal the
# installer prompts for each selected hotkey.

ISC_REPO_NAME="linux_hotkey_window_tools"
ISC_REPO_LABEL="Pointer-driven window move/resize hotkeys"

ISC_COMPONENTS=(
  "move_hotkey|Move active window with pointer (default alt+super+w)|on|configure_move_hotkey|detect_move_hotkey|uninstall_move_hotkey"
  "resize_hotkey|Resize active window from center (default alt+super+e)|on|configure_resize_hotkey|detect_resize_hotkey|uninstall_resize_hotkey"
  "open_kitty_sort_hotkey|Open kitty terminal and auto-sort windows (default super+less)|on|configure_open_kitty_sort_hotkey|detect_open_kitty_sort_hotkey|uninstall_open_kitty_sort_hotkey"
)

# Linux Hotkey Window Tools — AGENTS.md

## What this repository owns

A single GNOME Shell extension (`window-move-resize@local`) providing two
pointer-driven, hold-to-act window hotkeys:

- `drag-active-window-with-pointer` (`<Alt><Super>W`) — move the focused window.
- `scale-active-window-from-center` (`<Alt><Super>E`) — resize the focused
  window about its pinned center.

These were extracted from `linux_hotkey_setup`'s `monitor-window-hotkeys@local`
extension. Keep them standalone: this repo must install on its own with
`bash install.sh`, and `linux_hotkey_setup` delegates to this installer by
default.

## GNOME Shell reload requirements

Editing `extension.js`, `metadata.json`, or anything under `schemas/` requires
a GNOME Shell reload to take effect. Follow the `linux-configuration` skill —
the single source of truth for GNOME reload safety: X11 in-place `Alt+F2 r`, or
logout/login on Wayland. Never `gnome-shell --replace`, log the user out, or
kill the Shell to force the change through.

Installer-side gsettings changes (`install.sh`) apply live on the next install
run; they do not need a Shell reload.

## Clean Installation Compatibility

All changes must remain compatible with a clean installation run through
`installation_scripts/install.sh` and this repository's `install.sh`. The
installer follows the root-optional (sudo-free) pattern: `bash install.sh`
must complete as the desktop user, and `sudo bash install.sh` must also work
for the clean-install chain. Do not rely on packages, files, or settings that
exist only on the current machine.

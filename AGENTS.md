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

## Installer architecture (core + selectable hotkeys)

The installer is component-based, built on the shared component framework
(`linux_installation_scripts_functions`, resolved from a sibling checkout or
downloaded on demand — never vendored, never a hard requirement):

- **Core (always installed):** `install_extension_core` in `lib/hotkey_tools.sh`
  copies the extension, compiles the schema, and enables the extension.
  `clear_component_hotkeys` then clears the component-owned schema keys before
  component routing, so the extension is present no matter which hotkeys the
  user selects (including none) and deselected hotkeys do not keep stale
  bindings.
- **Hotkeys (optional, default-on, customizable):** each hotkey is a component in
  `installer/components.sh` mapped to a `configure_*` function. Honor the shared
  framework subcommands (`--list-components`, `--select`, `--default`, `--all`,
  interactive menu); keep listing/help side-effect free (handled before the core
  install).
- **Customization:** accelerators come from the friendly `modifier+key` syntax
  via `lib/accelerator.py`. Resolution order is per-hotkey env var
  (`MOVE_HOTKEY` / `RESIZE_HOTKEY`) → interactive prompt on a TTY → built-in
  default, so automated/clean-install runs never block.
- **Conflict release:** `lib/conflict_finder.py` normalizes accelerators
  (order- and case-insensitive) so only the GNOME defaults that genuinely
  collide with a *chosen* accelerator are freed. Do not hardcode a fixed
  unbinding list.

New user-visible features must be added as components here (default-on unless a
requirement makes them optional) so the owning `install.sh` reproduces them on a
clean machine.

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

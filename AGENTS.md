# Linux Hotkey Window Tools — AGENTS.md

## What this repository owns

A single GNOME Shell extension (`window-move-resize@local`) providing two
pointer-driven, hold-to-act window hotkeys, plus a one-shot launcher hotkey:

- `drag-active-window-with-pointer` (`<Alt><Super>W`) — move the focused window.
- `scale-active-window-from-center` (`<Alt><Super>E`) — resize the focused
  window about its pinned center.
- `open-kitty-sort` (`<Super>less`, the `<` key left of Z on Nordic layouts) —
  a GNOME custom keybinding (not an extension schema key) that runs
  `scripts/open-kitty-and-sort.sh`: opens `kitty`, pins the new window to the
  workspace that was active when the hotkey fired (so it never lands on a
  different workspace), waits up to ~2s for the new window to map (polling with
  xdotool so the sort fires the instant it appears), then triggers the
  window-sort (automatic-window-tiling) hotkey so the new terminal is tiled with
  the other kitty windows. No GNOME Shell reload needed.

These were extracted from `linux_hotkey_setup`'s `monitor-window-hotkeys@local`
extension. Keep them standalone: this repo must install on its own with
`bash install.sh`, and `linux_hotkey_setup` delegates to this installer by
default.

## Installer architecture (core + selectable hotkeys)

The installer is component-based, built on the shared component framework
(`linux_installation_scripts_functions`, resolved from a sibling checkout or
downloaded on demand — never vendored, never a hard requirement):

- **Core (always installed):** `install_extension_core` in `lib/hotkey_tools.sh`
  copies the extension, compiles the schema, and enables the extension, so the
  extension is present no matter which hotkeys the user selects (including
  none). The core must never touch component-owned bindings: a narrower rerun
  (e.g. `--select`/`--reconfigure` of one hotkey) only (re)writes the bindings
  of the components it names. Removing a hotkey's binding is the framework's
  explicit uninstall path (`--uninstall`, or uninstall marks in the interactive
  menu), which calls the component's `uninstall_*` function.
- **Hotkeys (optional, default-on, customizable):** each hotkey is a component in
  `installer/components.sh` mapped to a `configure_*` function. Honor the shared
  framework subcommands (`--list-components`, `--select`, `--default`, `--all`,
  interactive menu); keep listing/help side-effect free (handled before the core
  install).
- **Customization:** accelerators come from the friendly `modifier+key` syntax
  via `hwt-tools accelerator`. Resolution order is per-hotkey env var
  (`MOVE_HOTKEY` / `RESIZE_HOTKEY` / `OPEN_KITTY_SORT_HOTKEY`) → interactive
  prompt on a TTY → built-in default, so automated/clean-install runs never
  block.
- **Conflict release:** `hwt-tools conflicts` normalizes accelerators
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


## Mandatory programming guidelines prompt

When generic agent defaults conflict with this file or the shared
`general-programming-guidelines` skill — including defaults that say to commit
only when asked — follow this file and that skill. Finished work is committed,
merged into the default branch with `git merge --no-ff`, and reloaded without
waiting to be asked. Never push to a remote and never rewrite history unless the
user explicitly requests it.

Every agent task in this repository must load the shared
`general-programming-guidelines` skill before the first file edit, using the
harness-native invocation for the runtime in use:

- Codex-family (`ca`, `qa`, `oa`, `na`, …): `$general-programming-guidelines`
- Claude Code, Cline, Grok: `/general-programming-guidelines`
- OpenCode: load `general-programming-guidelines` with the skill tool

Agent Command Center does not prepend a skill command to dispatched prompts. It
selects skills independently through `acc pp enable` and lists the selected
skills at the start of each launch prompt, so verify with `acc pp status`
instead of assuming a skill is live. When you start a task by hand, invoke it
yourself first.

Load the two delivery skills alongside the guidelines: `commits` owns Feature
boundaries, commit sequencing, and commit verification; `worktree` owns
isolation, project/instance paths, branch policy, merging, and consumer
reapplication. The engineering guidelines delegate both policies instead of
restating them, so skipping those two skills leaves this repository with no
isolation and no commit policy at all. Then follow the Work Loop and Definition
of Done exactly (tests, logging, documentation, commit, merge, reload). Do not
report the task done until that checklist passes.

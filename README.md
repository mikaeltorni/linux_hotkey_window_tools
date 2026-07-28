# Linux Hotkey Window Tools

> Part of [installation_scripts](https://github.com/mikaeltorni/installation_scripts) — the master installer that orchestrates a productivity-focused Ubuntu 24.04 desktop setup. Tested on Ubuntu 24.04.4 LTS.

A standalone GNOME Shell extension that adds two pointer-driven, hold-to-act
window hotkeys, plus a one-shot launcher that opens a terminal and sorts it into
place:

- **Move (`<Alt><Super>W`)** — hold the chord and the focused window follows the
  pointer. The drag ends the moment you release Super (a left-button click also
  ends it). The window is clamped inside the monitor work area.
- **Resize (`<Alt><Super>E`)** — hold the chord and the focused window scales
  about its pinned center from its current size. Moving the pointer farther from
  the center enlarges the window, and moving it back toward the center shrinks it.
  Drag diagonally to scale both axes at once; drag straight sideways or straight
  up/down and the gesture locks to that axis, so the other one keeps the size it
  started at instead of drifting with your hand. The lock only engages after a
  short committed movement and holds through small wobble, releasing again once
  you clearly turn diagonal or onto the other axis. Scaling ends when you release
  Super (a mouse click or Escape also ends it).
- **Open kitty and sort (`<Super><`)** — press once to open a `kitty` terminal,
  wait briefly for it to map, then trigger the window-sort (automatic tiling)
  hotkey so the new terminal is tiled with the other kitty windows instead of
  having to be focused from the taskbar. `<` is the `less` key — the key left of
  `Z` on Nordic layouts. This is a GNOME custom keybinding that runs a helper
  script (not a pointer gesture), so it needs no GNOME Shell reload.

The extension itself is the **always-installed core**: it is installed and
enabled no matter which hotkeys you select, with no implicit accelerator owned by
the core. Each hotkey is an **optional, default-on, fully customizable module** —
you pick the accelerator and the installer only frees the GNOME defaults that
collide with the chord you actually chose.

Both features were previously part of the `linux_hotkey_setup`
`monitor-window-hotkeys@local` extension and now live here so they can be
installed on their own. `linux_hotkey_setup` installs this repository by default
when it sits beside it in the projects directory.

## Repository dependencies

This repository installs and runs **standalone** — it has **no** dependency on
any other setup repository. It is *consumed by* `linux_hotkey_setup`, which
installs it by default when it sits beside it in the projects directory; that is
a one-way relationship and does not create a dependency in this direction.

See the full cross-repository map in
[installation_scripts/DEPENDENCIES.md](https://github.com/mikaeltorni/installation_scripts/blob/master/DEPENDENCIES.md).

## Technology Stack

- A GNOME Shell extension (`extension.js`) implementing the two hold-to-act
  pointer gestures and their lifecycle.
- A helper script (`scripts/open-kitty-and-sort.sh`) bound to a GNOME custom
  keybinding that launches `kitty` and triggers the window-sort hotkey.
- A Bash installer built on the shared component framework
  (`linux_installation_scripts_functions`), following the root-optional
  (sudo-free) installer pattern.

## Installation

```bash
bash install.sh        # interactive on a terminal, else the default-on set
sudo bash install.sh   # also supported (used by the clean-install chain)
```

The extension core (files + compiled gsettings schema, enabled) installs into
`~/.local/share/gnome-shell/extensions/window-move-resize@local` regardless of
which hotkeys you select. During each install run, component-owned bindings are
cleared first; each selected hotkey then has its accelerator applied, and any
GNOME default binding that collides with that accelerator is freed.

After installation, log out and back in before testing GNOME Shell extension
changes. Do not reload GNOME Shell extensions from an active Wayland session.

### Selecting components

The installer exposes each hotkey as an independently selectable component
through the shared framework:

```bash
bash install.sh --list-components     # id<TAB>label<TAB>default (side-effect free)
bash install.sh --default             # install the default-on set, no prompts
bash install.sh --all                 # install every component, no prompts
bash install.sh --select move_hotkey  # install exactly these component ids
bash install.sh --help                # full usage
```

| Component id             | Hotkey                                     | Default          |
| ------------------------ | ------------------------------------------ | ---------------- |
| `move_hotkey`            | Move active window with pointer            | `alt+super+w`    |
| `resize_hotkey`          | Resize active window from center           | `alt+super+e`    |
| `open_kitty_sort_hotkey` | Open kitty terminal and auto-sort windows  | `super+less` (`<`) |

## Configuration

### Choosing your own hotkeys

Each hotkey is fully customizable. Describe a chord with the friendly
`modifier+key` syntax — join the parts with `+`, for example `control+t`,
`super+u`, or `alt+super+w`. Accepted modifiers are `control`/`ctrl`, `alt`,
`super`/`win`, and `shift`.

- **Non-interactively** (and for the clean-install chain), set the per-hotkey
  environment variable:

  ```bash
  MOVE_HOTKEY=control+t RESIZE_HOTKEY=alt+shift+r \
    OPEN_KITTY_SORT_HOTKEY=super+comma bash install.sh --default
  ```

- **On a terminal**, the installer prompts for each selected hotkey and shows the
  default; press Enter to keep it.

The installer converts your spec to the GTK accelerator form and writes it to the
extension schema, then frees only the GNOME default bindings that collide with
the chord you chose.

### Adjusting a binding later

The two pointer hotkeys live in the extension schema
(`schemas/org.gnome.shell.extensions.window-move-resize.gschema.xml`). Override
them per user with `gsettings` at any time:

```bash
gsettings set org.gnome.shell.extensions.window-move-resize \
  scale-active-window-from-center "['<Alt><Super>R']"
```

The **open-kitty-and-sort** hotkey is a GNOME custom keybinding instead, so it is
adjusted (and takes effect live, with no Shell reload) via the relocatable
media-keys schema:

```bash
p=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/open-kitty-sort/
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$p \
  binding "'<Super>less'"
```

The helper script it runs (`~/.local/bin/open-kitty-and-sort.sh`) opens `kitty`,
pins the new window to the workspace that was active when the hotkey fired (so it
never lands on a different workspace), waits up to `OPEN_KITTY_SORT_DELAY`
seconds (default `2`) for the new window to map, then simulates the window-sort
hotkey. With `xdotool` (X11) it polls for the new kitty window and fires the sort
the instant it appears — the 2 s is only the upper bound, not a fixed delay. The
sort accelerator is resolved from `OPEN_KITTY_SORT_HOTKEY`, else the
`automatic-window-tiling@local` extension's configured binding, else `<Super>t`.
Simulation uses `xdotool` when available (X11); without a key simulator the
terminal still opens and the sort is skipped with a logged message (for example
on a clean Wayland install — install `ydotool` with uinput access there to enable
the auto-sort).

## Project Structure

- `install.sh` — standalone, component-based installer (root-optional); installs
  the extension core, clears component-owned bindings, then routes selected
  hotkeys through the shared framework.
- `installer/components.sh` — component manifest mapping each hotkey id to its
  configure function.
- `lib/hotkey_tools.sh` — install library: extension-core install plus the
  per-hotkey configure functions and conflict release.
- `lib/accelerator.py` — converts friendly `modifier+key` specs to GTK
  accelerators and normalizes them for comparison.
- `lib/conflict_finder.py` — detects GNOME default bindings that shadow a chosen
  accelerator (order- and case-insensitive).
- `lib/bash_logging.sh` — centralized best-effort file logger for the Bash
  installer (writes to `.log/install.log`).
- `lib/gsettings_strv.py` — tested string-array helper used by the installer.
- `lib/log_utils.py` — centralized Python file logger and call-tracing
  decorator for installer-side helpers (writes to `.log/`).
- `scripts/open-kitty-and-sort.sh` — runtime helper bound to the
  open-kitty-and-sort GNOME custom keybinding: opens `kitty`, waits briefly,
  then triggers the window-sort (automatic tiling) hotkey.
- `extension.js` — the GNOME Shell extension entry point and gesture state
  machines (move + resize).
- `windowUtils.js` — reusable, version-spanning window/pointer helpers used by
  `extension.js`.
- `logger.js` — centralized leveled logger for the extension (routes to the
  systemd journal).
- `metadata.json` — extension metadata.
- `schemas/` — gsettings schema and compiled binary.
- `tests/` — pytest suite for the Python helpers and static installer checks.
- `.log/` — runtime logs from installer code and helpers (git-ignored).

## Deployment

```bash
bash -n install.sh
pytest tests/ -v
sudo bash install.sh
```

## Detect, reconfigure, and uninstall

This installer tracks what it has installed and can re-apply or remove it, so you
can refresh configuration after a repo update or cleanly back a feature out.

```bash
bash install.sh --detect            # show each component as installed|absent
bash install.sh --reconfigure a,b   # re-apply (idempotent) these component ids
bash install.sh --uninstall a,b     # uninstall these component ids
```

In the interactive menu (run `bash install.sh` on a terminal, or via the master
installer), already-installed components show a green `✓`. Select one with
**space** to **reconfigure** it (`~`), press **`u`** to mark it for **uninstall**
(`✗`), or press **`r`** to reconfigure every installed component at once. Detection
uses a live check where deterministic and otherwise an install receipt under
`${XDG_STATE_HOME:-~/.local/state}/isc/receipts/`; a component without a reversal
step simply clears that receipt on uninstall.

## Disclaimer

This software is provided under the MIT License on an **“as is”** basis, without warranties of any kind. To the maximum extent permitted by applicable law, the authors and copyright holders shall not be liable for any claims, damages, losses, or other liability arising from the use of this software.

You are solely responsible for determining whether this software is suitable, safe, lawful, and appropriate for your intended use. Unless explicitly stated otherwise, this project is general-purpose software and is not designed, tested, certified, or approved for safety-critical, medical, automotive, aviation, industrial-control, life-support, cybersecurity-critical, financial-critical, or other high-risk use cases.

The authors and copyright holders make no guarantees regarding security, reliability, availability, correctness, compliance, non-infringement, or fitness for any particular purpose.

This notice is intended to clarify the nature of the project and does not impose additional restrictions beyond the MIT License.

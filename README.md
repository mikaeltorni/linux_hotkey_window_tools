# Linux Hotkey Window Tools

> Part of [installation_scripts](https://github.com/mikaeltorni/installation_scripts) — the master installer that orchestrates a productivity-focused Ubuntu 24.04 desktop setup. Tested on Ubuntu 24.04.4 LTS.

A standalone GNOME Shell extension that adds two pointer-driven, hold-to-act
window hotkeys:

- **Move (`<Alt><Super>W`)** — hold the chord and the focused window follows the
  pointer. The drag ends the moment you release Super (a left-button click also
  ends it). The window is clamped inside the monitor work area.
- **Resize (`<Alt><Super>E`)** — hold the chord and the focused window scales
  about its pinned center from its current size. Moving the pointer farther from
  the center enlarges the window, and moving it back toward the center shrinks it,
  on both axes at once. Scaling ends when you release Super (a mouse click or
  Escape also ends it).

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
- A Bash installer for GNOME Shell extension installation and gsettings binding
  setup, following the root-optional (sudo-free) installer pattern.

## Installation

```bash
bash install.sh        # sudo-free, run as the desktop user
sudo bash install.sh   # also supported (used by the clean-install chain)
```

The installer copies the extension into
`~/.local/share/gnome-shell/extensions/window-move-resize@local`, compiles its
gsettings schema, applies the `<Alt><Super>W` / `<Alt><Super>E` binding
defaults, frees GNOME's default `toggle-maximized` binding on `<Alt><Super>E`,
and enables the extension.

After installation, log out and back in before testing GNOME Shell extension
changes. Do not reload GNOME Shell extensions from an active Wayland session.

## Configuration

The two keybindings live in the extension schema defaults
(`schemas/org.gnome.shell.extensions.window-move-resize.gschema.xml`):

- `drag-active-window-with-pointer` → `['<Alt><Super>W']`
- `scale-active-window-from-center` → `['<Alt><Super>E']`

Override them per user with `gsettings`:

```bash
gsettings set org.gnome.shell.extensions.window-move-resize \
  scale-active-window-from-center "['<Alt><Super>R']"
```

## Project Structure

- `install.sh` — standalone installer (root-optional).
- `lib/gsettings_strv.py` — tested string-array helper used by the installer.
- `lib/log_utils.py` — centralized file logger for the installer-side helpers
  (writes to `.log/`).
- `extension.js` — the GNOME Shell extension entry point and gesture state
  machines (move + resize).
- `windowUtils.js` — reusable, version-spanning window/pointer helpers used by
  `extension.js`.
- `logger.js` — centralized leveled logger for the extension (routes to the
  systemd journal).
- `metadata.json` — extension metadata.
- `schemas/` — gsettings schema and compiled binary.
- `tests/` — pytest suite for the Python helpers.
- `.log/` — runtime logs from the installer helpers (git-ignored).

## Deployment

```bash
bash -n install.sh
pytest tests/ -v
sudo bash install.sh
```

## Disclaimer

This software is provided under the MIT License on an **“as is”** basis, without warranties of any kind. To the maximum extent permitted by applicable law, the authors and copyright holders shall not be liable for any claims, damages, losses, or other liability arising from the use of this software.

You are solely responsible for determining whether this software is suitable, safe, lawful, and appropriate for your intended use. Unless explicitly stated otherwise, this project is general-purpose software and is not designed, tested, certified, or approved for safety-critical, medical, automotive, aviation, industrial-control, life-support, cybersecurity-critical, financial-critical, or other high-risk use cases.

The authors and copyright holders make no guarantees regarding security, reliability, availability, correctness, compliance, non-infringement, or fitness for any particular purpose.

This notice is intended to clarify the nature of the project and does not impose additional restrictions beyond the MIT License.

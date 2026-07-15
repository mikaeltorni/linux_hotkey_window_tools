"""automatic_window_tiling.py - resolve and trigger the Super+T tiling hotkey.

Reads the ``automatic-window-tiling@local`` extension's
``tile-focused-application-windows`` gsettings key (default ``<Super>t``),
converts GTK accelerators to xdotool key specs, and simulates the binding.
Shared by ``open-kitty-and-sort.sh`` and phrase_automation's agent placement
pipeline so both repos use one resolution path.

Components:
  - DEFAULT_SORT_ACCELERATOR: Fallback when gsettings is empty or missing.
  - AWT_EXTENSION_SCHEMA_DIR: Compiled schemas under the user's extension dir.
  - resolve_sort_accelerator: Resolve the GTK accelerator string.
  - gtk_to_xdotool: Convert GTK form to an xdotool key spec.
  - trigger_automatic_window_tiling: Simulate the tiling hotkey via xdotool.

Usage:
  python3 automatic_window_tiling.py resolve
  python3 automatic_window_tiling.py xdotool-spec
  python3 automatic_window_tiling.py trigger
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from log_utils import get_logger, log_call

LOGGER = get_logger("automatic_window_tiling", "automatic_window_tiling.log")

DEFAULT_SORT_ACCELERATOR = "<Super>t"
AWT_EXTENSION_ID = "automatic-window-tiling@local"
AWT_SCHEMA = "org.gnome.shell.extensions.automatic-window-tiling"
AWT_KEY = "tile-focused-application-windows"
AWT_EXTENSION_SCHEMA_DIR = (
    Path.home() / ".local/share/gnome-shell/extensions" / AWT_EXTENSION_ID / "schemas"
)
ENV_SORT_HOTKEY = "OPEN_KITTY_SORT_HOTKEY"


@log_call(LOGGER)
def resolve_sort_accelerator(
    *,
    env: os._Environ[str] | None = None,
    gsettings_get: Callable[[Sequence[str]], str] | None = None,
    schema_dir: Path | None = None,
) -> str:
    """Return the GTK accelerator for the automatic-window-tiling sort action.

    Resolution order matches ``open-kitty-and-sort.sh``:
      1. ``OPEN_KITTY_SORT_HOTKEY`` environment override (friendly or GTK form)
      2. The extension's configured ``tile-focused-application-windows`` key
      3. ``<Super>t``

    Args:
        env: Injectable environment mapping (defaults to ``os.environ``).
        gsettings_get: Injectable gsettings runner returning stdout text.
        schema_dir: Extension schema directory; defaults to the user install path.

    Returns:
        A GTK accelerator such as ``"<Super>t"``.
    """
    environment = env if env is not None else os.environ
    override = (environment.get(ENV_SORT_HOTKEY) or "").strip()
    if override:
        return override

    schema_path = schema_dir if schema_dir is not None else AWT_EXTENSION_SCHEMA_DIR
    if schema_path.is_dir():
        runner = gsettings_get or _default_gsettings_get
        try:
            raw = runner(
                [
                    "gsettings",
                    "--schemadir",
                    str(schema_path),
                    "get",
                    AWT_SCHEMA,
                    AWT_KEY,
                ]
            )
        except (OSError, subprocess.SubprocessError) as error:
            LOGGER.warning("gsettings read failed: %s", error)
            raw = ""
        first = _first_quoted_gsettings_value(raw)
        if first:
            return first

    return DEFAULT_SORT_ACCELERATOR


def _first_quoted_gsettings_value(raw: str) -> str:
    """Extract the first single-quoted entry from a gsettings strv value."""
    if "'" not in (raw or ""):
        return ""
    first = raw.split("'", 2)
    if len(first) < 2:
        return ""
    return first[1].strip()


def _default_gsettings_get(command: Sequence[str]) -> str:
    result = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return (result.stdout or "").strip()


@log_call(LOGGER)
def gtk_to_xdotool(accelerator: str) -> str:
    """Convert a GTK accelerator to an xdotool key spec.

    Modifier tokens are normalized; the final key token is preserved verbatim
    so named keysyms (``less``, ``Print``, ``Left``) stay valid for xdotool.

    Args:
        accelerator: GTK accelerator such as ``"<Super>t"`` or ``"<Control><Alt>t"``.

    Returns:
        An xdotool key spec such as ``"super+t"`` or ``"ctrl+alt+t"``.
    """
    value = accelerator or ""
    value = value.replace("<Primary>", "ctrl+")
    value = value.replace("<Control>", "ctrl+")
    value = value.replace("<Alt>", "alt+")
    value = value.replace("<Meta>", "alt+")
    value = value.replace("<Super>", "super+")
    value = value.replace("<Shift>", "shift+")
    return value


@log_call(LOGGER)
def trigger_automatic_window_tiling(
    *,
    env: os._Environ[str] | None = None,
    gsettings_get: Callable[[Sequence[str]], str] | None = None,
    which: Callable[[str], str | None] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    schema_dir: Path | None = None,
) -> bool:
    """Simulate the automatic-window-tiling hotkey via xdotool.

    Missing xdotool or a failed key simulation returns ``False`` without
    raising, matching the graceful degradation in ``open-kitty-and-sort.sh``.

    Args:
        env: Injectable environment mapping.
        gsettings_get: Injectable gsettings runner.
        which: Injectable executable lookup.
        run: Injectable subprocess runner.
        schema_dir: Extension schema directory override.

    Returns:
        ``True`` when xdotool accepted the key command, else ``False``.
    """
    executable_lookup = which or shutil.which
    xdotool = executable_lookup("xdotool")
    if not xdotool:
        LOGGER.warning("xdotool not available; automatic window tiling skipped")
        return False
    accel = resolve_sort_accelerator(
        env=env,
        gsettings_get=gsettings_get,
        schema_dir=schema_dir,
    )
    spec = gtk_to_xdotool(accel)
    try:
        result = run(
            [xdotool, "key", spec],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        LOGGER.warning("xdotool key failed: %s", error)
        return False
    if result.returncode != 0:
        LOGGER.warning(
            "xdotool key rejected accel=%r spec=%r status=%s",
            accel,
            spec,
            result.returncode,
        )
        return False
    LOGGER.info("triggered automatic window tiling accel=%r spec=%r", accel, spec)
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for shell callers and installers.

    Args:
        argv: Optional argument list. Supported commands: ``resolve``,
            ``xdotool-spec``, ``trigger``.

    Returns:
        Process exit code: 0 on success, 2 on invalid usage.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: automatic_window_tiling.py resolve|xdotool-spec|convert <accel>|trigger",
            file=sys.stderr,
        )
        return 2
    command = args[0]
    if command == "resolve":
        print(resolve_sort_accelerator())
        return 0
    if command == "xdotool-spec":
        print(gtk_to_xdotool(resolve_sort_accelerator()))
        return 0
    if command == "convert":
        if len(args) != 2:
            print("Usage: automatic_window_tiling.py convert <gtk-accelerator>", file=sys.stderr)
            return 2
        print(gtk_to_xdotool(args[1]))
        return 0
    if command == "trigger":
        return 0 if trigger_automatic_window_tiling() else 1
    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
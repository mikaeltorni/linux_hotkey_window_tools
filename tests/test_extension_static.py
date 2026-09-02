"""Static safety checks for the GNOME Shell gesture state machines."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension.js"


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"function {name}\(state\) \{{(?P<body>.*?)\n\}}", source, re.S)
    assert match is not None, f"{name}() not found"
    return match.group("body")


def test_gesture_starters_ignore_reentry_before_registering_timeout():
    source = EXTENSION.read_text(encoding="utf-8")

    for name in ("startPointerDrag", "startCenterScale"):
        body = _function_body(source, name)
        guard_index = body.find("if (state.timeoutId)")
        timeout_index = body.find("GLib.timeout_add")

        assert guard_index != -1, f"{name}() must guard against active timeouts"
        assert timeout_index != -1, f"{name}() must register a timeout"
        assert guard_index < timeout_index, f"{name}() must guard before adding a timeout"


def test_drag_clamps_against_the_monitor_under_the_pointer():
    """Clamping against the window's own monitor pins it to that monitor's edge,
    which makes dragging a window across monitors impossible."""
    source = EXTENSION.read_text(encoding="utf-8")

    assert "getWorkAreaAt(win, pointerX, pointerY)" in source, (
        "the drag loop must clamp against the work area under the pointer"
    )
    assert "getWindowWorkArea(" not in source, (
        "extension.js must not clamp gestures against the window's own monitor"
    )


def test_drag_ends_on_a_polled_pointer_button_release():
    """The stage 'captured-event' handler never sees a click that lands on an
    application window (always on Wayland, and on X11 without a shell grab), so
    the drag must detect the button release from the polled modifier mask.
    Without this the window keeps following the pointer after the click is let
    go — the drag can only be escaped by releasing Super."""
    source = EXTENSION.read_text(encoding="utf-8")

    assert "Clutter.ModifierType.BUTTON1_MASK" in source, (
        "the drag must read the left-button bit from the polled modifier mask"
    )

    body = _function_body(source, "startPointerDrag")
    assert "DRAG_BUTTON_MASK" in body, (
        "the drag poll must test the left-button mask on every tick"
    )
    assert "state.buttonHeld" in body, (
        "the drag poll must remember a seen button press so its release can end"
        " the gesture"
    )

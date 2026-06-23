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

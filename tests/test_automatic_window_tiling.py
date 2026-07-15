"""Unit tests for the shared automatic-window-tiling resolve/trigger helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import automatic_window_tiling as awt


def test_resolve_sort_accelerator_uses_env_override():
    assert awt.resolve_sort_accelerator(env={"OPEN_KITTY_SORT_HOTKEY": "<Super>w"}) == "<Super>w"


def test_resolve_sort_accelerator_reads_gsettings_first_entry():
    def gsettings_get(_command):
        return "['<Super>t']"

    assert (
        awt.resolve_sort_accelerator(
            env={},
            gsettings_get=gsettings_get,
            schema_dir=Path("/tmp/schemas"),
        )
        == "<Super>t"
    )


def test_resolve_sort_accelerator_defaults_when_gsettings_empty():
    def gsettings_get(_command):
        return "@as []"

    assert (
        awt.resolve_sort_accelerator(
            env={},
            gsettings_get=gsettings_get,
            schema_dir=Path("/tmp/schemas"),
        )
        == "<Super>t"
    )


def test_gtk_to_xdotool_preserves_named_keys():
    assert awt.gtk_to_xdotool("<Control><Alt>t") == "ctrl+alt+t"
    assert awt.gtk_to_xdotool("<Super>less") == "super+less"


def test_trigger_automatic_window_tiling_emits_xdotool_key_spec():
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(list(command))
        return MagicMock(returncode=0)

    assert awt.trigger_automatic_window_tiling(
        env={"OPEN_KITTY_SORT_HOTKEY": "<Super>t"},
        which=lambda name: "/usr/bin/xdotool" if name == "xdotool" else None,
        run=run,
    )
    assert calls == [["/usr/bin/xdotool", "key", "super+t"]]


def test_trigger_automatic_window_tiling_returns_false_without_xdotool():
    assert not awt.trigger_automatic_window_tiling(which=lambda _name: None)
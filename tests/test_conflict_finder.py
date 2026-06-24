"""Tests for normalizing conflict detection against GNOME keybinding rows."""

from __future__ import annotations

from accelerator import normalize_accelerator
from conflict_finder import iter_conflicts


def test_finds_conflict_regardless_of_order_and_case():
    rows = [
        "toggle-maximized ['<Alt>F10']",
        "activate-window-menu ['<Super><Alt>E']",
        "switch-to-workspace-left ['<Super>Page_Up', '<Control><Alt>Left']",
    ]
    target = normalize_accelerator("alt+super+e")

    assert list(iter_conflicts(rows, target)) == [
        ("activate-window-menu", "<Super><Alt>E"),
    ]


def test_returns_each_matching_array_element():
    rows = ["some-key ['<Alt><Super>w', '<Super><Alt>W']"]
    target = normalize_accelerator("alt+super+w")

    assert list(iter_conflicts(rows, target)) == [
        ("some-key", "<Alt><Super>w"),
        ("some-key", "<Super><Alt>W"),
    ]


def test_no_conflict_when_accelerator_absent():
    rows = ["toggle-maximized ['<Alt>F10']", "close ['<Alt>F4']"]
    target = normalize_accelerator("alt+super+e")

    assert list(iter_conflicts(rows, target)) == []


def test_skips_blank_and_unparsable_rows():
    rows = ["", "   ", "broken-line-without-value", "ok ['<Alt><Super>e']"]
    target = normalize_accelerator("alt+super+e")

    assert list(iter_conflicts(rows, target)) == [("ok", "<Alt><Super>e")]

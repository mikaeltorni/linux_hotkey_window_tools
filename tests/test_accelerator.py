"""Tests for the friendly-to-GNOME accelerator conversion and normalization."""

from __future__ import annotations

import pytest

from accelerator import normalize_accelerator, to_gnome_accelerator


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("control+t", "<Control>t"),
        ("ctrl+t", "<Control>t"),
        ("super+u", "<Super>u"),
        ("win+u", "<Super>u"),
        ("alt+super+w", "<Alt><Super>w"),
        # Modifier order in the input does not change the canonical output.
        ("super+alt+w", "<Alt><Super>w"),
        ("shift+control+a", "<Control><Shift>a"),
        # Named keys pass through verbatim.
        ("Print", "Print"),
        ("alt+F4", "<Alt>F4"),
    ],
)
def test_to_gnome_accelerator_converts_friendly_specs(spec, expected):
    assert to_gnome_accelerator(spec) == expected


@pytest.mark.parametrize("spec", ["", "   ", "control+", "alt++t", "foo+t"])
def test_to_gnome_accelerator_rejects_invalid_specs(spec):
    with pytest.raises(ValueError):
        to_gnome_accelerator(spec)


def test_normalize_matches_across_form_order_and_case():
    # Friendly and GTK forms, differing modifier order and key casing, compare
    # equal once normalized.
    assert normalize_accelerator("alt+super+E") == normalize_accelerator("<Super><Alt>e")
    assert normalize_accelerator("<Alt><Super>e") == normalize_accelerator("alt+super+e")


def test_normalize_distinguishes_different_chords():
    assert normalize_accelerator("<Alt><Super>e") != normalize_accelerator("<Alt><Super>w")
    assert normalize_accelerator("<Alt>e") != normalize_accelerator("<Super>e")


def test_normalize_rejects_unknown_modifier():
    with pytest.raises(ValueError):
        normalize_accelerator("<Hyper>e")

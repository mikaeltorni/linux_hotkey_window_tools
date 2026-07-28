"""Behavior tests for the center-scale axis-intent helper in extension.js.

extension.js can only be imported by GNOME Shell (it pulls in gi:// modules),
so these tests lift the self-contained resolveAxisLock() helper and its
constants out of the source and exercise them in node, which is how the same
code runs at gesture time.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension.js"

HORIZONTAL = "horizontal"
VERTICAL = "vertical"
NONE = "none"


def _helper_source() -> str:
    source = EXTENSION.read_text(encoding="utf-8")

    constants = re.findall(r"^const AXIS_LOCK_[A-Z_]+ = .*?;$", source, re.M)
    assert constants, "AXIS_LOCK_* constants not found in extension.js"

    match = re.search(r"^function resolveAxisLock\(.*?^\}$", source, re.M | re.S)
    assert match is not None, "resolveAxisLock() not found in extension.js"

    return "\n".join(constants) + "\n" + match.group(0)


def _resolve_many(cases: list[tuple[float, float, str]]) -> list[str]:
    """Run resolveAxisLock() in node once for every (dx, dy, lock) case."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the extension.js helper")

    script = (
        _helper_source()
        + "\nconst cases = "
        + json.dumps(cases)
        + ";\nconsole.log(JSON.stringify("
        "cases.map(([dx, dy, lock]) => resolveAxisLock(dx, dy, lock))));\n"
    )
    completed = subprocess.run(
        [node, "--input-type=module", "-"],
        input=script,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_straight_drags_lock_to_a_single_axis():
    """A clearly horizontal/vertical drag must resize only that axis."""
    assert _resolve_many(
        [
            (200, 4, NONE),
            (-200, -4, NONE),
            (4, 200, NONE),
            (-4, 200, NONE),
        ]
    ) == [HORIZONTAL, HORIZONTAL, VERTICAL, VERTICAL]


def test_diagonal_drags_keep_scaling_both_axes():
    """Corner intent is unchanged: no lock, both axes follow the pointer."""
    assert _resolve_many([(200, 200, NONE), (200, 120, NONE), (-120, 200, NONE)]) == [
        NONE,
        NONE,
        NONE,
    ]


def test_short_travel_never_locks_and_releases_an_existing_lock():
    """Below the travel threshold the intent is undecided, so scaling is free."""
    assert _resolve_many(
        [(10, 1, NONE), (1, 10, NONE), (10, 1, HORIZONTAL), (1, 10, VERTICAL)]
    ) == [NONE, NONE, NONE, NONE]


def test_hysteresis_holds_a_lock_through_off_axis_wobble():
    """Wobble too large to enter a lock must not break an established one."""
    # 50/200 = 0.25 enters; 120/200 = 0.6 would not enter but must not release.
    assert _resolve_many([(200, 120, NONE), (200, 120, HORIZONTAL), (120, 200, VERTICAL)]) == [
        NONE,
        HORIZONTAL,
        VERTICAL,
    ]


def test_lock_releases_once_the_drag_turns_diagonal():
    """Past the exit ratio the gesture is diagonal again and the lock drops."""
    assert _resolve_many([(200, 180, HORIZONTAL), (180, 200, VERTICAL)]) == [NONE, NONE]


def test_lock_switches_when_the_drag_turns_onto_the_other_axis():
    """A drag that reverses into a straight run on the other axis re-locks."""
    assert _resolve_many([(20, 300, HORIZONTAL), (300, 20, VERTICAL)]) == [
        VERTICAL,
        HORIZONTAL,
    ]


def test_enter_ratio_is_stricter_than_exit_ratio():
    """The hysteresis band must exist, otherwise the lock flickers per poll."""
    source = EXTENSION.read_text(encoding="utf-8")
    enter = float(re.search(r"AXIS_LOCK_ENTER_RATIO = ([\d.]+);", source).group(1))
    exit_ratio = float(re.search(r"AXIS_LOCK_EXIT_RATIO = ([\d.]+);", source).group(1))

    assert enter < exit_ratio


def test_center_scale_poll_holds_the_locked_out_axis_at_its_start_size():
    """The locked-out axis must be pinned to the size the gesture started at."""
    source = EXTENSION.read_text(encoding="utf-8")
    match = re.search(r"function startCenterScale\(.*?\n\}\n", source, re.S)
    assert match is not None, "startCenterScale() not found"
    body = match.group(0)

    assert "resolveAxisLock(" in body, "the poll must classify the drag's axis intent"
    assert "height = state.startHeight;" in body
    assert "width = state.startWidth;" in body

"""conflict_finder.py - find GNOME default bindings that shadow a hotkey.

``install.sh`` only releases the stock GNOME keybindings that genuinely collide
with a hotkey the user chose to add. Detecting a collision by raw string compare
is unreliable because GNOME stores modifiers in varying orders and casings
(``<Super><Alt>Left``); this helper normalizes both sides instead.

It reads ``gsettings list-recursively <schema>`` output on stdin and a target
accelerator as the sole argument, then prints one ``key<TAB>stored-accelerator``
line per conflict so the shell can remove each exact stored value. Diagnostics
go to the repository ``.log/`` directory via log_utils, keeping stdout clean.

Components:
  - parse_strv: Reuse gsettings_strv's array parser for stored values.
  - iter_conflicts: Yield (key, stored) pairs whose accelerator matches target.
  - main: CLI entrypoint used by install.sh.

Usage:
  gsettings list-recursively org.gnome.desktop.wm.keybindings \
    | python3 lib/conflict_finder.py '<Alt><Super>e'
"""

from __future__ import annotations

import sys
from typing import Iterator

from accelerator import normalize_accelerator
from gsettings_strv import parse_strv
from log_utils import get_logger, log_call

LOGGER = get_logger("conflict_finder", "conflict_finder.log")


def iter_conflicts(
    lines: list[str], target: tuple[frozenset[str], str]
) -> Iterator[tuple[str, str]]:
    """Yield (key, stored-accelerator) pairs that match the target accelerator.

    Each input line is a ``gsettings list-recursively`` row of the form
    ``key ['<Accel>', ...]`` (the schema prefix already stripped by the caller).
    Stored accelerators that fail to normalize are skipped rather than raising,
    so a single odd binding never aborts the install.

    Args:
        lines: The list-recursively rows to scan (schema prefix removed).
        target: The normalized accelerator to match against, as returned by
            ``normalize_accelerator``.

    Yields:
        ``(key, stored)`` tuples where ``stored`` is the exact array element to
        remove from that key.
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        key, _, raw_value = line.partition(" ")
        if not key or not raw_value:
            continue
        for stored in parse_strv(raw_value):
            try:
                if normalize_accelerator(stored) == target:
                    LOGGER.debug("conflict on key %r: stored %r", key, stored)
                    yield key, stored
            except ValueError:
                LOGGER.debug("skipping unparsable stored accelerator %r", stored)


@log_call(LOGGER)
def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by ``install.sh``.

    Reads list-recursively rows on stdin and prints ``key<TAB>stored`` for each
    binding whose accelerator matches the target passed as the only argument.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``). Must be a
            single target accelerator (friendly or GTK form).

    Returns:
        Process exit code: 0 on success, 2 on invalid usage or target.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        LOGGER.error("invalid conflict_finder usage: %r", args)
        print("Usage: conflict_finder.py <target-accelerator>", file=sys.stderr)
        return 2

    try:
        target = normalize_accelerator(args[0])
    except ValueError as error:
        LOGGER.error("invalid target accelerator: %s", error)
        print(f"Invalid accelerator: {error}", file=sys.stderr)
        return 2

    lines = sys.stdin.read().splitlines()
    for key, stored in iter_conflicts(lines, target):
        print(f"{key}\t{stored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

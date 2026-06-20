"""gsettings_strv.py - helpers for GNOME gsettings string-array values.

Pure functions for reading, de-duplicating, and writing the ``type="as"``
string-array values that install.sh manipulates (e.g. enabled-extensions and
the wm keybinding lists). The CLI entrypoint reads the current value from the
``CURRENT`` environment variable and prints the updated array to stdout for
``gsettings set``; all diagnostics go to the repository ``.log/`` directory via
log_utils so stdout stays clean.

Components:
  - parse_strv: Parse gsettings array output into a list of strings.
  - unique_values: Drop duplicates while preserving first appearance.
  - append_strv: Return a de-duplicated array with a value appended.
  - remove_strv: Return an array with a value removed.
  - format_strv: Serialize values back to the gsettings string-array format.
  - main: CLI entrypoint used by install.sh.

Usage:
  CURRENT="$(gsettings get org.gnome.shell enabled-extensions)" \
    python3 lib/gsettings_strv.py append "window-move-resize@local"
"""

from __future__ import annotations

import ast
import os
import sys

from log_utils import get_logger

_log = get_logger()


def parse_strv(raw: str | None) -> list[str]:
    """Parse gsettings string-array output into normalized string values.

    Strips the optional ``@as`` type prefix that ``gsettings get`` prints, then
    safely evaluates the literal. Any value that is missing, malformed, or not a
    list yields an empty list rather than raising, so the installer never aborts
    on unexpected gsettings output.

    Args:
        raw: Raw ``gsettings get`` output (e.g. ``"@as ['a', 'b']"``), or None.

    Returns:
        The parsed values as a list of strings; empty when input is missing or
        not a valid array literal.
    """
    value = (raw or "").strip()
    if value.startswith("@as "):
        value = value[4:].strip()

    try:
        parsed = ast.literal_eval(value) if value else []
    except (SyntaxError, ValueError):
        _log.warning("parse_strv: could not parse gsettings array: %r", raw)
        return []

    if not isinstance(parsed, list):
        _log.warning("parse_strv: parsed value is not a list: %r", raw)
        return []

    return [str(item) for item in parsed]


def unique_values(values: list[str]) -> list[str]:
    """Return values with duplicates removed while preserving first appearance.

    Args:
        values: The list of strings to de-duplicate.

    Returns:
        A new list containing each distinct value once, in first-seen order.
    """
    return list(dict.fromkeys(values))


def append_strv(raw: str | None, value: str) -> list[str]:
    """Return normalized values with ``value`` appended if it is not present.

    Args:
        raw: Raw ``gsettings get`` output for the array, or None.
        value: The string to ensure is present in the array.

    Returns:
        The de-duplicated array with ``value`` appended when it was absent (and
        non-empty); otherwise the existing de-duplicated array unchanged.
    """
    current = unique_values(parse_strv(raw))
    if value and value not in current:
        current.append(value)
        _log.debug("append_strv: added %r -> %r", value, current)
    else:
        _log.debug("append_strv: %r already present; unchanged", value)
    return current


def remove_strv(raw: str | None, value: str) -> list[str]:
    """Return normalized values with every occurrence of ``value`` removed.

    Args:
        raw: Raw ``gsettings get`` output for the array, or None.
        value: The string to drop from the array.

    Returns:
        A new list containing the parsed values with all occurrences of
        ``value`` removed.
    """
    result = [item for item in parse_strv(raw) if item != value]
    _log.debug("remove_strv: removed %r -> %r", value, result)
    return result


def format_strv(values: list[str]) -> str:
    """Serialize values for ``gsettings set``.

    Args:
        values: The list of strings to serialize.

    Returns:
        A gsettings-compatible array literal, e.g. ``"['a', 'b']"``.
    """
    return "[" + ", ".join(repr(str(item)) for item in values) + "]"


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by ``install.sh``.

    Reads the current array from the ``CURRENT`` environment variable, applies
    the requested ``append`` or ``remove`` action with the given value, and
    prints the serialized result to stdout. Diagnostics go to ``.log/`` only.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``). Must be
            ``[action, value]`` where action is ``"append"`` or ``"remove"``.

    Returns:
        Process exit code: 0 on success, 2 on invalid usage.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in {"append", "remove"}:
        _log.error("main: invalid usage: %r", args)
        print("Usage: gsettings_strv.py append|remove <value>", file=sys.stderr)
        return 2

    action, value = args
    current = os.environ.get("CURRENT", "")
    _log.info("main: %s %r against current=%r", action, value, current)
    result = append_strv(current, value) if action == "append" else remove_strv(current, value)
    print(format_strv(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

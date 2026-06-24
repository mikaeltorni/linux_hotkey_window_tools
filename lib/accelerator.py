"""accelerator.py - convert friendly hotkey specs to GNOME accelerator strings.

Users describe a hotkey with the simple ``modifier+key`` syntax (for example
``control+t``, ``super+u``, or ``alt+super+w``). The GNOME schema keys this
installer writes expect the canonical GTK accelerator form instead
(``<Control>t``, ``<Super>u``, ``<Alt><Super>w``). This module performs that
translation. The CLI entrypoint prints the canonical accelerator to stdout for
``gsettings set`` while every diagnostic goes to the repository ``.log/``
directory via log_utils, keeping stdout clean for the shell caller.

Components:
  - MODIFIER_ALIASES: Map accepted modifier words to canonical GTK names.
  - MODIFIER_ORDER: Canonical emit order for modifiers.
  - to_gnome_accelerator: Convert one friendly spec to a GTK accelerator.
  - normalize_accelerator: Reduce any spec to a comparable (modifiers, key) pair.
  - main: CLI entrypoint used by install.sh.

Usage:
  python3 lib/accelerator.py alt+super+w   # prints: <Alt><Super>w
"""

from __future__ import annotations

import re
import sys

from log_utils import get_logger, log_call

LOGGER = get_logger("accelerator", "accelerator.log")

# Accepted spellings for each modifier, mapped to the canonical GTK keyword that
# appears inside angle brackets. Comparison is case-insensitive.
MODIFIER_ALIASES = {
    "ctrl": "Control",
    "control": "Control",
    "alt": "Alt",
    "meta": "Alt",
    "super": "Super",
    "win": "Super",
    "windows": "Super",
    "cmd": "Super",
    "shift": "Shift",
}

# Emit modifiers in a stable canonical order regardless of input order so the
# resulting accelerator is deterministic and matches GNOME's own conventions.
MODIFIER_ORDER = ["Control", "Alt", "Super", "Shift"]


@log_call(LOGGER)
def to_gnome_accelerator(spec: str) -> str:
    """Convert a friendly ``modifier+key`` spec to a GTK accelerator string.

    The final ``+``-separated token is treated as the key; every preceding
    token must be a recognized modifier. Modifiers are de-duplicated and emitted
    in canonical order. The key token is preserved verbatim, which lets callers
    pass named keys (``Print``, ``space``) or letters as typed.

    Args:
        spec: Friendly hotkey such as ``"control+t"`` or ``"alt+super+w"``.

    Returns:
        The canonical GTK accelerator, e.g. ``"<Control>t"`` or
        ``"<Alt><Super>w"``.

    Raises:
        ValueError: When the spec is empty, has no key token, or names an
            unknown modifier.
    """
    raw = (spec or "").strip()
    if not raw:
        raise ValueError("empty hotkey specification")

    # Keep empty segments so a trailing/double "+" (e.g. "control+", "alt++t")
    # is rejected rather than silently reinterpreted.
    tokens = [part.strip() for part in raw.split("+")]
    if any(not token for token in tokens):
        raise ValueError(f"malformed hotkey {spec!r}: empty modifier or key")

    *modifier_tokens, key = tokens
    if not key:
        raise ValueError(f"hotkey {spec!r} has no key")

    seen: set[str] = set()
    for token in modifier_tokens:
        canonical = MODIFIER_ALIASES.get(token.lower())
        if canonical is None:
            raise ValueError(f"unknown modifier {token!r} in hotkey {spec!r}")
        seen.add(canonical)

    prefix = "".join(f"<{name}>" for name in MODIFIER_ORDER if name in seen)
    accelerator = f"{prefix}{key}"
    LOGGER.debug("converted hotkey %r -> %r", spec, accelerator)
    return accelerator


# Matches a single ``<Modifier>`` token at the start of a GTK accelerator.
_GTK_MODIFIER_RE = re.compile(r"<([^>]+)>")


def normalize_accelerator(text: str) -> tuple[frozenset[str], str]:
    """Reduce any accelerator spec to a comparable (modifiers, key) pair.

    Accepts both the friendly ``modifier+key`` form and the GTK
    ``<Modifier>key`` form so a user-chosen hotkey can be compared against the
    accelerators GNOME already stores, regardless of modifier ordering or key
    casing. Modifiers collapse to their canonical names and the key is
    lower-cased, which makes ``<Super><Alt>e`` and ``alt+super+E`` compare equal.

    Args:
        text: A friendly or GTK accelerator string.

    Returns:
        A tuple of the canonical modifier set and the lower-cased key.

    Raises:
        ValueError: When the spec is empty, has no key, or names an unknown
            modifier.
    """
    value = (text or "").strip()
    if not value:
        raise ValueError("empty accelerator")

    modifiers: set[str] = set()
    if "<" in value:
        for token in _GTK_MODIFIER_RE.findall(value):
            canonical = MODIFIER_ALIASES.get(token.lower())
            if canonical is None:
                raise ValueError(f"unknown modifier {token!r} in accelerator {text!r}")
            modifiers.add(canonical)
        key = _GTK_MODIFIER_RE.sub("", value)
    else:
        parts = [part.strip() for part in value.split("+") if part.strip()]
        if not parts:
            raise ValueError(f"accelerator {text!r} has no key")
        *modifier_tokens, key = parts
        for token in modifier_tokens:
            canonical = MODIFIER_ALIASES.get(token.lower())
            if canonical is None:
                raise ValueError(f"unknown modifier {token!r} in accelerator {text!r}")
            modifiers.add(canonical)

    if not key:
        raise ValueError(f"accelerator {text!r} has no key")
    return frozenset(modifiers), key.lower()


@log_call(LOGGER)
def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by ``install.sh``.

    Converts a single friendly hotkey spec passed as the only argument and
    prints the canonical GTK accelerator to stdout. Diagnostics go to ``.log/``
    only so stdout stays consumable by ``gsettings set``.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``). Must be a
            single friendly hotkey spec.

    Returns:
        Process exit code: 0 on success, 2 on invalid usage or an unparsable
        specification.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        LOGGER.error("invalid accelerator usage: %r", args)
        print("Usage: accelerator.py <modifier+...+key>", file=sys.stderr)
        return 2

    try:
        print(to_gnome_accelerator(args[0]))
    except ValueError as error:
        LOGGER.error("could not convert hotkey: %s", error)
        print(f"Invalid hotkey: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

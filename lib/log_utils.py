"""log_utils.py - centralized file logger for installer-side Python helpers.

Provides a single configured ``logging.Logger`` that writes timestamped,
leveled records to the repository's ``.log/`` directory. install.sh captures
the helpers' *stdout* (the computed gsettings array), so logging must never
touch stdout; every record goes to a file instead. Logging is best-effort: if
the ``.log/`` directory cannot be created (e.g. a read-only checkout), the
logger silently degrades to a no-op handler rather than breaking the install.

Components:
  - LOG_DIR: Path to the repository-root ``.log/`` directory.
  - get_logger: Return a process-wide singleton logger writing to ``.log/``.

Usage:
  from log_utils import get_logger
  log = get_logger()
  log.debug("append %r to current array", value)
"""

from __future__ import annotations

import logging
from pathlib import Path

# Repository root is one level above this lib/ directory; logs are centralized
# under <repo>/.log/ per the project logging policy (never the repo root, /tmp,
# or scattered folders).
REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / ".log"
LOG_FILE = LOG_DIR / "gsettings_strv.log"

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Module-level cache so repeated get_logger() calls reuse one configured logger
# and do not stack duplicate handlers (which would multiply every log line).
_logger: logging.Logger | None = None


def get_logger(name: str = "gsettings_strv") -> logging.Logger:
    """Return the shared file logger, configuring it on first use.

    The logger writes DEBUG and higher to ``LOG_FILE``. Configuration happens
    exactly once per process; later calls return the same instance. If the
    ``.log/`` directory cannot be created, the logger is attached to a
    ``NullHandler`` so callers can log unconditionally without raising.

    Args:
        name: Logger name recorded in each line; defaults to "gsettings_strv".

    Returns:
        A ``logging.Logger`` configured to write to ``.log/`` (or a silent
        no-op logger when the log directory is unavailable).
    """
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    # Never propagate to the root logger: that could surface records on stderr
    # or stdout and corrupt the array install.sh reads from this process.
    logger.propagate = False
    # logging keeps named loggers in a global registry that outlives this
    # module, so drop any handler a previous configuration attached to guarantee
    # exactly one handler (no duplicated log lines).
    for existing in list(logger.handlers):
        logger.removeHandler(existing)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    except OSError:
        # Read-only or otherwise unwritable checkout: degrade to a no-op handler
        # so logging calls stay safe rather than aborting the install.
        handler = logging.NullHandler()

    logger.addHandler(handler)
    _logger = logger
    return logger

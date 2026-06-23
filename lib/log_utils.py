"""log_utils.py - centralized file logger for installer-side Python helpers.

Provides the project's single configured Python ``logging.Logger`` plus the
standard ``log_call`` decorator. install.sh captures the helpers' *stdout* (the
computed gsettings array), so logging must never touch stdout; every record goes
to a file instead. Logging is best-effort: if the ``.log/`` directory cannot be
created, the logger silently degrades to a no-op handler rather than breaking
the install.

Components:
  - LOG_DIR: Path to the repository-root ``.log/`` directory.
  - get_logger: Return an idempotent logger writing to ``.log/``.
  - log_call: Decorator that logs every argument on entry and the return value
    on exit, with ``file:function`` in each record.

Usage:
  from log_utils import get_logger, log_call
  LOGGER = get_logger("gsettings_strv", "gsettings_strv.log")

  @log_call(LOGGER)
  def main(argv=None): ...
"""

from __future__ import annotations

import functools
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

# Repository root is one level above this lib/ directory; logs are centralized
# under <repo>/.log/ per the project logging policy (never the repo root, /tmp,
# or scattered folders).
REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / ".log"

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
F = TypeVar("F", bound=Callable[..., Any])


def get_logger(name: str, log_file: str) -> logging.Logger:
    """Return an idempotent project logger writing under repository ``.log/``.

    The logger writes DEBUG and higher to the requested file. If the ``.log/``
    directory cannot be created, the logger is attached to a ``NullHandler`` so
    callers can log unconditionally without raising or polluting stdout/stderr.

    Args:
        name: Logger name recorded in each line.
        log_file: File name inside the repository ``.log/`` directory.

    Returns:
        A ``logging.Logger`` configured to write to ``.log/`` (or a silent
        no-op logger when the log directory is unavailable).
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    # Never propagate to the root logger: that could surface records on stderr
    # or stdout and corrupt the array install.sh reads from this process.
    logger.propagate = False
    if logger.handlers:
        return logger

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(LOG_DIR / log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
    except OSError:
        # Read-only or otherwise unwritable checkout: degrade to a no-op handler
        # so logging calls stay safe rather than aborting the install.
        handler = logging.NullHandler()

    logger.addHandler(handler)
    return logger


def log_call(logger: logging.Logger, level: int = logging.DEBUG) -> Callable[[F], F]:
    """Trace a function by logging every argument on entry and return on exit.

    Each record carries the wrapped function's ``file:qualname`` so logs are
    searchable without manual context strings. The decorator logs no timing or
    intermediate state.

    Args:
        logger: Centralized logger obtained from ``get_logger``.
        level: Logging level for the enter and exit records.

    Returns:
        A decorator that wraps the target callable.
    """

    def decorator(func: F) -> F:
        location = f"{Path(func.__code__.co_filename).name}:{func.__qualname__}"
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            rendered = ", ".join(
                f"{name}={value!r}" for name, value in bound.arguments.items()
            )
            logger.log(level, "ENTER %s(%s)", location, rendered)
            result = func(*args, **kwargs)
            logger.log(level, "EXIT %s -> %r", location, result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator

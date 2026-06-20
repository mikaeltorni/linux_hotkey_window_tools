"""Tests for the centralized installer-side file logger (lib/log_utils.py)."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "log_utils.py"


def load_module():
    """Load lib/log_utils.py in isolation so each test gets a fresh module."""
    spec = importlib.util.spec_from_file_location("log_utils", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_get_logger_writes_records_to_repo_log_dir():
    mod = load_module()
    log = mod.get_logger()

    log.info("unit-test marker line")
    for handler in log.handlers:
        handler.flush()

    assert mod.LOG_DIR.name == ".log"
    assert mod.LOG_DIR.parent == ROOT
    assert mod.LOG_FILE.exists()
    assert "unit-test marker line" in mod.LOG_FILE.read_text(encoding="utf-8")


def test_get_logger_is_singleton_without_duplicate_handlers():
    mod = load_module()

    first = mod.get_logger()
    second = mod.get_logger()

    assert first is second
    assert len(first.handlers) == 1


def test_get_logger_does_not_propagate_to_root(capsys):
    mod = load_module()
    log = mod.get_logger()

    log.error("must not reach stdout or stderr")

    captured = capsys.readouterr()
    assert log.propagate is False
    assert captured.out == ""
    assert captured.err == ""


def test_get_logger_degrades_when_log_dir_unavailable(monkeypatch, tmp_path):
    mod = load_module()

    # Force mkdir to fail so the logger must fall back to a no-op handler.
    def _raise(*_args, **_kwargs):
        raise OSError("read-only checkout")

    monkeypatch.setattr(mod.Path, "mkdir", _raise)
    log = mod.get_logger()

    assert len(log.handlers) == 1
    assert isinstance(log.handlers[0], logging.NullHandler)
    # Logging through the no-op handler must not raise.
    log.warning("safe even without a writable log dir")

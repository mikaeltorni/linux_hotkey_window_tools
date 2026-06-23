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
    log = mod.get_logger("unit_test_log_utils", "unit-test.log")

    log.info("unit-test marker line")
    for handler in log.handlers:
        handler.flush()

    assert mod.LOG_DIR.name == ".log"
    assert mod.LOG_DIR.parent == ROOT
    log_file = mod.LOG_DIR / "unit-test.log"
    assert log_file.exists()
    assert "unit-test marker line" in log_file.read_text(encoding="utf-8")


def test_get_logger_is_singleton_without_duplicate_handlers():
    mod = load_module()

    first = mod.get_logger("unit_test_singleton", "unit-singleton.log")
    second = mod.get_logger("unit_test_singleton", "unit-singleton.log")

    assert first is second
    assert len(first.handlers) == 1


def test_get_logger_does_not_propagate_to_root(capsys):
    mod = load_module()
    log = mod.get_logger("unit_test_no_propagate", "unit-no-propagate.log")

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
    log = mod.get_logger("unit_test_null", "unit-null.log")

    assert len(log.handlers) == 1
    assert isinstance(log.handlers[0], logging.NullHandler)
    # Logging through the no-op handler must not raise.
    log.warning("safe even without a writable log dir")


def test_log_call_records_arguments_and_return_value():
    mod = load_module()
    log = mod.get_logger("unit_test_trace", "unit-trace.log")

    @mod.log_call(log)
    def sample(value, suffix="x"):
        return f"{value}-{suffix}"

    assert sample("alpha", suffix="beta") == "alpha-beta"
    for handler in log.handlers:
        handler.flush()

    text = (mod.LOG_DIR / "unit-trace.log").read_text(encoding="utf-8")
    assert "ENTER test_log_utils.py:" in text
    assert "sample(value='alpha', suffix='beta')" in text
    assert "EXIT test_log_utils.py:" in text
    assert "sample -> 'alpha-beta'" in text

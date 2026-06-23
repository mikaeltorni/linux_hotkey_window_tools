"""Static checks for installer-side centralized bash logging."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
BASH_LOGGER = ROOT / "lib" / "bash_logging.sh"


def test_install_script_sources_centralized_bash_logger():
    source = INSTALL.read_text(encoding="utf-8")

    assert 'source "$SCRIPT_DIR/lib/bash_logging.sh"' in source
    assert "install_log_info" in source
    assert "install_log_error" in source


def test_bash_logger_writes_under_repo_log_directory():
    source = BASH_LOGGER.read_text(encoding="utf-8")

    assert 'INSTALL_LOG_DIR="${INSTALL_LOG_DIR:-$SCRIPT_DIR/.log}"' in source
    assert 'INSTALL_LOG_FILE="${INSTALL_LOG_FILE:-$INSTALL_LOG_DIR/install.log}"' in source
    assert ">>\"$INSTALL_LOG_FILE\"" in source

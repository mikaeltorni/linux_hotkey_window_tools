"""pytest configuration shared by the lib/ helper tests.

Adds the repository ``lib/`` directory to ``sys.path`` so modules that import
their siblings by bare name (e.g. ``gsettings_strv`` importing ``log_utils``)
resolve the same way they do at runtime, where install.sh runs the script with
``lib/`` as ``sys.path[0]``.
"""

from __future__ import annotations

import sys
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

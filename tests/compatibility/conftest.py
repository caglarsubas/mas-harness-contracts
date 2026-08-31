"""Keep the packet-scoped no-sync test process on the checked-out source tree."""

from __future__ import annotations

import sys
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE))

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # tools/ lives at the repo root, outside the installed package
    sys.path.insert(0, str(ROOT))

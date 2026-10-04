"""Flashing menu for the ESP32 modules. Run from the project folder: python scripts/flash.py

Needs only Python 3.9+ (no .venv). It creates its own tool environment in .flash-env/ on first use,
after asking. See docs/flashing.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flash_tool.cli import main

if __name__ == "__main__":
    sys.exit(main())

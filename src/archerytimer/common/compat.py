"""Small Python-version shims."""

from __future__ import annotations

import sys
from typing import Any

# ``dataclass(slots=True)`` needs Python 3.10+. Use ``@dataclass(frozen=True, **SLOTS)``
# so that state, event and message classes get slots where the interpreter supports it.
SLOTS: dict[str, Any] = {"slots": True} if sys.version_info >= (3, 10) else {}

"""Per-user UI preferences and the last used setup, kept as JSON in the user data dir.

Display settings only; they never affect the core. A missing or damaged file means defaults.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("archerytimer.ui.prefs")

FILE_NAME = "ui_prefs.json"
FPS_CHOICES = (15, 30, 60)
IDLE_DELAYS_MIN = (1, 5, 10, 30)
IDLE_STYLES = ("clock", "dim", "black")
ECO_FPS = 15


@dataclass
class Prefs:
    lang: Optional[str] = None
    tenths: Optional[bool] = None
    fps_cap: Optional[int] = None
    eco: bool = False
    idle_screen: bool = True
    idle_delay_min: int = 5
    idle_style: str = "clock"  # clock | dim | black
    last_setup: Optional[dict[str, Any]] = field(default=None)
    # Default timing for new sessions: prep_s / shoot_s / warn_s, each None = the sequence's own.
    timing: Optional[dict[str, Optional[float]]] = field(default=None)


def _timing(raw: Any) -> Optional[dict[str, Optional[float]]]:
    if not isinstance(raw, dict):
        return None
    out: dict[str, Optional[float]] = {}
    for key in ("prep_s", "shoot_s", "warn_s"):
        v = raw.get(key)
        out[key] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return out if any(v is not None for v in out.values()) else None


class PrefsStore:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path
        self.prefs = Prefs()

    def load(self) -> Prefs:
        if self.path is None or not self.path.exists():
            return self.prefs
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.prefs = Prefs(
                lang=data["lang"] if data.get("lang") in ("sv", "en") else None,
                tenths=data["tenths"] if isinstance(data.get("tenths"), bool) else None,
                fps_cap=data["fps_cap"] if data.get("fps_cap") in FPS_CHOICES else None,
                eco=bool(data.get("eco", False)),
                idle_screen=bool(data.get("idle_screen", True)),
                idle_delay_min=data["idle_delay_min"]
                if data.get("idle_delay_min") in IDLE_DELAYS_MIN
                else 5,
                idle_style=data["idle_style"] if data.get("idle_style") in IDLE_STYLES else "clock",
                last_setup=data["last_setup"] if isinstance(data.get("last_setup"), dict) else None,
                timing=_timing(data.get("timing")),
            )
        except (OSError, ValueError, AttributeError, KeyError) as exc:
            log.warning("ignoring damaged preferences %s: %r", self.path, exc)
        return self.prefs

    def save(self) -> None:
        if self.path is None:
            return
        p = self.prefs
        data = {
            "lang": p.lang,
            "tenths": p.tenths,
            "fps_cap": p.fps_cap,
            "eco": p.eco,
            "idle_screen": p.idle_screen,
            "idle_delay_min": p.idle_delay_min,
            "idle_style": p.idle_style,
            "last_setup": p.last_setup,
            "timing": p.timing,
        }
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            tmp.replace(self.path)  # atomic: a power cut never leaves half a file
        except OSError as exc:
            log.warning("cannot save preferences: %s", exc)

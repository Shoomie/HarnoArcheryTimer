"""Sound settings of one core: which outputs are on, volume, output device.

Kept by the core (not the UI) and saved as JSON in the per-user data dir, so a device keeps
its sound setup across restarts and whichever UI is attached.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("archerytimer.audio")

FILE_NAME = "core_audio.json"


@dataclass(frozen=True)
class AudioSettings:
    local: bool = True  # speakers on this machine (audio worker)
    mcu: bool = True  # horn / buzzer on the microcontroller ($S / $B)
    volume: float = 0.8  # local output, 0.0-1.0
    device: str = ""  # local output device name; "" = system default

    def updated(self, values: Mapping[str, Any]) -> AudioSettings:
        """Apply UI ``settings`` values (``sound_local``, ``sound_mcu``, ``volume``,
        ``audio_device``); anything invalid is ignored."""
        changes: dict[str, Any] = {}
        if isinstance(values.get("sound_local"), bool):
            changes["local"] = values["sound_local"]
        if isinstance(values.get("sound_mcu"), bool):
            changes["mcu"] = values["sound_mcu"]
        vol = values.get("volume")
        if isinstance(vol, (int, float)) and not isinstance(vol, bool):
            changes["volume"] = max(0.0, min(1.0, float(vol)))
        if isinstance(values.get("audio_device"), str):
            changes["device"] = values["audio_device"]
        return replace(self, **changes)


SETTING_KEYS = frozenset({"sound_local", "sound_mcu", "volume", "audio_device"})


def from_table(table: Mapping[str, Any]) -> AudioSettings:
    """Defaults from the ``[audio]`` table of the settings TOML."""
    return AudioSettings().updated(
        {
            "sound_local": table.get("local"),
            "sound_mcu": table.get("mcu"),
            "volume": table.get("volume"),
            "audio_device": table.get("device"),
        }
    )


class AudioSettingsStore:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path

    def load(self, default: AudioSettings) -> AudioSettings:
        if self.path is None or not self.path.exists():
            return default
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return default.updated(
                {
                    "sound_local": data.get("local"),
                    "sound_mcu": data.get("mcu"),
                    "volume": data.get("volume"),
                    "audio_device": data.get("device"),
                }
            )
        except (OSError, ValueError, AttributeError) as exc:
            log.warning("ignoring damaged audio settings %s: %r", self.path, exc)
            return default

    def save(self, settings: AudioSettings) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(settings), indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("cannot save audio settings: %s", exc)

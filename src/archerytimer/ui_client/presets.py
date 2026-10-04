"""Presets (setup cards) from TOML: bundled ones plus the club's own in the user data dir."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib  # type: ignore[no-redef]

log = logging.getLogger("archerytimer.ui.presets")

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "config" / "presets"
# Rotation options offered on step 2 unless a preset lists its own.
DEFAULT_LINE_OPTIONS: tuple[tuple[str, ...], ...] = (
    ("AB",),
    ("AB", "CD"),
    ("A", "B", "C"),
    ("A", "B", "C", "D"),
)
OPEN_ENDED = 99  # shown as "End 3" instead of "End 3 of 99"


@dataclass(frozen=True)
class Preset:
    id: str
    name: Mapping[str, str]
    sequence: str
    groups: tuple[str, ...]
    ends: int
    practice_ends: int
    open_ended: bool = False
    line_options: tuple[tuple[str, ...], ...] = DEFAULT_LINE_OPTIONS


def _parse(pid: str, body: Mapping[str, Any]) -> Preset:
    groups = tuple(str(g) for g in body["groups"])
    options = tuple(tuple(str(g) for g in o) for o in body.get("line_options", ()))
    options = options or DEFAULT_LINE_OPTIONS
    if groups not in options:
        options = (groups, *options)
    return Preset(
        id=pid,
        name=dict(body.get("name", {})),
        sequence=str(body["sequence"]),
        groups=groups,
        ends=int(body.get("ends", 1)),
        practice_ends=int(body.get("practice_ends", 0)),
        open_ended=bool(body.get("open_ended", False)),
        line_options=options,
    )


def load_presets(*directories: Path) -> list[Preset]:
    """Every ``*.toml`` in the directories, in file then definition order. Bad entries are
    skipped with a warning so one typo in a club file never blocks the setup screen."""
    presets: dict[str, Preset] = {}
    for directory in directories or (DEFAULT_DIR,):
        for path in sorted(directory.glob("*.toml")) if directory.is_dir() else []:
            try:
                with path.open("rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, ValueError) as exc:
                log.warning("cannot read presets %s: %s", path, exc)
                continue
            for pid, body in data.get("preset", {}).items():
                try:
                    presets[pid] = _parse(pid, body)
                except (KeyError, TypeError, ValueError) as exc:
                    log.warning("bad preset %r in %s: %r", pid, path.name, exc)
    return list(presets.values())


def find(presets: list[Preset], pid: str) -> Optional[Preset]:
    return next((p for p in presets if p.id == pid), None)


@dataclass(frozen=True)
class TimingPreset:
    """Quick-pick timer lengths for the Timers screen (all values in seconds)."""

    id: str
    name: Mapping[str, str]
    prep_s: float
    shoot_s: float
    warn_s: float


def load_timings(*directories: Path) -> list[TimingPreset]:
    out: dict[str, TimingPreset] = {}
    for directory in directories or (DEFAULT_DIR,):
        for path in sorted(directory.glob("*.toml")) if directory.is_dir() else []:
            try:
                with path.open("rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, ValueError) as exc:
                log.warning("cannot read timings %s: %s", path, exc)
                continue
            for tid, body in data.get("timing", {}).items():
                try:
                    out[tid] = TimingPreset(
                        tid,
                        dict(body.get("name", {})),
                        float(body["prep_s"]),
                        float(body["shoot_s"]),
                        float(body["warn_s"]),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    log.warning("bad timing %r in %s: %r", tid, path.name, exc)
    return list(out.values())

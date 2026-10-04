"""Immutable data model: rules, session config, events and state snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, Union

from archerytimer.common.compat import SLOTS


class Light(str, Enum):
    """Light state. Values are the serial protocol letters."""

    OFF = "O"
    GREEN = "G"
    YELLOW = "Y"
    RED = "R"


class Mode(str, Enum):
    IDLE = "idle"  # no round yet / after reset
    RUNNING = "running"  # inside a phase of a round
    WAITING = "waiting"  # between rounds, next round is ready
    FINISHED = "finished"  # all ends done


@dataclass(frozen=True, **SLOTS)
class PhaseSpec:
    id: str
    duration_ns: int
    light: Light
    whistle_on_start: int = 0
    warn_at_ns: Union[int, None] = None  # remaining time at which the warning light starts
    warn_light: Light = Light.YELLOW


@dataclass(frozen=True, **SLOTS)
class Sequence:
    id: str
    name: Mapping[str, str]
    phases: Tuple[PhaseSpec, ...]


@dataclass(frozen=True, **SLOTS)
class SessionConfig:
    sequence_id: str
    groups: Tuple[str, ...] = ("AB",)
    total_ends: int = 1
    practice_ends: int = 0
    alternate_order: bool = True  # rotate which group shoots first on each end
    auto_advance: bool = False
    auto_advance_delay_ns: int = 5_000_000_000
    # Per-session overrides of the sequence's PREP / SHOOT durations and the SHOOT warning
    # threshold (None = keep the sequence's value; warn_ns == 0 switches the warning off).
    prep_ns: Union[int, None] = None
    shoot_ns: Union[int, None] = None
    warn_ns: Union[int, None] = None


@dataclass(frozen=True, **SLOTS)
class EngineSettings:
    emergency_blasts: int = 5
    blast_ms: int = 500
    gap_ms: int = 500
    # "mcu": one Whistle event, the device times the blasts ($S).
    # "host": the engine schedules each Buzzer on/off event ($B).
    whistle_timing: str = "mcu"
    pause_light: Light = Light.RED
    late_threshold_ns: int = 2_000_000


# --- Events emitted to the outside world, in order: hardware/audio first, then state. ---


@dataclass(frozen=True, **SLOTS)
class LightChange:
    light: Light


@dataclass(frozen=True, **SLOTS)
class Whistle:
    """``count`` blasts, timed by the receiver. ``count == 0`` means silence now."""

    count: int
    blast_ms: int
    gap_ms: int


@dataclass(frozen=True, **SLOTS)
class Buzzer:
    on: bool


@dataclass(frozen=True, **SLOTS)
class Snapshot:
    seq: int
    mode: Mode
    sequence_id: str
    phase_id: str
    phase_start_ns: int
    deadline_ns: int
    paused: bool
    remaining_at_pause_ns: int
    light: Light
    group: str
    end_no: int
    total_ends: int
    practice: bool
    round_index: int
    total_rounds: int
    emergency: bool
    link: str
    planned_ns: int = 0  # longest phase of the session's sequence (shown while waiting)


Event = Union[LightChange, Whistle, Buzzer, Snapshot]


@dataclass(frozen=True, **SLOTS)
class Command:
    name: str
    args: Mapping[str, object] = field(default_factory=dict)

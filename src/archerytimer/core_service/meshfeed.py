"""What a leader core tells its MCU for the radio: timer state (``$U``) and session (``$J``).

Pure functions from engine objects to the typed serial v2 frames (``docs/mesh.md`` TIMER and SESSION
fields). The serial worker repeats them and subtracts elapsed time; nothing here reads a clock.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Optional

from archerytimer.common.clock import NS_PER_MS
from archerytimer.core.models import Mode, Sequence, SessionConfig, Snapshot
from archerytimer.hardware.mesh_types import (
    FLAG_EMERGENCY,
    FLAG_PAUSED,
    KEEP,
    MODES,
    SessionInfo,
    TimerState,
)

_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def master_id_from(node_id: str) -> int:
    """Stable non-zero 32-bit radio identity of a core, derived from its node id."""
    value = int.from_bytes(hashlib.sha256(node_id.encode()).digest()[:4], "little")
    return value or 1


def radio_name(name: str) -> str:
    """A device name as the MCU accepts it (1-12 of ``A-Za-z0-9_-``)."""
    clean = _ID_RE.sub("-", name)[:12].strip("-")
    return clean or "timer"


def _ms(ns: Optional[int]) -> int:
    return KEEP if ns is None else min(KEEP - 1, max(0, ns // NS_PER_MS))


def session_info(config: SessionConfig, rev: int) -> SessionInfo:
    """``warn_ns == 0`` (warning off) stays 0; ``None`` keeps the sequence's own value."""
    return SessionInfo(
        rev=rev % 256,
        alternate_order=config.alternate_order,
        auto_advance=config.auto_advance,
        total_ends=min(255, config.total_ends),
        practice_ends=min(255, config.practice_ends),
        prep_ms=_ms(config.prep_ns),
        shoot_ms=_ms(config.shoot_ns),
        warn_ms=_ms(config.warn_ns),
        auto_delay_ms=_ms(config.auto_advance_delay_ns),
        sequence_id=_ID_RE.sub("-", config.sequence_id)[:16] or "seq",
        groups=tuple(config.groups[:8]),
    )


def timer_state(
    snap: Snapshot,
    sequences: Mapping[str, Sequence],
    groups: tuple[str, ...],
    rev: int,
    now_ns: int,
) -> TimerState:
    """``remaining_ms`` is valid at ``now_ns``: time left while running, the frozen time while
    paused or in an emergency, 0 otherwise."""
    seq = sequences.get(snap.sequence_id)
    phase = 0
    if seq is not None:
        for i, spec in enumerate(seq.phases):
            if spec.id == snap.phase_id:
                phase = i
                break
    if snap.mode is Mode.RUNNING:
        frozen = snap.paused or snap.emergency
        remaining = snap.remaining_at_pause_ns if frozen else snap.deadline_ns - now_ns
    else:
        remaining = 0  # followers derive the planned length from the session's sequence
    group = groups.index(snap.group) if snap.group in groups else 0
    flags = (FLAG_PAUSED if snap.paused else 0) | (FLAG_EMERGENCY if snap.emergency else 0)
    return TimerState(
        mode=MODES.index(snap.mode.value),
        phase=min(255, phase),
        remaining_ms=_ms(remaining),
        end_no=min(255, snap.end_no),
        total_ends=min(255, snap.total_ends),
        group=min(255, group),
        round=min(255, snap.round_index),
        total_rounds=min(255, snap.total_rounds),
        flags=flags,
        rev=rev % 256,
    )

"""Shared types of the mesh v2 contract (``docs/mesh.md``, ``docs/protocol.md`` serial v2).

Contains the typed serial v2
frames (parsing and encoding of the ``$`` lines belong to ``protocol.py``) and the radio payload
dataclasses with their exact byte layout (``to_bytes`` / ``from_bytes``). Header, tag, HMAC are the
frame codec in ``mesh_codec.py``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from archerytimer.common.compat import SLOTS

KEEP = 0xFFFF_FFFF  # SESSION time fields: keep the sequence's own value
NO_SOUND_AGE = 0xFFFF

# Mesh roles the host declares with ``$R`` and the roles reported by ``$O``.
ROLE_MASTER, ROLE_MIRROR, ROLE_RADIO_FED, ROLE_NONE = "M", "F", "E", "N"
ROLES = (ROLE_MASTER, ROLE_MIRROR, ROLE_RADIO_FED, ROLE_NONE)

# Remote action codes (CMD frame, ``$P,tx`` / ``$P,cmd``) and the engine command each stands for.
ACTIONS = {
    1: "primary",
    2: "pause",
    3: "resume",
    4: "stop_end",
    5: "next",
    6: "back",
    7: "emergency",
}
ACTION_CODES = {name: code for code, name in ACTIONS.items()}
EMERGENCY_ACTION = 7
EMERGENCY_MASK_BIT = 1 << (EMERGENCY_ACTION - 1)

# TIMER ``flags`` bits and ``mode`` codes.
FLAG_PAUSED, FLAG_EMERGENCY, FLAG_BUZZER = 1, 2, 4
MODES = ("idle", "running", "waiting", "finished")

# Config keys of ``$C``.
CONFIG_BOOL_KEYS = ("lights", "sound", "radio", "remote")
CONFIG_KEYS = ("name", *CONFIG_BOOL_KEYS, "chan", "mkey", "btn1", "btn2", "btn3", "btn4")

# Roster kinds of ``$D``.
KIND_NODE, KIND_REMOTE, KIND_MASTER, KIND_MIRROR, KIND_RADIO_FED = "N", "R", "M", "F", "E"


def mask_allows(mask: int, action: int) -> bool:
    """Emergency is always allowed for a paired remote; other actions need their mask bit."""
    return action == EMERGENCY_ACTION or bool(mask & (1 << (action - 1)))


# --- radio payloads (docs/mesh.md section 2) -----------------------------------------------

_TIMER = struct.Struct("<IIBBBBBIBBBBBBBBBBH")  # 29 bytes (session after master_id)
_SOUND = struct.Struct("<IIBBBB")  # 12 bytes (session after master_id)


@dataclass(frozen=True, **SLOTS)
class RadioTimer:
    master_id: int
    rank: int
    lights: int  # G=1 Y=2 R=4
    flags: int
    mode: int
    phase: int
    remaining_ms: int
    end_no: int
    total_ends: int
    group: int
    round: int
    total_rounds: int
    session_rev: int
    sound_seq: int
    sound_count: int
    sound_blast: int  # x10 ms
    sound_gap: int  # x10 ms
    sound_age: int = NO_SOUND_AGE
    session: int = 1  # master's persisted session counter (wire order: after master_id)

    def to_bytes(self) -> bytes:
        return _TIMER.pack(
            self.master_id, self.session, self.rank, self.lights, self.flags, self.mode, self.phase,
            self.remaining_ms, self.end_no, self.total_ends, self.group, self.round,
            self.total_rounds, self.session_rev, self.sound_seq, self.sound_count,
            self.sound_blast, self.sound_gap, self.sound_age,
        )  # fmt: skip

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioTimer:
        if len(data) != _TIMER.size:
            raise ValueError(f"TIMER payload must be {_TIMER.size} bytes, got {len(data)}")
        (
            mid, session, rank, lights, flags, mode, phase, remaining, end_no, total_ends,
            group, rnd, total_rounds, rev, sseq, scount, sblast, sgap, sage,
        ) = _TIMER.unpack(data)  # fmt: skip
        return cls(
            mid, rank, lights, flags, mode, phase, remaining, end_no, total_ends, group, rnd,
            total_rounds, rev, sseq, scount, sblast, sgap, sage, session=session,
        )  # fmt: skip


@dataclass(frozen=True, **SLOTS)
class RadioSound:
    master_id: int
    sound_seq: int
    count: int
    blast: int  # x10 ms
    gap: int  # x10 ms
    session: int = 1

    def to_bytes(self) -> bytes:
        return _SOUND.pack(
            self.master_id, self.session, self.sound_seq, self.count, self.blast, self.gap
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioSound:
        if len(data) != _SOUND.size:
            raise ValueError(f"SOUND payload must be {_SOUND.size} bytes, got {len(data)}")
        (mid, session, seq, count, blast, gap) = _SOUND.unpack(data)
        return cls(mid, seq, count, blast, gap, session=session)


@dataclass(frozen=True, **SLOTS)
class RadioSession:
    master_id: int
    rev: int
    alternate_order: bool
    auto_advance: bool
    total_ends: int
    practice_ends: int
    prep_ms: int  # KEEP = sequence's value
    shoot_ms: int
    warn_ms: int  # KEEP = sequence's value, 0 = warning off
    auto_delay_ms: int
    sequence_id: str
    groups: tuple[str, ...] = field(default_factory=tuple)

    def to_bytes(self) -> bytes:
        seq = self.sequence_id.encode("ascii")
        flags = (1 if self.alternate_order else 0) | (2 if self.auto_advance else 0)
        out = struct.pack(
            "<IBBBBIIII", self.master_id, self.rev, flags, self.total_ends, self.practice_ends,
            self.prep_ms, self.shoot_ms, self.warn_ms, self.auto_delay_ms,
        )  # fmt: skip
        out += bytes([len(seq)]) + seq + bytes([len(self.groups)])
        for g in self.groups:
            out += bytes([len(g)]) + g.encode("ascii")
        return out

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioSession:
        head = struct.Struct("<IBBBBIIII")
        try:
            (mid, rev, flags, ends, pract, prep, shoot, warn, delay) = head.unpack_from(data)
            pos = head.size
            n = data[pos]
            seq = data[pos + 1 : pos + 1 + n].decode("ascii")
            pos += 1 + n
            count = data[pos]
            pos += 1
            groups = []
            for _ in range(count):
                gl = data[pos]
                groups.append(data[pos + 1 : pos + 1 + gl].decode("ascii"))
                pos += 1 + gl
        except (struct.error, IndexError, UnicodeDecodeError) as exc:
            raise ValueError(f"bad SESSION payload: {exc}") from None
        if pos != len(data):
            raise ValueError("trailing bytes in SESSION payload")
        return cls(mid, rev, bool(flags & 1), bool(flags & 2), ends, pract, prep, shoot, warn,
                   delay, seq, tuple(groups))  # fmt: skip


# --- serial v2 frames (typed; parse/encode lives in protocol.py) ---------------------------


@dataclass(frozen=True, **SLOTS)
class Role:
    """``$R,<role>[,<id>,<session>]``"""

    role: str
    master_id: Optional[int] = None
    session: Optional[int] = None


@dataclass(frozen=True, **SLOTS)
class Config:
    """``$C,<key>,<value>`` (both directions: the MCU echoes a stored value)."""

    key: str
    value: str


@dataclass(frozen=True, **SLOTS)
class ConfigQuery:
    """``$Q``"""


@dataclass(frozen=True, **SLOTS)
class TimerState:
    """``$U,...``: timer state for the radio TIMER frame."""

    mode: int
    phase: int
    remaining_ms: int
    end_no: int
    total_ends: int
    group: int
    round: int
    total_rounds: int
    flags: int
    rev: int


@dataclass(frozen=True, **SLOTS)
class SessionInfo:
    """``$J,...`` host to MCU: same content as ``RadioSession`` without the master id."""

    rev: int
    alternate_order: bool
    auto_advance: bool
    total_ends: int
    practice_ends: int
    prep_ms: int
    shoot_ms: int
    warn_ms: int
    auto_delay_ms: int
    sequence_id: str
    groups: tuple[str, ...]


@dataclass(frozen=True, **SLOTS)
class PairOpen:
    seconds: int


@dataclass(frozen=True, **SLOTS)
class PairClose:
    pass


@dataclass(frozen=True, **SLOTS)
class PairAccept:
    mac: str
    mask: int


@dataclass(frozen=True, **SLOTS)
class PairReject:
    mac: str


@dataclass(frozen=True, **SLOTS)
class PairDelete:
    mac: str


@dataclass(frozen=True, **SLOTS)
class PairAck:
    mac: str
    counter: int
    result: int  # 0 done, 1 denied


@dataclass(frozen=True, **SLOTS)
class PairTx:
    action: int


@dataclass(frozen=True, **SLOTS)
class PairRequest:
    """MCU to host: a remote asks to pair."""

    mac: str
    name: str
    caps: str


@dataclass(frozen=True, **SLOTS)
class RemoteCommand:
    """MCU to host: ``$P,cmd,<mac>,<action>,<counter>`` from a paired remote."""

    mac: str
    action: int
    counter: int


@dataclass(frozen=True, **SLOTS)
class PairDone:
    mac: str


@dataclass(frozen=True, **SLOTS)
class PairState:
    open: bool
    seconds_left: int


@dataclass(frozen=True, **SLOTS)
class MeshStatus:
    """``$O,...``"""

    role: str
    src: str  # H host, E radio, N none
    peers: int
    conflict: bool
    master_id: int  # 0 = none
    chan: int


@dataclass(frozen=True, **SLOTS)
class RosterEntry:
    mac: str
    kind: str
    caps: str  # "" when none
    rssi: int  # dBm magnitude
    fw: str
    name: str  # "" when none


@dataclass(frozen=True, **SLOTS)
class RosterGone:
    mac: str


@dataclass(frozen=True, **SLOTS)
class FeedTimer:
    payload: bytes


@dataclass(frozen=True, **SLOTS)
class FeedSound:
    payload: bytes


@dataclass(frozen=True, **SLOTS)
class FeedSession:
    payload: bytes

"""Serial protocol between host and MCU (v1 plus the mesh v2 frames): pure encode/decode functions.

Frame format: ``$<CMD>[,<arg>...]*<XX>\\n`` where ``XX`` is two uppercase hex digits of the
XOR of every byte between ``$`` and ``*``. A whole frame, including the newline, is at most
64 bytes; the long commands ``J F W Y D P`` of serial v2 may reach 160 bytes. See
``docs/protocol.md``, ``firmware/test_vectors.txt`` and ``firmware/test_vectors_v2.txt``.

Nothing here does I/O or reads a clock. ``decode`` raises ``ProtocolError``; ``FrameParser``
turns a raw byte stream into frames and errors without ever raising.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import reduce
from typing import Callable, Optional, Union

from archerytimer.common.compat import SLOTS
from archerytimer.hardware.mesh_types import (
    CONFIG_BOOL_KEYS,
    CONFIG_KEYS,
    ROLE_MASTER,
    ROLE_MIRROR,
    ROLES,
    Config,
    ConfigQuery,
    FeedSession,
    FeedSound,
    FeedTimer,
    MeshStatus,
    PairAccept,
    PairAck,
    PairClose,
    PairDelete,
    PairDone,
    PairOpen,
    PairReject,
    PairRequest,
    PairState,
    PairTx,
    RemoteCommand,
    Role,
    RosterEntry,
    RosterGone,
    SessionInfo,
    TimerState,
)

PROTOCOL_VERSION = 1
PROTOCOL_VERSION_MESH = 2  # devices reporting this (and capability R) speak serial v2
MAX_FRAME_BYTES = 64
MAX_LONG_FRAME_BYTES = 160  # commands in LONG_COMMANDS
LONG_COMMANDS = frozenset("JFWYDP")
_MAX_CONTENT_BYTES = MAX_FRAME_BYTES - 1  # the terminating newline takes one byte

# Error codes. The first four go on the wire in ``$E,<code>``; MF never does.
ERR_CHECKSUM = "CS"
ERR_UNKNOWN_CMD = "UC"
ERR_BAD_ARG = "BA"
ERR_OVERFLOW = "OV"
ERR_MALFORMED = "MF"  # framing garbage: silently discarded, no reply
WIRE_ERROR_CODES = frozenset({ERR_CHECKSUM, ERR_UNKNOWN_CMD, ERR_BAD_ARG, ERR_OVERFLOW})

CAPABILITIES = (
    "LSBGT"  # host commands the reference MCU accepts: lights, sound, buzzer, group, time
)
# K: button events; N: ESP-NOW sync; W: whistle ids ($S,n,id) and timing; R: mesh v2 ($R $C $U ...)
ALLOWED_CAPS = CAPABILITIES + "KNWR"
ROSTER_CAPS = "LSBKR"
ESPNOW_MODES = (0, 1, 2, 3)  # off, bridge, follow, auto
ESPNOW_MODE_NAMES = {"off": 0, "bridge": 1, "follow": 2, "auto": 3}
ESPNOW_SOURCES = ("H", "E", "N")  # active output source: host, ESP-NOW, none

_U32_MAX = 0xFFFF_FFFF
_FRAME_RE = re.compile(rb"\$([\x20-\x7e]*)\*([0-9A-F]{2})")
_GROUP_RE = re.compile(r"[A-Z0-9]{1,8}")
_FW_RE = re.compile(r"[A-Za-z0-9._+\-]{1,16}")
_NAME_RE = re.compile(r"[A-Za-z0-9_\-]{1,12}")
_SEQ_RE = re.compile(r"[A-Za-z0-9_\-]{1,16}")
_SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_JGROUP_RE = re.compile(r"[A-Z0-9]{1,8}")
_MAC_RE = re.compile(r"[0-9A-F]{12}")
_ID_RE = re.compile(r"[0-9A-F]{8}")
_SESSION_RE = re.compile(r"[1-9][0-9]{0,9}")
_MASK_RE = re.compile(r"[0-9A-F]{2}")
_MKEY_RE = re.compile(r"[0-9A-F]{32}")
_HEX_RE = re.compile(r"(?:[0-9A-F]{2})+")
_TIMER_PAYLOAD_BYTES = 29
_SOUND_PAYLOAD_BYTES = 12


class ProtocolError(Exception):
    """A frame could not be encoded or decoded. ``code`` is one of the ``ERR_*`` values."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# --- frames ------------------------------------------------------------------------------


@dataclass(frozen=True, **SLOTS)
class Lights:
    """``$L,<state>``: ``G``/``Y``/``R`` (or a combination such as ``RY``) or ``O`` (off)."""

    state: str


@dataclass(frozen=True, **SLOTS)
class Whistle:
    """``$S,<n>[,<id>[,<blast_ms>,<gap_ms>]]``: play ``n`` blasts with MCU-side timing; 0 = silence.

    ``id`` (1-255) is only sent to devices with capability ``W``: the device ignores a frame
    whose id equals the last one it accepted, so the host can safely repeat it to heal a loss.
    """

    count: int
    id: Optional[int] = None
    blast_ms: Optional[int] = None  # v2: explicit timing (capability W); needs id and gap_ms
    gap_ms: Optional[int] = None


@dataclass(frozen=True, **SLOTS)
class Buzzer:
    """``$B,<0|1>``: raw buzzer or horn on or off, for host-timed sound."""

    on: bool


@dataclass(frozen=True, **SLOTS)
class Group:
    """``$G,<name>``: line-group indicator such as ``AB`` or ``CD``."""

    name: str


@dataclass(frozen=True, **SLOTS)
class Remaining:
    """``$T,<ms>``: remaining milliseconds for an MCU-driven digit display."""

    ms: int


@dataclass(frozen=True, **SLOTS)
class Heartbeat:
    """``$H,<seq>,<lights>,<group>``: full current state; ``group`` is empty when unused."""

    seq: int
    lights: str
    group: str


@dataclass(frozen=True, **SLOTS)
class Hello:
    """``$V``: hello and version request."""


@dataclass(frozen=True, **SLOTS)
class HelloReply:
    """``$I,<proto>,<fw>,<caps>``: protocol version, firmware version, capabilities."""

    proto: int
    fw: str
    caps: str


@dataclass(frozen=True, **SLOTS)
class Ack:
    """``$A,<seq>``: acknowledges the heartbeat with that sequence number."""

    seq: int


@dataclass(frozen=True, **SLOTS)
class Button:
    """``$K,<id>,<0|1>``: MCU to host, button ``id`` (1-99) went down (1) or up (0)."""

    id: int
    down: bool


@dataclass(frozen=True, **SLOTS)
class EspNowMode:
    """``$M,<n>``: host to MCU, set the ESP-NOW role: 0 off, 1 bridge, 2 follow, 3 auto."""

    mode: int


@dataclass(frozen=True, **SLOTS)
class EspNowStatus:
    """``$N,<mode>,<peers>,<src>``: MCU to host. ``src`` is the active output source."""

    mode: int
    peers: int
    src: str


@dataclass(frozen=True, **SLOTS)
class Error:
    """``$E,<code>``: the MCU rejected a frame."""

    code: str


Frame = Union[
    Lights,
    Whistle,
    Buzzer,
    Group,
    Remaining,
    Heartbeat,
    Hello,
    HelloReply,
    Ack,
    Button,
    EspNowMode,
    EspNowStatus,
    Error,
    Role,
    Config,
    ConfigQuery,
    TimerState,
    SessionInfo,
    PairOpen,
    PairClose,
    PairAccept,
    PairReject,
    PairDelete,
    PairAck,
    PairTx,
    PairRequest,
    RemoteCommand,
    PairDone,
    PairState,
    MeshStatus,
    RosterEntry,
    RosterGone,
    FeedTimer,
    FeedSound,
    FeedSession,
]
HOST_FRAME_TYPES = (
    Lights,
    Whistle,
    Buzzer,
    Group,
    Remaining,
    Heartbeat,
    Hello,
    EspNowMode,
    Role,
    Config,
    ConfigQuery,
    TimerState,
    SessionInfo,
    PairOpen,
    PairClose,
    PairAccept,
    PairReject,
    PairDelete,
    PairAck,
    PairTx,
)

# --- argument validation -----------------------------------------------------------------


def _bad(detail: str) -> ProtocolError:
    return ProtocolError(ERR_BAD_ARG, detail)


def _uint(text: str, maximum: int) -> int:
    # Canonical decimal only (no sign, no leading zeros), so frames round-trip exactly.
    if not (text.isascii() and text.isdigit()) or (len(text) > 1 and text[0] == "0"):
        raise _bad(f"not a canonical unsigned integer: {text!r}")
    value = int(text)
    if value > maximum:
        raise _bad(f"{value} exceeds {maximum}")
    return value


def _lights(text: str) -> str:
    if text == "O":
        return text
    if text and set(text) <= set("GYR") and len(set(text)) == len(text):
        return text
    raise _bad(f"invalid light state: {text!r}")


def _group(text: str, allow_empty: bool = False) -> str:
    if (allow_empty and text == "") or _GROUP_RE.fullmatch(text):
        return text
    raise _bad(f"invalid group: {text!r}")


def _caps(text: str) -> str:
    if set(text) <= set(ALLOWED_CAPS) and len(set(text)) == len(text):
        return text
    raise _bad(f"invalid capabilities: {text!r}")


def _args(args: list[str], count: int) -> None:
    if len(args) != count:
        raise _bad(f"expected {count} argument(s), got {len(args)}")


def _p_lights(a: list[str]) -> Frame:
    _args(a, 1)
    return Lights(_lights(a[0]))


def _blast_ms(text: str) -> int:
    value = _uint(text, 2000)
    if value < 10 or value % 10:
        raise _bad(f"blast/gap must be 10-2000 in steps of 10: {value}")
    return value


def _p_whistle(a: list[str]) -> Frame:
    if len(a) not in (1, 2, 4):
        raise _bad(f"expected 1, 2 or 4 argument(s), got {len(a)}")
    ident = None
    if len(a) >= 2:
        ident = _uint(a[1], 255)
        if ident == 0:
            raise _bad("whistle id must be 1-255")
    blast = gap = None
    if len(a) == 4:
        blast, gap = _blast_ms(a[2]), _blast_ms(a[3])
    return Whistle(_uint(a[0], 99), ident, blast, gap)


def _p_buzzer(a: list[str]) -> Frame:
    _args(a, 1)
    if a[0] not in ("0", "1"):
        raise _bad(f"buzzer must be 0 or 1: {a[0]!r}")
    return Buzzer(a[0] == "1")


def _p_group(a: list[str]) -> Frame:
    _args(a, 1)
    return Group(_group(a[0]))


def _p_remaining(a: list[str]) -> Frame:
    _args(a, 1)
    return Remaining(_uint(a[0], _U32_MAX))


def _p_heartbeat(a: list[str]) -> Frame:
    _args(a, 3)
    return Heartbeat(_uint(a[0], _U32_MAX), _lights(a[1]), _group(a[2], allow_empty=True))


def _p_hello(a: list[str]) -> Frame:
    _args(a, 0)
    return Hello()


def _p_hello_reply(a: list[str]) -> Frame:
    _args(a, 3)
    if not _FW_RE.fullmatch(a[1]):
        raise _bad(f"invalid firmware version: {a[1]!r}")
    return HelloReply(_uint(a[0], 255), a[1], _caps(a[2]))


def _p_ack(a: list[str]) -> Frame:
    _args(a, 1)
    return Ack(_uint(a[0], _U32_MAX))


def _p_button(a: list[str]) -> Frame:
    _args(a, 2)
    bid = _uint(a[0], 99)
    if bid < 1 or a[1] not in ("0", "1"):
        raise _bad(f"invalid button frame: {a!r}")
    return Button(bid, a[1] == "1")


def _p_espnow_mode(a: list[str]) -> Frame:
    _args(a, 1)
    mode = _uint(a[0], 3)
    return EspNowMode(mode)


def _p_espnow_status(a: list[str]) -> Frame:
    _args(a, 3)
    mode = _uint(a[0], 3)
    peers = _uint(a[1], 99)
    if a[2] not in ESPNOW_SOURCES:
        raise _bad(f"invalid source: {a[2]!r}")
    return EspNowStatus(mode, peers, a[2])


def _p_error(a: list[str]) -> Frame:
    _args(a, 1)
    if a[0] not in WIRE_ERROR_CODES:
        raise _bad(f"unknown error code: {a[0]!r}")
    return Error(a[0])


# --- serial v2 argument parsers ------------------------------------------------------------


def _hex(text: str, pattern: re.Pattern[str], what: str) -> int:
    if not pattern.fullmatch(text):
        raise _bad(f"invalid {what}: {text!r}")
    return int(text, 16)


def _mac(text: str) -> str:
    if not _MAC_RE.fullmatch(text):
        raise _bad(f"invalid mac: {text!r}")
    return text


def _flag(text: str) -> bool:
    if text not in ("0", "1"):
        raise _bad(f"expected 0 or 1: {text!r}")
    return text == "1"


def _ranged(text: str, low: int, high: int) -> int:
    value = _uint(text, high)
    if value < low:
        raise _bad(f"{value} below {low}")
    return value


def _roster_caps(text: str) -> str:
    if text == "-":
        return ""
    if text and set(text) <= set(ROSTER_CAPS) and len(set(text)) == len(text):
        return text
    raise _bad(f"invalid capabilities: {text!r}")


def _roster_name(text: str) -> str:
    if text == "-":
        return ""
    if _NAME_RE.fullmatch(text):
        return text
    raise _bad(f"invalid name: {text!r}")


def _config_value(key: str, value: str) -> None:
    if key == "name":
        if not _NAME_RE.fullmatch(value):
            raise _bad(f"invalid name: {value!r}")
    elif key in CONFIG_BOOL_KEYS:
        _flag(value)
    elif key == "chan":
        _ranged(value, 1, 13)
    elif key == "mkey":
        if not _MKEY_RE.fullmatch(value):
            raise _bad("mkey must be 32 uppercase hex digits")
    else:  # btn1..btn4
        _uint(value, 7)


def _p_role(a: list[str]) -> Frame:
    if len(a) not in (1, 3) or a[0] not in ROLES:
        raise _bad(f"invalid role frame: {a!r}")
    needs_id = a[0] in (ROLE_MASTER, ROLE_MIRROR)
    if needs_id != (len(a) == 3):
        raise _bad(f"role {a[0]} {'needs id and session' if needs_id else 'takes no id'}")
    if not needs_id:
        return Role(a[0])
    ident = _hex(a[1], _ID_RE, "master id")
    if ident == 0:
        raise _bad("master id must not be 0")
    if not _SESSION_RE.fullmatch(a[2]) or int(a[2]) > _U32_MAX:
        raise _bad("session must be a canonical decimal u32 >= 1")
    return Role(a[0], ident, int(a[2]))


def _p_config(a: list[str]) -> Frame:
    _args(a, 2)
    if a[0] not in CONFIG_KEYS:
        raise _bad(f"unknown config key: {a[0]!r}")
    _config_value(a[0], a[1])
    return Config(a[0], a[1])


def _p_config_query(a: list[str]) -> Frame:
    _args(a, 0)
    return ConfigQuery()


def _p_timer_state(a: list[str]) -> Frame:
    _args(a, 10)
    return TimerState(
        _uint(a[0], 3),
        _uint(a[1], 255),
        _uint(a[2], _U32_MAX),
        _uint(a[3], 255),
        _uint(a[4], 255),
        _uint(a[5], 255),
        _uint(a[6], 255),
        _uint(a[7], 255),
        _uint(a[8], 7),
        _uint(a[9], 255),
    )


def _p_session(a: list[str]) -> Frame:
    _args(a, 10)
    flags = _uint(a[1], 3)
    if not _SEQ_RE.fullmatch(a[8]):
        raise _bad(f"invalid sequence id: {a[8]!r}")
    groups = tuple(a[9].split(":"))
    if not 1 <= len(groups) <= 8 or not all(_JGROUP_RE.fullmatch(g) for g in groups):
        raise _bad(f"invalid groups: {a[9]!r}")
    return SessionInfo(
        _uint(a[0], 255),
        bool(flags & 1),
        bool(flags & 2),
        _uint(a[2], 255),
        _uint(a[3], 255),
        _uint(a[4], _U32_MAX),
        _uint(a[5], _U32_MAX),
        _uint(a[6], _U32_MAX),
        _uint(a[7], _U32_MAX),
        a[8],
        groups,
    )


def _p_pair(a: list[str]) -> Frame:
    if not a:
        raise _bad("missing pairing subcommand")
    sub, rest = a[0], a[1:]
    if sub == "open":
        _args(rest, 1)
        return PairOpen(_ranged(rest[0], 1, 120))
    if sub == "close":
        _args(rest, 0)
        return PairClose()
    if sub == "accept":
        _args(rest, 2)
        mask = _hex(rest[1], _MASK_RE, "mask")
        if mask > 0x7F:
            raise _bad("mask has only 7 action bits")
        return PairAccept(_mac(rest[0]), mask)
    if sub == "reject":
        _args(rest, 1)
        return PairReject(_mac(rest[0]))
    if sub == "del":
        _args(rest, 1)
        return PairDelete(_mac(rest[0]))
    if sub == "ack":
        _args(rest, 3)
        return PairAck(_mac(rest[0]), _uint(rest[1], _U32_MAX), _uint(rest[2], 1))
    if sub == "tx":
        _args(rest, 1)
        return PairTx(_ranged(rest[0], 1, 7))
    if sub == "req":
        _args(rest, 3)
        return PairRequest(_mac(rest[0]), _roster_name(rest[1]), _roster_caps(rest[2]))
    if sub == "cmd":
        _args(rest, 3)
        return RemoteCommand(_mac(rest[0]), _ranged(rest[1], 1, 7), _uint(rest[2], _U32_MAX))
    if sub == "paired":
        _args(rest, 1)
        return PairDone(_mac(rest[0]))
    if sub == "state":
        _args(rest, 2)
        return PairState(_flag(rest[0]), _uint(rest[1], 120))
    raise _bad(f"unknown pairing subcommand: {sub!r}")


def _p_mesh_status(a: list[str]) -> Frame:
    _args(a, 6)
    if a[0] not in ROLES or a[1] not in ESPNOW_SOURCES:
        raise _bad(f"invalid mesh status: {a!r}")
    return MeshStatus(
        a[0],
        a[1],
        _uint(a[2], 99),
        _flag(a[3]),
        _hex(a[4], _ID_RE, "master id"),
        _ranged(a[5], 1, 13),
    )


def _p_roster(a: list[str]) -> Frame:
    if len(a) == 2 and a[1] == "gone":
        return RosterGone(_mac(a[0]))
    _args(a, 6)
    if a[1] not in ("N", "R", "M", "F", "E"):
        raise _bad(f"invalid roster kind: {a[1]!r}")
    if not _SEMVER_RE.fullmatch(a[4]):
        raise _bad(f"invalid firmware version: {a[4]!r}")
    return RosterEntry(
        _mac(a[0]), a[1], _roster_caps(a[2]), _uint(a[3], 127), a[4], _roster_name(a[5])
    )


def _feed_payload(a: list[str], exact: Optional[int]) -> bytes:
    _args(a, 1)
    if not _HEX_RE.fullmatch(a[0]):
        raise _bad("payload must be uppercase hex bytes")
    data = bytes.fromhex(a[0])
    if exact is not None and len(data) != exact:
        raise _bad(f"payload must be {exact} bytes, got {len(data)}")
    return data


def _p_feed_timer(a: list[str]) -> Frame:
    return FeedTimer(_feed_payload(a, _TIMER_PAYLOAD_BYTES))


def _p_feed_sound(a: list[str]) -> Frame:
    return FeedSound(_feed_payload(a, _SOUND_PAYLOAD_BYTES))


def _p_feed_session(a: list[str]) -> Frame:
    return FeedSession(_feed_payload(a, None))


_PARSERS: dict[str, Callable[[list[str]], Frame]] = {
    "L": _p_lights,
    "S": _p_whistle,
    "B": _p_buzzer,
    "G": _p_group,
    "T": _p_remaining,
    "H": _p_heartbeat,
    "V": _p_hello,
    "I": _p_hello_reply,
    "A": _p_ack,
    "K": _p_button,
    "M": _p_espnow_mode,
    "N": _p_espnow_status,
    "E": _p_error,
    "R": _p_role,
    "C": _p_config,
    "Q": _p_config_query,
    "U": _p_timer_state,
    "J": _p_session,
    "P": _p_pair,
    "O": _p_mesh_status,
    "D": _p_roster,
    "F": _p_feed_timer,
    "W": _p_feed_sound,
    "Y": _p_feed_session,
}

# --- encode / decode ---------------------------------------------------------------------


def checksum(body: bytes) -> int:
    """XOR of all bytes. ``body`` is what lies between ``$`` and ``*``."""
    return reduce(lambda acc, b: acc ^ b, body, 0)


def frame_fields(frame: Frame) -> tuple[str, list[str]]:
    """The command letter and argument strings a frame is sent as."""
    if isinstance(frame, Lights):
        return "L", [frame.state]
    if isinstance(frame, Whistle):
        return "S", _whistle_args(frame)
    if isinstance(frame, Buzzer):
        return "B", ["1" if frame.on else "0"]
    if isinstance(frame, Group):
        return "G", [frame.name]
    if isinstance(frame, Remaining):
        return "T", [str(frame.ms)]
    if isinstance(frame, Heartbeat):
        return "H", [str(frame.seq), frame.lights, frame.group]
    if isinstance(frame, Hello):
        return "V", []
    if isinstance(frame, HelloReply):
        return "I", [str(frame.proto), frame.fw, frame.caps]
    if isinstance(frame, Ack):
        return "A", [str(frame.seq)]
    if isinstance(frame, Button):
        return "K", [str(frame.id), "1" if frame.down else "0"]
    if isinstance(frame, EspNowMode):
        return "M", [str(frame.mode)]
    if isinstance(frame, EspNowStatus):
        return "N", [str(frame.mode), str(frame.peers), frame.src]
    if isinstance(frame, Error):
        return "E", [frame.code]
    return _v2_fields(frame)


def _whistle_args(frame: Whistle) -> list[str]:
    args = [str(frame.count)]
    if frame.id is None:
        if frame.blast_ms is not None or frame.gap_ms is not None:
            raise _bad("whistle timing needs an id")
        return args
    args.append(str(frame.id))
    if frame.blast_ms is not None or frame.gap_ms is not None:
        if frame.blast_ms is None or frame.gap_ms is None:
            raise _bad("whistle timing needs both blast and gap")
        args += [str(frame.blast_ms), str(frame.gap_ms)]
    return args


def _id8(value: int) -> str:
    if not 0 <= value <= _U32_MAX:
        raise _bad(f"id out of range: {value}")
    return f"{value:08X}"


def _v2_fields(frame: Frame) -> tuple[str, list[str]]:
    """Wire strings of the serial v2 frames (an empty caps or name goes out as ``-``)."""
    if isinstance(frame, Role):
        if frame.master_id is None:
            return "R", [frame.role]
        if frame.session is None or not 1 <= frame.session <= _U32_MAX:
            raise _bad("role frame session must be 1..2^32-1")
        return "R", [frame.role, _id8(frame.master_id), str(frame.session)]
    if isinstance(frame, Config):
        return "C", [frame.key, frame.value]
    if isinstance(frame, ConfigQuery):
        return "Q", []
    if isinstance(frame, TimerState):
        nums = (
            frame.mode,
            frame.phase,
            frame.remaining_ms,
            frame.end_no,
            frame.total_ends,
            frame.group,
            frame.round,
            frame.total_rounds,
            frame.flags,
            frame.rev,
        )
        return "U", [str(n) for n in nums]
    if isinstance(frame, SessionInfo):
        flags = (1 if frame.alternate_order else 0) | (2 if frame.auto_advance else 0)
        head = (frame.rev, flags, frame.total_ends, frame.practice_ends, frame.prep_ms)
        times = (frame.shoot_ms, frame.warn_ms, frame.auto_delay_ms)
        return "J", [
            *(str(n) for n in head),
            *(str(n) for n in times),
            frame.sequence_id,
            ":".join(frame.groups),
        ]
    if isinstance(frame, PairOpen):
        return "P", ["open", str(frame.seconds)]
    if isinstance(frame, PairClose):
        return "P", ["close"]
    if isinstance(frame, PairAccept):
        return "P", ["accept", frame.mac, f"{frame.mask:02X}"]
    if isinstance(frame, PairReject):
        return "P", ["reject", frame.mac]
    if isinstance(frame, PairDelete):
        return "P", ["del", frame.mac]
    if isinstance(frame, PairAck):
        return "P", ["ack", frame.mac, str(frame.counter), str(frame.result)]
    if isinstance(frame, PairTx):
        return "P", ["tx", str(frame.action)]
    if isinstance(frame, PairRequest):
        return "P", ["req", frame.mac, frame.name or "-", frame.caps or "-"]
    if isinstance(frame, RemoteCommand):
        return "P", ["cmd", frame.mac, str(frame.action), str(frame.counter)]
    if isinstance(frame, PairDone):
        return "P", ["paired", frame.mac]
    if isinstance(frame, PairState):
        return "P", ["state", "1" if frame.open else "0", str(frame.seconds_left)]
    if isinstance(frame, MeshStatus):
        return "O", [
            frame.role,
            frame.src,
            str(frame.peers),
            "1" if frame.conflict else "0",
            _id8(frame.master_id),
            str(frame.chan),
        ]
    if isinstance(frame, RosterEntry):
        return "D", [
            frame.mac,
            frame.kind,
            frame.caps or "-",
            str(frame.rssi),
            frame.fw,
            frame.name or "-",
        ]
    if isinstance(frame, RosterGone):
        return "D", [frame.mac, "gone"]
    if isinstance(frame, FeedTimer):
        return "F", [frame.payload.hex().upper()]
    if isinstance(frame, FeedSound):
        return "W", [frame.payload.hex().upper()]
    if isinstance(frame, FeedSession):
        return "Y", [frame.payload.hex().upper()]
    raise TypeError(f"not a protocol frame: {frame!r}")


def _limit(cmd: str) -> int:
    return MAX_LONG_FRAME_BYTES if cmd in LONG_COMMANDS else MAX_FRAME_BYTES


def encode(frame: Frame) -> bytes:
    """Serialize a frame. Raises ``ProtocolError`` (BA or OV) if it is not valid v1."""
    cmd, args = frame_fields(frame)
    _PARSERS[cmd](args)  # same validation the receiver applies
    body = ",".join([cmd, *args]).encode("ascii")
    data = b"$" + body + b"*" + f"{checksum(body):02X}".encode("ascii") + b"\n"
    if len(data) > _limit(cmd):
        raise ProtocolError(ERR_OVERFLOW, f"{len(data)} bytes")
    return data


def decode(line: bytes | str) -> Frame:
    """Parse one frame; a trailing ``\\n`` or ``\\r\\n`` is optional. Raises ``ProtocolError``.

    Checks run in this order: length (OV), framing (MF), checksum (CS), command (UC),
    arguments (BA).
    """
    if isinstance(line, str):
        try:
            data = line.encode("ascii")
        except UnicodeEncodeError:
            raise ProtocolError(ERR_MALFORMED, "non-ASCII input") from None
    else:
        data = line
    if data.endswith(b"\n"):
        data = data[:-1]
    if data.endswith(b"\r"):
        data = data[:-1]
    cmd_letter = data[1:2].decode("ascii", "replace") if data[:1] == b"$" else ""
    if len(data) + 1 > _limit(cmd_letter):
        raise ProtocolError(ERR_OVERFLOW, f"{len(data) + 1} bytes")
    m = _FRAME_RE.fullmatch(data)
    if m is None:
        raise ProtocolError(ERR_MALFORMED, "not a $...*XX frame")
    body = m.group(1)
    if b"$" in body or b"*" in body:
        raise ProtocolError(ERR_MALFORMED, "stray frame delimiter")
    if checksum(body) != int(m.group(2), 16):
        raise ProtocolError(ERR_CHECKSUM)
    cmd, *args = body.decode("ascii").split(",")
    parser = _PARSERS.get(cmd)
    if parser is None:
        raise ProtocolError(ERR_UNKNOWN_CMD, cmd)
    return parser(args)


class FrameParser:
    """Incremental decoder for a byte stream (split reads, garbage, over-long lines).

    ``feed`` returns frames and ``ProtocolError`` values in arrival order; it never raises.
    Empty lines are ignored. Resynchronizes on every ``\\n``.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._overflow = False

    def feed(self, data: bytes) -> list[Frame | ProtocolError]:
        out: list[Frame | ProtocolError] = []
        start = 0
        while True:
            end = data.find(b"\n", start)
            if end < 0:
                self._append(data[start:])
                return out
            self._append(data[start:end])
            result = self._finish()
            if result is not None:
                out.append(result)
            start = end + 1

    def _append(self, chunk: bytes) -> None:
        if self._overflow:
            return
        self._buf.extend(chunk)
        if len(self._buf) > MAX_LONG_FRAME_BYTES:  # content plus an optional CR
            self._overflow = True
            self._buf.clear()

    def _finish(self) -> Frame | ProtocolError | None:
        if self._overflow:
            self._overflow = False
            return ProtocolError(ERR_OVERFLOW, "line too long")
        line = bytes(self._buf)
        self._buf.clear()
        if line in (b"", b"\r"):
            return None
        try:
            return decode(line)
        except ProtocolError as exc:
            return exc

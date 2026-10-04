"""Mesh v2 radio frame codec (``docs/mesh.md`` sections 1, 2 and 5): header, HMAC tag, payloads.

Pure functions, no I/O. The payloads of TIMER, SOUND and SESSION are the dataclasses of
``mesh_types``; the other frame types are defined here. Reference for the firmware and the
simulator, validated against ``firmware/mesh_vectors.txt``.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Union

from archerytimer.common.compat import SLOTS
from archerytimer.hardware.mesh_types import (
    ACTIONS,
    RadioSession,
    RadioSound,
    RadioTimer,
)

MAGIC = 0xA8
VERSION = 0x02
HEADER_LEN = 8
TAG_LEN = 8
MAX_FRAME = 250
MAX_NAME = 12
MAC_LEN = 6
PUB_LEN = 32
ZERO_KEY = bytes(16)

T_HELLO, T_TIMER, T_SOUND, T_CMD, T_CMD_ACK, T_SESSION = 1, 2, 3, 4, 5, 6
T_PAIR_OPEN, T_PAIR_REQ, T_PAIR_ACC = 7, 8, 9
TYPE_NAMES = {
    T_HELLO: "HELLO",
    T_TIMER: "TIMER",
    T_SOUND: "SOUND",
    T_CMD: "CMD",
    T_CMD_ACK: "CMD_ACK",
    T_SESSION: "SESSION",
    T_PAIR_OPEN: "PAIR_OPEN",
    T_PAIR_REQ: "PAIR_REQ",
    T_PAIR_ACC: "PAIR_ACC",
}
MESH_KEY_TYPES = (T_HELLO, T_TIMER, T_SOUND, T_CMD_ACK, T_SESSION, T_PAIR_OPEN)

RESULT_DONE, RESULT_DENIED, RESULT_UNKNOWN = 0, 1, 2


class FrameError(ValueError):
    """The frame must be dropped silently."""


# --- payloads that are not in mesh_types ---------------------------------------------------


@dataclass(frozen=True, **SLOTS)
class RadioHello:
    caps: int
    role: int
    rank: int
    conflict: int
    master_id: int
    fw: tuple[int, int, int]
    name: str = ""

    def to_bytes(self) -> bytes:
        name = self.name.encode("ascii")
        if len(name) > MAX_NAME:
            raise ValueError("HELLO name too long")
        return (
            struct.pack("<BBBBIBBBB", self.caps, self.role, self.rank, self.conflict,
                        self.master_id, *self.fw, len(name)) + name
        )  # fmt: skip

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioHello:
        head = struct.Struct("<BBBBIBBBB")
        if len(data) < head.size:
            raise ValueError("HELLO payload too short")
        caps, role, rank, conflict, mid, f0, f1, f2, n = head.unpack_from(data)
        if n > MAX_NAME or len(data) != head.size + n:
            raise ValueError("bad HELLO name length")
        return cls(caps, role, rank, conflict, mid, (f0, f1, f2),
                   data[head.size :].decode("ascii"))  # fmt: skip


@dataclass(frozen=True, **SLOTS)
class RadioCmd:
    counter: int
    action: int

    def to_bytes(self) -> bytes:
        return struct.pack("<IB", self.counter, self.action)

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioCmd:
        if len(data) != 5:
            raise ValueError("CMD payload must be 5 bytes")
        counter, action = struct.unpack("<IB", data)
        if action not in ACTIONS:
            raise ValueError(f"CMD action {action} may not be sent by a remote")
        return cls(counter, action)


@dataclass(frozen=True, **SLOTS)
class RadioCmdAck:
    target_mac: bytes
    counter: int
    result: int

    def to_bytes(self) -> bytes:
        return self.target_mac + struct.pack("<IB", self.counter, self.result)

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioCmdAck:
        if len(data) != MAC_LEN + 5:
            raise ValueError("CMD_ACK payload must be 11 bytes")
        counter, result = struct.unpack_from("<IB", data, MAC_LEN)
        if result > RESULT_UNKNOWN:
            raise ValueError("bad CMD_ACK result")
        return cls(bytes(data[:MAC_LEN]), counter, result)


@dataclass(frozen=True, **SLOTS)
class RadioPairOpen:
    master_id: int
    seconds_left: int
    master_pub: bytes

    def to_bytes(self) -> bytes:
        return struct.pack("<IB", self.master_id, self.seconds_left) + self.master_pub

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioPairOpen:
        if len(data) != 5 + PUB_LEN:
            raise ValueError("PAIR_OPEN payload must be 37 bytes")
        mid, left = struct.unpack_from("<IB", data)
        return cls(mid, left, bytes(data[5:]))


@dataclass(frozen=True, **SLOTS)
class RadioPairReq:
    caps: int
    name: str
    remote_pub: bytes

    def to_bytes(self) -> bytes:
        name = self.name.encode("ascii")
        return bytes([self.caps, len(name)]) + name + self.remote_pub

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioPairReq:
        if len(data) < 2:
            raise ValueError("PAIR_REQ payload too short")
        n = data[1]
        if n > MAX_NAME or len(data) != 2 + n + PUB_LEN:
            raise ValueError("bad PAIR_REQ length")
        return cls(data[0], data[2 : 2 + n].decode("ascii"), bytes(data[2 + n :]))


@dataclass(frozen=True, **SLOTS)
class RadioPairAcc:
    target_mac: bytes
    blob: bytes

    def to_bytes(self) -> bytes:
        return self.target_mac + self.blob

    @classmethod
    def from_bytes(cls, data: bytes) -> RadioPairAcc:
        if len(data) != MAC_LEN + 32:
            raise ValueError("PAIR_ACC payload must be 38 bytes")
        return cls(bytes(data[:MAC_LEN]), bytes(data[MAC_LEN:]))


Payload = Union[
    RadioHello,
    RadioTimer,
    RadioSound,
    RadioCmd,
    RadioCmdAck,
    RadioSession,
    RadioPairOpen,
    RadioPairReq,
    RadioPairAcc,
]

_PAYLOAD_TYPE: dict[type, int] = {
    RadioHello: T_HELLO,
    RadioTimer: T_TIMER,
    RadioSound: T_SOUND,
    RadioCmd: T_CMD,
    RadioCmdAck: T_CMD_ACK,
    RadioSession: T_SESSION,
    RadioPairOpen: T_PAIR_OPEN,
    RadioPairReq: T_PAIR_REQ,
    RadioPairAcc: T_PAIR_ACC,
}
_PARSERS: dict[int, Callable[[bytes], Payload]] = {
    T_HELLO: RadioHello.from_bytes,
    T_TIMER: RadioTimer.from_bytes,
    T_SOUND: RadioSound.from_bytes,
    T_CMD: RadioCmd.from_bytes,
    T_CMD_ACK: RadioCmdAck.from_bytes,
    T_SESSION: RadioSession.from_bytes,
    T_PAIR_OPEN: RadioPairOpen.from_bytes,
    T_PAIR_REQ: RadioPairReq.from_bytes,
    T_PAIR_ACC: RadioPairAcc.from_bytes,
}


@dataclass(frozen=True, **SLOTS)
class MeshFrame:
    ptype: int
    epoch: int
    seq: int
    payload: Payload
    hop: int = 0


@dataclass(**SLOTS)
class KeyRing:
    """The keys a node holds. ``remote_keys`` are keyed by the remote's MAC (6 bytes)."""

    mesh_key: bytes
    remote_keys: Mapping[bytes, bytes] = field(default_factory=dict)
    pairing_open: bool = False  # PAIR_REQ (zero key) is accepted only while this is set
    pair_key: Optional[bytes] = None  # K, for PAIR_ACC


def compute_tag(key: bytes, body: bytes, src_mac: bytes) -> bytes:
    return hmac.new(key, body + src_mac, hashlib.sha256).digest()[:TAG_LEN]


def encode(frame: MeshFrame, key: bytes, src_mac: bytes) -> bytes:
    """Build a complete frame (header, payload, tag) signed with ``key``."""
    if len(src_mac) != MAC_LEN:
        raise ValueError("MAC must be 6 bytes")
    ptype = _PAYLOAD_TYPE[type(frame.payload)]
    if ptype != frame.ptype:
        raise ValueError("ptype does not match the payload")
    if not 0 <= frame.hop <= 3:
        raise ValueError("hop is two bits")
    body = struct.pack("<BBBBHH", MAGIC, VERSION, ptype, frame.hop, frame.epoch & 0xFFFF,
                       frame.seq & 0xFFFF) + frame.payload.to_bytes()  # fmt: skip
    out = body + compute_tag(key, body, src_mac)
    if len(out) > MAX_FRAME:
        raise ValueError("frame exceeds the ESP-NOW limit")
    return out


def make_frame(payload: Payload, epoch: int, seq: int) -> MeshFrame:
    return MeshFrame(_PAYLOAD_TYPE[type(payload)], epoch, seq, payload)


def key_for(ptype: int, src_mac: bytes, keys: KeyRing) -> Optional[bytes]:
    """The key that signs a frame of this type from this sender, or None if it cannot be valid."""
    if ptype in MESH_KEY_TYPES:
        return keys.mesh_key
    if ptype == T_CMD:
        return keys.remote_keys.get(src_mac)
    if ptype == T_PAIR_REQ:
        return ZERO_KEY if keys.pairing_open else None
    if ptype == T_PAIR_ACC:
        return keys.pair_key
    return None


def decode(data: bytes, src_mac: bytes, keys: KeyRing) -> MeshFrame:
    """Validate and parse one received frame; raise ``FrameError`` if it must be dropped."""
    if len(data) < HEADER_LEN + TAG_LEN or len(data) > MAX_FRAME:
        raise FrameError("length")
    magic, version, ptype, flags, epoch, seq = struct.unpack_from("<BBBBHH", data)
    if magic != MAGIC or version != VERSION:
        raise FrameError("magic/version")
    if flags != 0:  # hop must be 0 in the first release, other bits reserved
        raise FrameError("flags/hop")
    if ptype not in _PARSERS:
        raise FrameError("type")
    key = key_for(ptype, src_mac, keys)
    if key is None:
        raise FrameError("no key")
    body = data[:-TAG_LEN]
    if not hmac.compare_digest(compute_tag(key, body, src_mac), data[-TAG_LEN:]):
        raise FrameError("tag")
    try:
        payload = _PARSERS[ptype](body[HEADER_LEN:])
    except (ValueError, UnicodeDecodeError, struct.error) as exc:
        raise FrameError(f"payload: {exc}") from None
    return MeshFrame(ptype, epoch, seq, payload, 0)


def try_decode(data: bytes, src_mac: bytes, keys: KeyRing) -> Optional[MeshFrame]:
    try:
        return decode(data, src_mac, keys)
    except FrameError:
        return None


# --- dedupe (section 1) --------------------------------------------------------------------


def seq_newer(seq: int, last: int) -> bool:
    """``int16(seq - last) > 0``"""
    diff = (seq - last) & 0xFFFF
    return 0 < diff < 0x8000


class Dedupe:
    """Per-source ``(epoch, seq)`` filter. A new epoch resets the peer and is accepted at once."""

    def __init__(self) -> None:
        self._last: dict[bytes, tuple[int, int]] = {}

    def accept(self, src_mac: bytes, epoch: int, seq: int) -> bool:
        prev = self._last.get(src_mac)
        if prev is None or prev[0] != epoch:
            self._last[src_mac] = (epoch, seq)
            return True
        if seq_newer(seq, prev[1]):
            self._last[src_mac] = (epoch, seq)
            return True
        return False

    def forget(self, src_mac: bytes) -> None:
        self._last.pop(src_mac, None)

    def clear(self) -> None:
        self._last.clear()


# --- pairing crypto after the key agreement (section 5, steps 4) ---------------------------


def derive_pair_key(shared: bytes, remote_mac: bytes, master_mac: bytes) -> bytes:
    return hmac.new(shared, b"harno-pair" + remote_mac + master_mac, hashlib.sha256).digest()


def pair_blob(pair_key: bytes, mesh_key: bytes, remote_key: bytes) -> bytes:
    """``(mesh_key || remote_key) XOR HMAC(K, "enc")``; the same call decrypts."""
    pad = hmac.new(pair_key, b"enc", hashlib.sha256).digest()
    plain = mesh_key + remote_key
    if len(plain) != 32:
        raise ValueError("keys must be 16 bytes each")
    return bytes(a ^ b for a, b in zip(plain, pad))


def open_blob(pair_key: bytes, blob: bytes) -> tuple[bytes, bytes]:
    """Remote side: recover ``(mesh_key, remote_key)`` from a PAIR_ACC blob."""
    pad = hmac.new(pair_key, b"enc", hashlib.sha256).digest()
    plain = bytes(a ^ b for a, b in zip(blob, pad))
    return plain[:16], plain[16:]

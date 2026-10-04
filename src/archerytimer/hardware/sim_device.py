"""Simulated microcontroller speaking serial protocol v1 (and v2 with capability R).

``SimDevice`` is a deterministic, synchronous core: bytes in (``feed``), reply bytes out,
and ``poll`` to run the watchdog. It reads time only from the injected ``Clock``, so tests
drive it with a ``FakeClock``.

To use it like a real serial port, ``SimDeviceRunner`` runs a device on a thread over a
port object with the small pyserial-like API used here (``read``, ``write``, ``close``,
``is_open``, ``timeout``). Two ports are provided:

- ``memory_port_pair()``: an in-memory cable, works on every platform.
- ``open_pty()``: a pseudo-terminal for Linux and macOS; the host opens the returned path
  with pyserial exactly as it would open ``/dev/ttyACM0``.
"""

from __future__ import annotations

import sys
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from archerytimer.common.clock import NS_PER_S, Clock, MonotonicClock
from archerytimer.common.compat import SLOTS
from archerytimer.hardware.mesh_types import (
    Config,
    ConfigQuery,
    PairAccept,
    PairAck,
    PairClose,
    PairDelete,
    PairOpen,
    PairReject,
    PairTx,
    Role,
    SessionInfo,
    TimerState,
)
from archerytimer.hardware.protocol import (
    CAPABILITIES,
    ERR_BAD_ARG,
    ERR_UNKNOWN_CMD,
    HOST_FRAME_TYPES,
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_MESH,
    Ack,
    Button,
    Buzzer,
    Error,
    EspNowMode,
    EspNowStatus,
    FrameParser,
    Group,
    Heartbeat,
    Hello,
    HelloReply,
    Lights,
    ProtocolError,
    Remaining,
    Whistle,
    encode,
)

SAFE_LIGHTS = "R"
DEFAULT_WATCHDOG_NS = NS_PER_S  # no valid frame for this long: force RED and silence

_CAP_FOR_FRAME: dict[type, str] = {
    Lights: "L",
    Whistle: "S",
    Buzzer: "B",
    Group: "G",
    Remaining: "T",
    EspNowMode: "N",
    Role: "R",
    Config: "R",
    ConfigQuery: "R",
    TimerState: "R",
    SessionInfo: "R",
    PairOpen: "R",
    PairClose: "R",
    PairAccept: "R",
    PairReject: "R",
    PairDelete: "R",
    PairAck: "R",
    PairTx: "R",
}

# Stored configuration of a fresh v2 device (``$C``); ``mkey`` is write-only.
DEFAULT_CONFIG = {
    "name": "sim",
    "lights": "1",
    "sound": "1",
    "radio": "1",
    "remote": "1",
    "chan": "1",
    "btn1": "0",
    "btn2": "0",
    "btn3": "0",
    "btn4": "0",
}


@dataclass(frozen=True, **SLOTS)
class LogEntry:
    """One frame as the device saw it. ``direction`` is ``"rx"`` or ``"tx"``."""

    t_ns: int
    direction: str
    data: bytes


class SimDevice:
    """Behaves like the reference firmware: handshake, state assertions, ACKs, watchdog."""

    def __init__(
        self,
        clock: Clock | None = None,
        *,
        fw: str = "sim-0.1.0",
        caps: str = CAPABILITIES,
        proto: int | None = None,
        watchdog_ns: int = DEFAULT_WATCHDOG_NS,
        log_size: int = 1000,
    ) -> None:
        self._clock: Clock = clock or MonotonicClock()
        self._fw = fw
        self._caps = caps
        # Reports proto 2 when it has capability R (mesh v2), unless a test forces a value.
        self._proto = (
            proto
            if proto is not None
            else (PROTOCOL_VERSION_MESH if "R" in caps else PROTOCOL_VERSION)
        )
        self._last_sound_id = 0
        self.sound_dupes = 0
        self._watchdog_ns = watchdog_ns
        self._parser = FrameParser()
        self._last_valid_rx_ns = self._clock.now_ns()
        self._drop_rx = 0
        self._corrupt_tx = 0
        self._pending = bytearray()
        self.mute = False  # a dead MCU: still acts on frames, never replies
        self.log: deque[LogEntry] = deque(maxlen=log_size)

        # Observable output state. Boots into the safe state.
        self.lights = SAFE_LIGHTS
        self.group = ""
        self.remaining_ms: int | None = None
        self.buzzer = False
        self.whistle = 0  # blasts of the last $S; 0 = silent
        self.sound_events: list[int] = []  # every $S count received, in order
        self.last_heartbeat_seq: int | None = None
        self.fault = False  # watchdog has tripped and no valid frame has arrived since
        self.watchdog_trips = 0
        self.espnow_mode = 0  # last $M received

        # Serial v2 state (only touched when the device has capability R).
        self.role: Role | None = None  # last $R received
        self.config: dict[str, str] = dict(DEFAULT_CONFIG)
        self.mkey = ""
        self.timer_state: TimerState | None = None
        self.session: SessionInfo | None = None
        self.pairing: list[Any] = []  # every $P host frame received, in order
        self.whistle_timing: tuple[int, int] | None = None  # blast_ms, gap_ms of the last $S

    # --- fault injection -------------------------------------------------------------

    def drop_frames(self, n: int) -> None:
        """Ignore the next ``n`` valid incoming frames, as if lost on the wire."""
        self._drop_rx = n

    def corrupt_replies(self, n: int) -> None:
        """Flip a byte in the next ``n`` replies so their checksum fails."""
        self._corrupt_tx = n

    def press_button(self, button_id: int, down: bool = True) -> None:
        """Queue a ``$K`` frame; ``SimDeviceRunner`` writes it to the host promptly."""
        self._pending += self._send(Button(button_id, down))

    def emit(self, frame: Any) -> None:
        """Queue any MCU-to-host frame (``$O $D $F $W $Y $P ...``); the runner writes it out."""
        self._pending += self._send(frame)

    def take_pending(self) -> bytes:
        data, self._pending = bytes(self._pending), bytearray()
        return data

    # --- I/O -------------------------------------------------------------------------

    def feed(self, data: bytes) -> bytes:
        """Process bytes received from the host and return the bytes to send back."""
        replies = bytearray()
        for item in self._parser.feed(data):
            now = self._clock.now_ns()
            if isinstance(item, ProtocolError):
                if item.code != "MF":  # framing garbage is dropped silently
                    replies += self._send(Error(item.code))
                continue
            self.log.append(LogEntry(now, "rx", encode(item)))
            if not isinstance(item, HOST_FRAME_TYPES):
                replies += self._send(Error(ERR_UNKNOWN_CMD))
                continue
            if self._drop_rx > 0:
                self._drop_rx -= 1
                continue
            self._last_valid_rx_ns = now
            self.fault = False
            needed = _CAP_FOR_FRAME.get(type(item))
            if isinstance(item, Whistle) and item.blast_ms is not None:
                needed = "W"
            if needed is not None and needed not in self._caps:
                replies += self._send(Error(ERR_UNKNOWN_CMD))
                continue
            replies += self._handle(item)
        return bytes(replies)

    def poll(self) -> bool:
        """Run the watchdog. Returns True if it tripped on this call."""
        if self.fault:
            return False
        if self._clock.now_ns() - self._last_valid_rx_ns < self._watchdog_ns:
            return False
        self.fault = True
        self.watchdog_trips += 1
        self.lights = SAFE_LIGHTS
        self.buzzer = False
        self.whistle = 0
        return True

    # --- internals -------------------------------------------------------------------

    def _handle(self, frame: Any) -> bytes:
        if isinstance(frame, Hello):
            return self._send(HelloReply(self._proto, self._fw, self._caps))
        if isinstance(frame, Lights):
            self.lights = frame.state
        elif isinstance(frame, Whistle):
            if frame.id is not None:
                if frame.id == self._last_sound_id:
                    self.sound_dupes += 1  # a repeat of a frame already acted on
                    return b""
                self._last_sound_id = frame.id
            self.whistle = frame.count
            self.whistle_timing = (
                None if frame.blast_ms is None else (frame.blast_ms, frame.gap_ms or 0)
            )
            self.sound_events.append(frame.count)
            if frame.count == 0:
                self.buzzer = False
        elif isinstance(frame, Buzzer):
            self.buzzer = frame.on
        elif isinstance(frame, Group):
            self.group = frame.name
        elif isinstance(frame, Remaining):
            self.remaining_ms = frame.ms
        elif isinstance(frame, EspNowMode):
            self.espnow_mode = frame.mode
            return self._send(EspNowStatus(frame.mode, 0, "H"))
        elif isinstance(frame, Role):
            self.role = frame
        elif isinstance(frame, Config):
            self.config[frame.key] = frame.value
            if frame.key == "mkey":
                self.mkey = frame.value
                self.config.pop("mkey")
            return self._send(frame)  # stored: echo the same frame
        elif isinstance(frame, ConfigQuery):
            return b"".join(self._send(Config(k, v)) for k, v in self.config.items())
        elif isinstance(frame, TimerState):
            self.timer_state = frame
        elif isinstance(frame, SessionInfo):
            self.session = frame
        elif isinstance(
            frame,
            (PairOpen, PairClose, PairAccept, PairReject, PairDelete, PairAck, PairTx),
        ):
            self.pairing.append(frame)
        elif isinstance(frame, Heartbeat):
            self.lights = frame.lights
            if "G" in self._caps:
                self.group = frame.group
            self.last_heartbeat_seq = frame.seq
            return self._send(Ack(frame.seq))
        else:  # pragma: no cover - guarded by HOST_FRAME_TYPES
            return self._send(Error(ERR_BAD_ARG))
        return b""

    def _send(self, frame: Any) -> bytes:
        data = encode(frame)
        self.log.append(LogEntry(self._clock.now_ns(), "tx", data))
        if self._corrupt_tx > 0:
            self._corrupt_tx -= 1
            data = data[:1] + bytes([data[1] ^ 0x01]) + data[2:]
        return b"" if self.mute else data


# --- ports -------------------------------------------------------------------------------


class Port(Protocol):
    timeout: float | None

    @property
    def is_open(self) -> bool: ...

    def read(self, size: int = 1) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def close(self) -> None: ...


class _Pipe:
    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.buf = bytearray()
        self.closed = False


class MemoryPort:
    """One end of an in-memory serial cable. Closing either end closes both (an unplug)."""

    def __init__(self, rx: _Pipe, tx: _Pipe) -> None:
        self._rx = rx
        self._tx = tx
        self.timeout: float | None = None

    @property
    def is_open(self) -> bool:
        return not self._rx.closed

    @property
    def in_waiting(self) -> int:
        with self._rx.cond:
            return len(self._rx.buf)

    def read(self, size: int = 1) -> bytes:
        """Return up to ``size`` bytes; wait up to ``timeout`` seconds if none are ready."""
        with self._rx.cond:
            if not self._rx.buf and not self._rx.closed and self.timeout != 0:
                self._rx.cond.wait(self.timeout)
            data = bytes(self._rx.buf[:size])
            del self._rx.buf[:size]
            return data

    def write(self, data: bytes) -> int:
        with self._tx.cond:
            if self._tx.closed:
                raise OSError("port closed")
            self._tx.buf.extend(data)
            self._tx.cond.notify_all()
        return len(data)

    def close(self) -> None:
        for pipe in (self._rx, self._tx):
            with pipe.cond:
                pipe.closed = True
                pipe.cond.notify_all()


def memory_port_pair() -> tuple[MemoryPort, MemoryPort]:
    """Return ``(host_end, device_end)`` of an in-memory cable."""
    to_device, to_host = _Pipe(), _Pipe()
    return MemoryPort(rx=to_host, tx=to_device), MemoryPort(rx=to_device, tx=to_host)


class PtyPort:
    """Device end of a pseudo-terminal (POSIX only)."""

    def __init__(self, master_fd: int, slave_fd: int) -> None:
        self._master = master_fd
        self._slave = slave_fd  # held open so the host side never sees a hang-up early
        self._open = True
        self.timeout: float | None = None

    @property
    def is_open(self) -> bool:
        return self._open

    def read(self, size: int = 1) -> bytes:
        import os
        import select

        if not self._open:
            return b""
        ready, _, _ = select.select([self._master], [], [], self.timeout)
        if not ready:
            return b""
        try:
            return os.read(self._master, size)
        except OSError:
            return b""

    def write(self, data: bytes) -> int:
        import os

        return os.write(self._master, data)

    def close(self) -> None:
        import os

        if self._open:
            self._open = False
            os.close(self._master)
            os.close(self._slave)


def open_pty() -> tuple[PtyPort, str]:
    """Create a pty. Returns the device end and the path the host should open."""
    if sys.platform == "win32":
        raise OSError("pseudo-terminals are not available on Windows; use memory_port_pair()")
    import os
    import pty
    import tty

    master, slave = pty.openpty()
    tty.setraw(slave)  # no echo, no line editing, no CR/LF translation
    return PtyPort(master, slave), os.ttyname(slave)


# --- runner ------------------------------------------------------------------------------


class SimDeviceRunner:
    """Runs a ``SimDevice`` on its own thread over a port, until stopped or the port closes."""

    def __init__(self, device: SimDevice, port: Port, *, poll_s: float = 0.005) -> None:
        self._device = device
        self._port = port
        self._poll_s = poll_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sim-device", daemon=False)

    def start(self) -> SimDeviceRunner:
        self._port.timeout = self._poll_s
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def __enter__(self) -> SimDeviceRunner:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop.is_set() and self._port.is_open:
            data = self._port.read(256)
            if data:
                reply = self._device.feed(data)
                if reply:
                    try:
                        self._port.write(reply)
                    except OSError:
                        break
            pending = self._device.take_pending()
            if pending:
                try:
                    self._port.write(pending)
                except OSError:
                    break
            self._device.poll()

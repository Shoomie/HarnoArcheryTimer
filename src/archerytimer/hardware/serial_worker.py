"""Serial worker: turns engine events into protocol frames, keeps the link alive.

One writer thread blocks on a ``SimpleQueue`` (no polling), writes each state change
the moment it arrives, and re-asserts full state with a heartbeat every 200 ms. A small
reader thread per connection collects ACKs. If writes fail, or heartbeats go unanswered
for ``ack_timeout_s``, the link is reported down and the worker reconnects with backoff.

The worker is deliberately dumb: it never decides anything about timing. It only
forwards what the engine emitted. It is used directly as the engine's ``emit`` callback.

Mesh v2: only when the device reports proto 2 and capability ``R`` does the connect sequence send
``$R`` (role) and the stored ``$C`` configuration, and do the methods below put ``$U $J $P $C $Q``
frames on the wire; a proto 1 device never sees any of them. Frames the MCU sends back arrive as
typed items on the ``on_*`` callbacks (called on the reader thread).
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import queue
import threading
from collections import deque
from typing import Callable, Mapping, Optional, Sequence, Union

from archerytimer.common.clock import NS_PER_S, Clock, MonotonicClock
from archerytimer.core import models as m
from archerytimer.hardware import protocol as p
from archerytimer.hardware.mesh_types import (
    FLAG_PAUSED,
    ROLE_NONE,
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
from archerytimer.hardware.sim_device import Port

log = logging.getLogger("archerytimer.serial")

LINK_UP = "up"
LINK_DOWN = "down"

_STOP = object()


class _SetEspNow:
    def __init__(self, mode: int) -> None:
        self.mode = mode


class _SetLights:
    def __init__(self, on: bool) -> None:
        self.on = on


class _SetMcuSound:
    def __init__(self, on: bool) -> None:
        self.on = on


class _MeshFrame:
    """A serial v2 frame to send (dropped silently on a device without mesh support)."""

    def __init__(self, frame: p.Frame) -> None:
        self.frame = frame


class _SetRoleSession:
    def __init__(self, session: int) -> None:
        self.session = session


class _SetRole:
    def __init__(self, role: Role) -> None:
        self.role = role


class _SetConfig:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class _SetTimer:
    def __init__(self, state: TimerState, at_ns: int) -> None:
        self.state = state
        self.at_ns = at_ns  # when the state was true (remaining_ms is valid at this moment)


class _SetSession:
    def __init__(self, session: SessionInfo) -> None:
        self.session = session


MESH_SESSION_RESEND_NS = 2 * NS_PER_S  # the MCU wants SESSION every 2 s (docs/protocol.md)

# A whistle frame with an id is repeated at these delays; the MCU ignores repeats of an id it
# already acted on, so a frame lost on the wire is healed within ~120 ms.
WHISTLE_RESEND_MS = (40, 120)


class SerialWorker:
    def __init__(
        self,
        port_factory: Callable[[], Port],
        clock: Optional[Clock] = None,
        on_link: Optional[Callable[[str], None]] = None,
        on_button: Optional[Callable[[int, bool], None]] = None,
        on_espnow: Optional[Callable[[p.EspNowStatus], None]] = None,
        espnow_mode: Optional[int] = None,
        *,
        role: Optional[Role] = None,
        config: Optional[Mapping[str, str]] = None,
        on_mesh_status: Optional[Callable[[MeshStatus], None]] = None,
        on_roster: Optional[Callable[[Union[RosterEntry, RosterGone]], None]] = None,
        on_feed: Optional[Callable[[Union[FeedTimer, FeedSound, FeedSession]], None]] = None,
        on_pairing: Optional[Callable[[Union[PairRequest, PairDone, PairState]], None]] = None,
        on_remote_command: Optional[Callable[[RemoteCommand], None]] = None,
        on_config: Optional[Callable[[Config], None]] = None,
        on_connect: Optional[Callable[[Role], Role]] = None,
        heartbeat_s: float = 0.2,
        hello_timeout_s: float = 0.5,
        ack_timeout_s: float = 1.0,
        backoff_s: Sequence[float] = (0.2, 0.5, 1.0, 2.0),
    ) -> None:
        self._factory = port_factory
        self._clock: Clock = clock or MonotonicClock()
        self._on_link = on_link or (lambda _s: None)
        self._on_button = on_button
        self._on_espnow = on_espnow
        self._espnow_mode = espnow_mode  # None: leave the MCU's stored mode alone
        self._on_mesh_status = on_mesh_status
        self._on_roster = on_roster
        self._on_feed = on_feed
        self._on_pairing = on_pairing
        self._on_remote_command = on_remote_command
        self._on_config = on_config
        # Called on the worker thread at every (re)connect to a mesh device, before ``$R`` is
        # written, with the current role; the Role it returns (a master or mirror gets a new,
        # persisted session counter) is what is sent and remembered.
        self._on_connect = on_connect
        self._role = role or Role(ROLE_NONE)  # re-sent on every reconnect (mesh devices only)
        self._config: dict[str, str] = dict(config or {})  # stored $C, re-sent on reconnect
        self._timer: Optional[tuple[TimerState, int]] = None  # (state, received_ns)
        self._session: Optional[SessionInfo] = None
        self._next_session_ns = 0
        self._mesh = False  # the connected device speaks serial v2
        self.mesh_status: Optional[MeshStatus] = None
        self.device_config: dict[str, str] = {}  # what the MCU echoed or reported with $C
        self._mcu_sound = True  # False: the MCU's horn is switched off, no $S / $B frames
        self._lights_on = True  # False: this device's lights are kept dark ($L,O)
        self._whistle_id = 0
        self._resends: list[tuple[int, bytes]] = []  # (due_ns, frame), writer thread only
        self.espnow: Optional[p.EspNowStatus] = None
        self._hb_ns = round(heartbeat_s * NS_PER_S)
        self._hello_timeout_s = hello_timeout_s
        self._ack_timeout_ns = round(ack_timeout_s * NS_PER_S)
        self._backoff = tuple(backoff_s)

        self._queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Desired output state, owned by the worker thread.
        self._lights = "R"
        self._group = ""
        self._hb_seq = 0

        self._link = LINK_DOWN
        self.info: Optional[p.HelloReply] = None
        self.errors: deque[str] = deque(maxlen=50)
        # (enqueue_ns, write_done_ns) per frame written for an engine event; for the probe.
        self.latencies: deque[tuple[int, int]] = deque(maxlen=10_000)

    # ---------------------------------------------------------------- public

    @property
    def link(self) -> str:
        return self._link

    def submit(self, event: m.Event) -> None:
        """Thread-safe, never blocks. Usable directly as the engine's ``emit``."""
        self._queue.put((self._clock.now_ns(), event))

    __call__ = submit

    def set_espnow_mode(self, mode: int) -> None:
        """Thread-safe. Remembered and re-sent on every reconnect."""
        self._queue.put((self._clock.now_ns(), _SetEspNow(mode)))

    def set_lights(self, on: bool) -> None:
        """Thread-safe. Off keeps this device's lights dark whatever the engine says; the
        safe state on shutdown or a lost link is still RED (by the MCU watchdog)."""
        self._queue.put((self._clock.now_ns(), _SetLights(on)))

    def set_mcu_sound(self, on: bool) -> None:
        """Thread-safe. Switching off also silences whatever the MCU is playing."""
        self._queue.put((self._clock.now_ns(), _SetMcuSound(on)))

    # --- mesh v2 (thread-safe; ignored by a proto 1 device) ---

    @property
    def mesh(self) -> bool:
        """True while connected to a device that speaks serial v2."""
        return self._mesh

    def set_role(self, role: Role) -> None:
        """Remembered and re-sent on every reconnect."""
        self._queue.put((self._clock.now_ns(), _SetRole(role)))

    def set_session(self, session: int) -> None:
        """Change the session of a master/mirror role while running (``$R`` is re-sent)."""
        self._queue.put((self._clock.now_ns(), _SetRoleSession(session)))

    def set_config(self, key: str, value: str) -> None:
        """Store ``$C,key,value`` on the MCU; remembered and re-sent on every reconnect."""
        p.encode(Config(key, value))  # raises ProtocolError for an invalid pair, nothing queued
        self._queue.put((self._clock.now_ns(), _SetConfig(key, value)))

    def forget_radio_keys(self) -> None:
        """One-shot ``$C,mkey`` of all zeros: the ESP32 drops its radio keys and asks a master to
        pair it. Never remembered (a reconnect must not wipe the key pairing just gave it)."""
        self._mesh_send(Config("mkey", "0" * 32))

    def query_config(self) -> None:
        """Ask the MCU for its whole configuration; the answers come to ``on_config``."""
        self._mesh_send(ConfigQuery())

    def send_timer_state(self, state: TimerState) -> None:
        """``$U``: on change; the worker repeats it with every heartbeat (``remaining_ms`` is
        reduced by the time since it was given, unless paused)."""
        now = self._clock.now_ns()
        self._queue.put((now, _SetTimer(state, now)))

    def send_session(self, session: SessionInfo) -> None:
        """``$J``: on change; the worker repeats it every 2 s."""
        self._queue.put((self._clock.now_ns(), _SetSession(session)))

    def pair_open(self, seconds: int) -> None:
        self._mesh_send(PairOpen(seconds))

    def pair_close(self) -> None:
        self._mesh_send(PairClose())

    def pair_accept(self, mac: str, mask: int) -> None:
        self._mesh_send(PairAccept(mac, mask))

    def pair_reject(self, mac: str) -> None:
        self._mesh_send(PairReject(mac))

    def pair_delete(self, mac: str) -> None:
        self._mesh_send(PairDelete(mac))

    def pair_ack(self, mac: str, counter: int, result: int) -> None:
        self._mesh_send(PairAck(mac, counter, result))

    def pair_tx(self, action: int) -> None:
        self._mesh_send(PairTx(action))

    def send_mesh(self, frame: p.Frame) -> None:
        """Any typed serial v2 frame (the pairing registry uses this)."""
        self._mesh_send(frame)

    send_pair_tx = pair_tx  # the name MeshFollower expects

    def _mesh_send(self, frame: p.Frame) -> None:
        p.encode(frame)  # validate on the caller's thread
        self._queue.put((self._clock.now_ns(), _MeshFrame(frame)))

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="serial", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        """Send RED and silence if connected, then close."""
        self._stop.set()
        self._queue.put(_STOP)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    # ---------------------------------------------------------------- thread

    def _set_link(self, state: str) -> None:
        if state != self._link:
            self._link = state
            log.info("link %s", state)
            self._on_link(state)

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            port = self._connect()
            if port is None:
                delay = self._backoff[min(attempt, len(self._backoff) - 1)]
                attempt += 1
                self._stop.wait(delay)
                continue
            attempt = 0
            try:
                self._serve(port)
            finally:
                self._set_link(LINK_DOWN)
                try:
                    port.close()
                except Exception:
                    log.exception("closing port")

    def _connect(self) -> Optional[Port]:
        try:
            port = self._factory()
        except Exception as exc:
            log.debug("open failed: %s", exc)
            return None
        try:
            port.timeout = 0.02
            port.write(p.encode(p.Hello()))
            parser = p.FrameParser()
            deadline = self._clock.now_ns() + round(self._hello_timeout_s * NS_PER_S)
            while self._clock.now_ns() < deadline and not self._stop.is_set():
                for item in parser.feed(port.read(64)):
                    if isinstance(item, p.HelloReply):
                        self.info = item
                        self._mesh = item.proto >= p.PROTOCOL_VERSION_MESH and "R" in item.caps
                        if item.proto not in (p.PROTOCOL_VERSION, p.PROTOCOL_VERSION_MESH):
                            log.warning(
                                "protocol mismatch: device %s, host %s",
                                item.proto,
                                p.PROTOCOL_VERSION_MESH,
                            )
                        return port
        except Exception as exc:
            log.debug("handshake failed: %s", exc)
        with contextlib.suppress(Exception):
            port.close()
        return None

    def _serve(self, port: Port) -> None:
        dead = threading.Event()
        last_ack = [self._clock.now_ns()]
        reader = threading.Thread(
            target=self._read_loop, args=(port, dead, last_ack), name="serial-rx", daemon=False
        )
        reader.start()
        try:
            # Anything queued while we were down is stale; keep only the state it carried.
            self._drain_state_only()
            if not self._write_state(port):
                return
            self._set_link(LINK_UP)
            next_hb = self._clock.now_ns() + self._hb_ns
            self._next_session_ns = self._clock.now_ns() + MESH_SESSION_RESEND_NS
            while not self._stop.is_set() and not dead.is_set():
                wake = min([next_hb, *(due for due, _ in self._resends)])
                timeout = max(0.0, (wake - self._clock.now_ns()) / NS_PER_S)
                item: object = None
                with contextlib.suppress(queue.Empty):
                    item = self._queue.get(timeout=timeout)
                now = self._clock.now_ns()
                if item is _STOP:
                    break
                if isinstance(item, tuple):
                    enq, event = item
                    for frame in self._frames_for(event):
                        if not self._write(port, frame, enq):
                            return
                    now = self._clock.now_ns()
                due = [f for t, f in self._resends if t <= now]
                if due:
                    self._resends = [(t, f) for t, f in self._resends if t > now]
                    for frame in due:
                        if not self._write(port, frame, None):
                            return
                if now >= next_hb:
                    next_hb = now + self._hb_ns
                    self._hb_seq += 1
                    hb = p.Heartbeat(self._hb_seq, self._shown(), self._group)
                    if not self._write(port, p.encode(hb), None):
                        return
                    for frame in self._mesh_repeats(now):
                        if not self._write(port, frame, None):
                            return
                if now - last_ack[0] > self._ack_timeout_ns:
                    log.warning("no heartbeat ACK for %.1f s", (now - last_ack[0]) / NS_PER_S)
                    return
        finally:
            if self._stop.is_set():
                self._safe_state(port)
            dead.set()
            reader.join(timeout=1.0)

    def _read_loop(self, port: Port, dead: threading.Event, last_ack: list[int]) -> None:
        parser = p.FrameParser()
        while not dead.is_set():
            try:
                data = port.read(64)
            except Exception:
                dead.set()
                return
            if not port.is_open:
                dead.set()
                return
            for item in parser.feed(data):
                if isinstance(item, p.Ack):
                    last_ack[0] = self._clock.now_ns()
                elif isinstance(item, p.Button):
                    if self._on_button:
                        self._on_button(item.id, item.down)
                elif isinstance(item, p.EspNowStatus):
                    self.espnow = item
                    if self._on_espnow:
                        self._on_espnow(item)
                elif isinstance(item, p.Error):
                    self.errors.append(item.code)
                    log.warning("device error %s", item.code)
                else:
                    self._dispatch_mesh(item)

    def _dispatch_mesh(self, item: object) -> None:
        if isinstance(item, MeshStatus):
            self.mesh_status = item
            if self._on_mesh_status:
                self._on_mesh_status(item)
        elif isinstance(item, (RosterEntry, RosterGone)):
            if self._on_roster:
                self._on_roster(item)
        elif isinstance(item, (FeedTimer, FeedSound, FeedSession)):
            if self._on_feed:
                self._on_feed(item)
        elif isinstance(item, (PairRequest, PairDone, PairState)):
            if self._on_pairing:
                self._on_pairing(item)
        elif isinstance(item, RemoteCommand):
            if self._on_remote_command:
                self._on_remote_command(item)
        elif isinstance(item, Config):
            self.device_config[item.key] = item.value
            if self._on_config:
                self._on_config(item)

    # ---------------------------------------------------------------- frames

    def _frames_for(self, event: object) -> list[bytes]:
        """Update desired state and return the frames to write for an engine event."""
        if isinstance(event, m.LightChange):
            self._lights = event.light.value
            return [p.encode(p.Lights(self._shown()))]
        if isinstance(event, _SetLights):
            self._lights_on = event.on
            return [p.encode(p.Lights(self._shown()))]
        if isinstance(event, m.Whistle):
            if not self._mcu_sound:
                return []
            return self._whistle_frames(event.count, event.blast_ms, event.gap_ms)
        if isinstance(event, m.Buzzer):
            return [p.encode(p.Buzzer(event.on))] if self._mcu_sound else []
        if isinstance(event, _SetMcuSound):
            self._mcu_sound = event.on
            self._resends.clear()
            if event.on:
                return []
            return [p.encode(p.Whistle(0)), p.encode(p.Buzzer(False))]
        if isinstance(event, _MeshFrame):
            return [p.encode(event.frame)] if self._mesh else []
        if isinstance(event, _SetRoleSession):
            if self._role.master_id is None:
                return []
            self._role = Role(self._role.role, self._role.master_id, event.session)
            return [p.encode(self._role)] if self._mesh else []
        if isinstance(event, _SetRole):
            self._role = event.role
            return [p.encode(event.role)] if self._mesh else []
        if isinstance(event, _SetConfig):
            self._config[event.key] = event.value
            return [p.encode(Config(event.key, event.value))] if self._mesh else []
        if isinstance(event, _SetTimer):
            self._timer = (event.state, event.at_ns)
            return [p.encode(event.state)] if self._mesh else []
        if isinstance(event, _SetSession):
            self._session = event.session
            self._next_session_ns = self._clock.now_ns() + MESH_SESSION_RESEND_NS
            return [p.encode(event.session)] if self._mesh else []
        if isinstance(event, _SetEspNow):
            self._espnow_mode = event.mode
            return [p.encode(p.EspNowMode(event.mode))]
        if isinstance(event, m.Snapshot) and event.group != self._group:
            self._group = event.group
            if self._group:
                return [p.encode(p.Group(self._group))]
        return []

    def _shown(self) -> str:
        return self._lights if self._lights_on else "O"

    @staticmethod
    def _whistle_timing(
        count: int, blast_ms: Optional[int], gap_ms: Optional[int]
    ) -> tuple[Optional[int], Optional[int]]:
        """The engine's blast and gap if the wire accepts them (10-2000 ms, steps of 10)."""
        if count == 0 or blast_ms is None or gap_ms is None:
            return None, None
        for value in (blast_ms, gap_ms):
            if not 10 <= value <= 2000 or value % 10:
                return None, None
        return blast_ms, gap_ms

    def _whistle_frames(
        self, count: int, blast_ms: Optional[int] = None, gap_ms: Optional[int] = None
    ) -> list[bytes]:
        """``$S,n`` (with an id and scheduled repeats if the device can de-duplicate; with explicit
        blast and gap on a serial v2 device)."""
        self._resends.clear()  # a newer sound command supersedes any pending repeat
        if self.info is None or "W" not in self.info.caps:
            return [p.encode(p.Whistle(count))]
        self._whistle_id = self._whistle_id % 255 + 1  # 1..255, never 0
        timing = self._whistle_timing(count, blast_ms, gap_ms) if self._mesh else (None, None)
        frame = p.encode(p.Whistle(count, self._whistle_id, *timing))
        now = self._clock.now_ns()
        self._resends = [(now + ms * 1_000_000, frame) for ms in WHISTLE_RESEND_MS]
        return [frame]

    def _drain_state_only(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is _STOP:
                self._queue.put(_STOP)
                return
            self._frames_for(item[1])  # type: ignore[index]

    def _write_state(self, port: Port) -> bool:
        frames = [p.encode(p.Lights(self._shown()))]
        if self._espnow_mode is not None and self.info is not None and "N" in self.info.caps:
            frames.append(p.encode(p.EspNowMode(self._espnow_mode)))
        if self._group:
            frames.append(p.encode(p.Group(self._group)))
        if self._mesh:
            if self._on_connect is not None and self._role.master_id is not None:
                self._role = self._on_connect(self._role)
            frames.append(p.encode(self._role))
            frames += [p.encode(Config(k, v)) for k, v in self._config.items()]
            frames += self._mesh_repeats(self._clock.now_ns(), force=True)
        return all(self._write(port, f, None) for f in frames)

    def _mesh_repeats(self, now: int, force: bool = False) -> list[bytes]:
        """``$U`` with every heartbeat (remaining time advanced to now) and ``$J`` every 2 s."""
        if not self._mesh:
            return []
        frames: list[bytes] = []
        if self._timer is not None:
            state, at = self._timer
            if not state.flags & FLAG_PAUSED and state.remaining_ms != 0xFFFF_FFFF:
                elapsed_ms = max(0, (now - at) // 1_000_000)
                state = dataclasses.replace(
                    state, remaining_ms=max(0, state.remaining_ms - elapsed_ms)
                )
            frames.append(p.encode(state))
        if self._session is not None and (force or now >= self._next_session_ns):
            self._next_session_ns = now + MESH_SESSION_RESEND_NS
            frames.append(p.encode(self._session))
        return frames

    def _safe_state(self, port: Port) -> None:
        for frame in (p.Lights("R"), p.Whistle(0), p.Buzzer(False)):  # always, whatever the toggle
            try:
                port.write(p.encode(frame))
            except Exception:
                return

    def _write(self, port: Port, data: bytes, enq_ns: Optional[int]) -> bool:
        try:
            port.write(data)
            flush = getattr(port, "flush", None)
            if flush is not None:
                flush()
        except Exception as exc:
            log.warning("write failed: %s", exc)
            return False
        done = self._clock.now_ns()
        if enq_ns is not None:
            self.latencies.append((enq_ns, done))
        log.debug("tx %r", data)
        return True

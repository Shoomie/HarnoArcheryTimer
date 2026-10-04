"""Client side of the IPC: connect, reconnect, clock sync, latest state.

Used by UI clients and by follower cores (which attach ``on_message`` to mirror the leader).

A reader thread parses incoming messages; a writer thread sends outgoing ones, so a
command (the emergency stop in particular) never waits behind a read and a hung peer can
never block the UI thread. All view state (``snapshot`` etc.) is only mutated in
``drain()``, which the UI calls from its main thread.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, Clock, MonotonicClock
from archerytimer.core.models import Snapshot
from archerytimer.ipc.clocksync import OffsetEstimator
from archerytimer.ipc.messages import Message, MessageError, ping_msg, snapshot_from_dict
from archerytimer.ipc.transport import Connection, ConnectionClosed

log = logging.getLogger("archerytimer.ipc.link")

_STOP = object()


class CoreLink:
    def __init__(
        self,
        connect: Callable[[], Connection],
        wake: Optional[Callable[[], None]] = None,
        clock: Optional[Clock] = None,
        *,
        on_message: Optional[Callable[[Message], None]] = None,
        on_connect: Optional[Callable[[Callable[[Message], bool]], None]] = None,
        ping_interval_s: float = 2.0,
        backoff_s: tuple[float, ...] = (0.2, 0.5, 1.0),
    ) -> None:
        self._connect = connect
        self._wake = wake or (lambda: None)
        self._on_message = on_message
        self._on_connect = on_connect  # called on the link thread after each connect
        self._clock: Clock = clock or MonotonicClock()
        self._ping_ns = round(ping_interval_s * NS_PER_S)
        self._backoff = backoff_s
        self._inbox: queue.SimpleQueue[Message] = queue.SimpleQueue()
        self._out: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._conn: Optional[Connection] = None
        self.estimator = OffsetEstimator()

        # Written by the link thread (single attribute stores), read by the UI thread.
        self.connected = False
        self.ever_connected = False
        self.lost_since_ns: Optional[int] = None

        # Mutated only in drain(), on the UI thread.
        self.snapshot: Optional[Snapshot] = None
        self.hello: Optional[Message] = None
        self.hw_link = ""  # "up" / "down" / "" (unknown)
        self.upstream_ok = True  # False when a follower core has lost its leader
        self.upstream_via = ""  # "radio" when the timer comes over the ESP32 radio only
        self.espnow: Optional[dict[str, Any]] = None
        self.audio: Optional[dict[str, Any]] = None  # the core's sound state
        self.node: Optional[dict[str, Any]] = None  # the core's network role state
        self.roster: Optional[dict[str, Any]] = (
            None  # the timer network (devices, master, conflict)
        )
        self.remotes: Optional[dict[str, Any]] = None  # paired remotes and the pairing window
        self.followers: Optional[dict[str, Any]] = None  # leader: followers and their access
        self.follower: Optional[dict[str, Any]] = None  # follower core: this device's own access
        self.leader_rtt_ms: Optional[int] = None  # follower core: round trip to the main timer
        self.leader_offset_ms: Optional[int] = None  # follower core: main timer clock minus ours
        self.hw_fw = ""
        self.hw_chip = ""

    # ---------------------------------------------------------------- UI thread

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ui-link", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._out.put(_STOP)
        conn = self._conn
        if conn is not None:
            conn.close()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def send(self, msg: Message) -> bool:
        """Queue a message for the core. False if there is no connection (it is dropped)."""
        if not self.connected:
            return False
        self._out.put(msg)
        return True

    def drain(self) -> bool:
        """Apply queued messages. True if the visible state changed."""
        changed = False
        while True:
            try:
                msg = self._inbox.get_nowait()
            except queue.Empty:
                return changed
            kind = msg.get("type")
            try:
                if kind == "state":
                    self.snapshot = snapshot_from_dict(msg["state"])
                    changed = True
                elif kind == "hello":
                    self.hello = msg
                    changed = True
                elif kind == "audio":
                    self.audio = {k: v for k, v in msg.items() if k not in ("type", "v")}
                    changed = True
                elif kind == "node":
                    self.node = {k: v for k, v in msg.items() if k not in ("type", "v")}
                    changed = True
                elif kind in ("roster", "remotes", "followers", "follower"):
                    setattr(self, kind, {k: v for k, v in msg.items() if k not in ("type", "v")})
                    changed = True
                elif kind == "link":
                    self.hw_link = str(msg.get("status", ""))
                    self.upstream_ok = msg.get("upstream", "up") != "down"
                    self.upstream_via = str(msg.get("via", "") or "")
                    self.hw_fw = str(msg.get("fw", ""))
                    self.hw_chip = str(msg.get("chip", ""))
                    esp = msg.get("espnow")
                    self.espnow = esp if isinstance(esp, dict) else None
                    rtt, off = msg.get("leader_rtt_ms"), msg.get("leader_offset_ms")
                    self.leader_rtt_ms = rtt if isinstance(rtt, int) else None
                    self.leader_offset_ms = off if isinstance(off, int) else None
                    changed = True
            except (KeyError, MessageError) as exc:
                log.warning("bad %s message: %s", kind, exc)

    @property
    def rtt_ms(self) -> Optional[int]:
        """Best recent round trip to the core, None before the first clock sample."""
        est = self.estimator
        return round(est.rtt_ns / 1e6) if est.synced else None

    @property
    def offset_ms(self) -> Optional[int]:
        """Core clock minus ours in ms, None before the first clock sample."""
        est = self.estimator
        return round(est.offset_ns / 1e6) if est.synced else None

    def sequence_names(self, sequence_id: str) -> dict[str, str]:
        if self.hello is None:
            return {}
        names = self.hello.get("sequences", {}).get(sequence_id, {})
        return dict(names) if isinstance(names, dict) else {}

    def timings(self, sequence_id: str) -> dict[str, float]:
        """prep_s / shoot_s / warn_s of a sequence, from the core's hello."""
        if self.hello is None:
            return {}
        info = self.hello.get("timings", {}).get(sequence_id, {})
        return {k: float(v) for k, v in info.items()} if isinstance(info, dict) else {}

    def sequence_ids(self) -> list[str]:
        if self.hello is None:
            return []
        return list(self.hello.get("sequences", {}))

    # ---------------------------------------------------------------- link thread

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                conn = self._connect()
            except ConnectionClosed:
                delay = self._backoff[min(attempt, len(self._backoff) - 1)]
                attempt += 1
                self._stop.wait(delay)
                continue
            attempt = 0
            self._session(conn)

    def _session(self, conn: Connection) -> None:
        self._conn = conn
        self.estimator.reset()
        self.lost_since_ns = None
        self.connected = True
        self.ever_connected = True
        log.info("connected to core")
        self._wake()
        # drop stale outgoing messages from before this connection
        while True:
            try:
                self._out.get_nowait()
            except queue.Empty:
                break
        writer = threading.Thread(target=self._write_loop, args=(conn,), name="ui-link-tx")
        writer.start()
        if self._on_connect is not None:
            try:
                self._on_connect(self.send)  # e.g. a follower core sends ``join``
            except Exception:
                log.exception("on_connect failed")
        try:
            self._read_loop(conn)
        finally:
            self.connected = False
            self.lost_since_ns = self._clock.now_ns()
            self._conn = None
            conn.close()
            self._out.put(_STOP)
            writer.join(timeout=3.0)
            while True:  # remove our own _STOP so the next session's writer is not killed
                try:
                    if self._out.get_nowait() is not _STOP:
                        continue
                except queue.Empty:
                    break
            if not self._stop.is_set():
                log.info("lost connection to core")
            self._wake()

    def _read_loop(self, conn: Connection) -> None:
        next_ping = self._clock.now_ns()
        burst = 5  # a quick burst at connect gives a usable offset almost immediately
        ping_id = 0
        while not self._stop.is_set():
            now = self._clock.now_ns()
            if now >= next_ping:
                ping_id += 1
                self._out.put(ping_msg(ping_id, now))
                burst -= 1
                next_ping = now + (NS_PER_S // 10 if burst > 0 else self._ping_ns)
            try:
                msg = conn.recv(0.05)
            except ConnectionClosed:
                return
            if msg is None:
                continue
            if msg.get("type") == "pong":
                try:
                    self.estimator.add(int(msg["t0"]), int(msg["t1"]), self._clock.now_ns())
                except (KeyError, TypeError, ValueError):
                    log.warning("malformed pong")
                self._notify(msg)
                continue
            self._inbox.put(msg)
            self._notify(msg)
            self._wake()

    def _notify(self, msg: Message) -> None:
        if self._on_message is not None:
            try:
                self._on_message(msg)
            except Exception:
                log.exception("on_message failed for %r", msg.get("type"))

    def _write_loop(self, conn: Connection) -> None:
        while True:
            item = self._out.get()
            if item is _STOP:
                return
            try:
                conn.send(item)  # type: ignore[arg-type]
            except ConnectionClosed:
                conn.close()
                return

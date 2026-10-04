"""IPC server and client helper, transport-agnostic.

Server: every client gets its own outgoing queue and writer thread, so ``publish`` (called
from the engine thread) only does a queue put and can never block on a slow or dead UI.
On connect a client receives ``hello``, the latest ``link`` and the latest ``state``, so a
restarted UI recovers exactly.
"""

from __future__ import annotations

import ipaddress
import logging
import queue
import threading
from typing import Any, Callable, Optional

from archerytimer.common.clock import Clock, MonotonicClock
from archerytimer.ipc.messages import Message, pong_msg
from archerytimer.ipc.transport import Connection, ConnectionClosed, Listener

log = logging.getLogger("archerytimer.ipc")

MAX_QUEUED = 1000  # a client this far behind is dropped; it can reconnect and resync


def _is_loopback(peer: Optional[str]) -> bool:
    """No peer address (in-process) or a loopback address: the operator's own machine."""
    if not peer:
        return True
    try:
        addr = ipaddress.ip_address(peer.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback


class ClientInfo:
    """One connected client as the message owner sees it: who (``peer``, ``is_local``), a place to
    keep per-connection state (``ctx``) and a non-blocking ``send`` to answer this client alone."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.out: queue.SimpleQueue[Optional[Message]] = queue.SimpleQueue()
        self.dead = False
        peer = getattr(conn, "peer", None)
        self.peer: Optional[str] = str(peer) if peer else None
        self.is_local = _is_loopback(self.peer)
        self.ctx: dict[str, Any] = {}
        self._enqueue: Callable[[ClientInfo, Message], None] = lambda _c, _m: None

    def send(self, msg: Message) -> None:
        self._enqueue(self, msg)


_Client = ClientInfo


class IpcServer:
    def __init__(
        self,
        listener: Listener,
        hello: Message,
        on_message: Callable[[Message], None],
        clock: Optional[Clock] = None,
        *,
        gate: Optional[Callable[[ClientInfo, Message], bool]] = None,
        on_disconnect: Optional[Callable[[ClientInfo], None]] = None,
    ) -> None:
        self._clock: Clock = clock or MonotonicClock()
        self._listener = listener
        self._hello = hello
        self._on_message = on_message
        self._gate = gate  # (client, msg) -> pass it on? Every message except ping goes through it.
        self._on_disconnect = on_disconnect
        self._lock = threading.Lock()
        self._clients: list[_Client] = []
        self._latest: dict[str, Message] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def latest_state(self) -> Optional[Message]:
        with self._lock:
            return self._latest.get("state")

    def set_hello(self, hello: Message) -> None:
        """Replace the greeting sent to future clients (a follower learns the leader's)."""
        with self._lock:
            self._hello = hello

    def start(self) -> None:
        t = threading.Thread(target=self._accept_loop, name="ipc-accept", daemon=False)
        t.start()
        self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        self._listener.close()
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            self._drop(c)
        for t in self._threads:
            t.join(timeout=2.0)

    def publish(self, msg: Message) -> None:
        """Remember the latest ``state``/``link`` for new clients and fan out. Never blocks."""
        with self._lock:
            if msg["type"] in ("state", "link", "audio", "node", "followers"):
                self._latest[msg["type"]] = msg
            clients = list(self._clients)
        for c in clients:
            self._enqueue(c, msg)

    # ---------------------------------------------------------------- internals

    def _enqueue(self, c: _Client, msg: Message) -> None:
        if c.dead:
            return
        if c.out.qsize() > MAX_QUEUED:
            log.warning("ipc client too slow, dropping")
            self._drop(c)
            return
        c.out.put(msg)

    def _drop(self, c: _Client) -> None:
        with self._lock:
            if c.dead:
                return
            c.dead = True
            if c in self._clients:
                self._clients.remove(c)
        c.out.put(None)  # wake the writer
        c.conn.close()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            conn = self._listener.accept(0.1)
            if conn is None:
                continue
            c = ClientInfo(conn)
            c._enqueue = self._enqueue
            with self._lock:
                # Queue hello, link, state under the lock so no publish slips in between.
                c.out.put(self._hello)
                for kind in ("link", "audio", "node", "followers", "state"):
                    if kind in self._latest:
                        c.out.put(self._latest[kind])
                self._clients.append(c)
            for target, name in ((self._writer, "ipc-tx"), (self._reader, "ipc-rx")):
                t = threading.Thread(target=target, args=(c,), name=name, daemon=False)
                t.start()
                self._threads.append(t)
            log.info("ipc client connected")

    def _writer(self, c: _Client) -> None:
        while True:
            msg = c.out.get()
            if msg is None:
                return
            try:
                c.conn.send(msg)
            except ConnectionClosed:
                self._drop(c)
                return

    def _reader(self, c: _Client) -> None:
        while not c.dead and not self._stop.is_set():
            try:
                msg = c.conn.recv(0.2)
            except ConnectionClosed:
                break
            if msg is None:
                continue
            if msg.get("type") == "ping":
                try:
                    self._enqueue(c, pong_msg(msg["id"], msg["t0"], self._clock.now_ns()))
                except KeyError:
                    log.warning("malformed ping")
                continue
            if self._gate is not None:
                try:
                    if not self._gate(c, msg):
                        continue
                except Exception:
                    log.exception("gate for %r", msg.get("type"))
                    continue  # fail closed
            if msg.get("type") in ("cmd", "settings"):
                try:
                    self._on_message(msg)
                except Exception:
                    log.exception("handling %r", msg.get("type"))
            else:
                log.warning("ignoring unknown message type %r", msg.get("type"))
        self._drop(c)
        if self._on_disconnect is not None:
            try:
                self._on_disconnect(c)
            except Exception:
                log.exception("on_disconnect")
        log.info("ipc client disconnected")


class IpcClient:
    """Minimal client for the UI and tests: a reader thread feeding a queue."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn
        self.messages: queue.SimpleQueue[Message] = queue.SimpleQueue()
        self.closed = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ipc-client", daemon=False)
        self._thread.start()

    def send(self, msg: Message) -> None:
        self._conn.send(msg)

    def get(self, timeout: float = 2.0) -> Optional[Message]:
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._conn.close()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            try:
                msg = self._conn.recv(0.2)
            except ConnectionClosed:
                self.closed.set()
                return
            if msg is not None:
                self.messages.put(msg)

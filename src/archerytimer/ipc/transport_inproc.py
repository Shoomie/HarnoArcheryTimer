"""In-process transport: same interface as sockets, for tests and single-process use."""

from __future__ import annotations

import queue
from typing import Optional

from archerytimer.ipc.messages import Message
from archerytimer.ipc.transport import Connection, ConnectionClosed

_CLOSED = object()


class InprocConnection:
    def __init__(self, rx: queue.SimpleQueue[object], tx: queue.SimpleQueue[object]) -> None:
        self._rx = rx
        self._tx = tx
        self._closed = False

    def send(self, msg: Message) -> None:
        if self._closed:
            raise ConnectionClosed
        self._tx.put(msg)

    def recv(self, timeout: float) -> Optional[Message]:
        try:
            item = self._rx.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _CLOSED:
            self._rx.put(_CLOSED)  # keep raising on later calls
            raise ConnectionClosed
        return item  # type: ignore[return-value]

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._tx.put(_CLOSED)
            self._rx.put(_CLOSED)


class InprocListener:
    def __init__(self) -> None:
        self._pending: queue.SimpleQueue[Optional[Connection]] = queue.SimpleQueue()
        self._closed = False

    def connect(self) -> Connection:
        """Client side: returns the client's end; the server's end goes to ``accept``."""
        if self._closed:
            raise ConnectionClosed
        c2s: queue.SimpleQueue[object] = queue.SimpleQueue()
        s2c: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._pending.put(InprocConnection(rx=c2s, tx=s2c))
        return InprocConnection(rx=s2c, tx=c2s)

    def accept(self, timeout: float) -> Optional[Connection]:
        try:
            return self._pending.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._closed = True

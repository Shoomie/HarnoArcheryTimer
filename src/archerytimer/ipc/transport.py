"""Transport interface. Two implementations: sockets (production) and in-process (tests)."""

from __future__ import annotations

from typing import Optional, Protocol

from archerytimer.ipc.messages import Message


class ConnectionClosed(Exception):
    pass


class Connection(Protocol):
    def send(self, msg: Message) -> None:
        """Raises ``ConnectionClosed`` if the peer is gone."""
        ...

    def recv(self, timeout: float) -> Optional[Message]:
        """Next message, or None after ``timeout`` s. Raises ``ConnectionClosed``."""
        ...

    def close(self) -> None: ...


class Listener(Protocol):
    def accept(self, timeout: float) -> Optional[Connection]:
        """A new client connection, or None after ``timeout`` s."""
        ...

    def close(self) -> None: ...

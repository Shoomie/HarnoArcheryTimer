"""Localhost TCP transport, newline-delimited JSON. Portable to Windows, Linux and macOS."""

from __future__ import annotations

import contextlib
import logging
import select
import socket
from typing import Optional

from archerytimer.ipc.messages import Message, MessageError, decode_line, encode_line
from archerytimer.ipc.transport import ConnectionClosed

log = logging.getLogger("archerytimer.ipc")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SEND_TIMEOUT_S = 2.0  # a peer that cannot take data this long is considered dead
MAX_LINE = 1 << 20


class SocketConnection:
    def __init__(self, sock: socket.socket) -> None:
        sock.settimeout(SEND_TIMEOUT_S)
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self.peer: Optional[str] = None  # remote IP, for the server's local/remote decision
        with contextlib.suppress(OSError, IndexError):
            self.peer = str(sock.getpeername()[0])
        self._buf = bytearray()
        self._closed = False

    def send(self, msg: Message) -> None:
        if self._closed:
            raise ConnectionClosed
        try:
            self._sock.sendall(encode_line(msg))
        except OSError as exc:
            self.close()
            raise ConnectionClosed from exc

    def recv(self, timeout: float) -> Optional[Message]:
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = bytes(self._buf[:nl])
                del self._buf[: nl + 1]
                if not line.strip():
                    continue
                try:
                    return decode_line(line)
                except MessageError as exc:
                    log.warning("dropping bad message: %s", exc)
                    continue
            if self._closed:
                raise ConnectionClosed
            try:
                ready, _, _ = select.select([self._sock], [], [], timeout)
                if not ready:
                    return None
                data = self._sock.recv(65536)
            except (OSError, ValueError) as exc:
                self.close()
                raise ConnectionClosed from exc
            if not data:
                self.close()
                raise ConnectionClosed
            self._buf += data
            if len(self._buf) > MAX_LINE:
                self.close()
                raise ConnectionClosed
            timeout = 0.0  # we got data; only loop again for a complete line without waiting

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            with contextlib.suppress(OSError):
                self._sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                self._sock.close()


class SocketListener:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(8)
        self.address: tuple[str, int] = self._sock.getsockname()[:2]

    def accept(self, timeout: float) -> Optional[SocketConnection]:
        try:
            ready, _, _ = select.select([self._sock], [], [], timeout)
            if not ready:
                return None
            conn, _ = self._sock.accept()
        except (OSError, ValueError):
            return None
        return SocketConnection(conn)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()


def connect_socket(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 2.0
) -> SocketConnection:
    try:
        return SocketConnection(socket.create_connection((host, port), timeout=timeout))
    except OSError as exc:
        raise ConnectionClosed from exc

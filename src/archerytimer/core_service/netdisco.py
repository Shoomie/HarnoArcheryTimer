"""Find the other timers on the local network: EVERY core broadcasts a small UDP beacon (beacon
v2: role, name, id, who it follows, session state, radio status, version) and every core listens.
Lets a volunteer pick "the main timer" from a list instead of typing an address, and lets the
roster list all devices and notice two leaders. The old beacon (leaders only, ``app``/``port``/
``name``) still parses and counts as a leader.

Best effort and never fatal: a network without broadcast just shows an empty list (the leader
address can still be given with ``--leader``). Nothing here touches timing.
"""

from __future__ import annotations

import contextlib
import json
import logging
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from archerytimer.common.compat import SLOTS

log = logging.getLogger("archerytimer.netdisco")

BEACON_PORT = 8766
BEACON_PERIOD_S = 2.0
LEADER_TTL_S = 6.0  # a core not heard for this long drops off the list
INSTANCE_TTL_S = LEADER_TTL_S
BEACON_VERSION = 2
_APP = "archerytimer"
BEACON_ROLES = ("leader", "follower", "alone")
BEACON_STATES = ("idle", "running", "waiting", "finished", "")


@dataclass(frozen=True, **SLOTS)
class Instance:
    """One core heard on the LAN (``addr`` = host:port of its IPC server)."""

    id: str
    name: str
    addr: str
    role: str = "leader"
    follows: str = ""
    state: str = ""
    radio: str = ""
    version: str = ""


def leader_conflict(names: list[str]) -> list[str]:
    """Names of the leaders involved when there is more than one (else empty)."""
    return sorted(names) if len(names) > 1 else []


class Beacon:
    """Announce this core to the LAN every couple of seconds (``tcp_port`` = its IPC port).

    ``update`` changes the dynamic fields (role, follows, session state, radio status) from any
    thread; the next beacon carries them.
    """

    def __init__(
        self,
        tcp_port: int,
        name: str = "",
        target: tuple[str, int] = ("255.255.255.255", BEACON_PORT),
        *,
        node_id: str = "",
        role: str = "leader",
        follows: str = "",
        state: str = "",
        radio: str = "",
        version: str = "",
    ) -> None:
        self._port = tcp_port
        self._fields: dict[str, Any] = {
            "name": name or socket.gethostname(),
            "id": node_id,
            "role": role,
            "follows": follows,
            "state": state,
            "radio": radio,
            "ver": version,
        }
        self._lock = threading.Lock()
        self._target = target
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def update(self, **fields: Any) -> None:
        """Change ``name``, ``role``, ``follows``, ``state``, ``radio`` or ``ver``."""
        with self._lock:
            self._fields.update({k: v for k, v in fields.items() if k in self._fields})

    def payload(self) -> bytes:
        with self._lock:
            body = {"app": _APP, "v": BEACON_VERSION, "port": self._port, **self._fields}
        return json.dumps(body).encode()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="beacon")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            while not self._stop.is_set():
                with contextlib.suppress(OSError):
                    sock.sendto(self.payload(), self._target)
                self._stop.wait(BEACON_PERIOD_S)
        finally:
            sock.close()


class LeaderBrowser:
    """Listener side: the cores heard recently. ``leaders()`` keeps the old
    ``{"name", "addr"}`` shape (leaders only); ``instances()`` lists every core."""

    def __init__(
        self,
        port: int = BEACON_PORT,
        on_change: Optional[Callable[[], None]] = None,
        now: Callable[[], float] = time.monotonic,
        own_id: str = "",
    ) -> None:
        self._port = port
        self.on_change = on_change or (lambda: None)
        self._now = now
        self._own_id = own_id  # our own beacon comes back on the broadcast: ignore it
        self._lock = threading.Lock()
        self._seen: dict[str, tuple[Instance, float]] = {}  # key -> (instance, last heard)
        self._listed: tuple[Instance, ...] = ()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def instances(self) -> list[Instance]:
        cutoff = self._now() - INSTANCE_TTL_S
        with self._lock:
            return [i for _k, (i, t) in sorted(self._seen.items()) if t >= cutoff]

    def leaders(self) -> list[dict[str, str]]:
        return [{"name": i.name, "addr": i.addr} for i in self.instances() if i.role == "leader"]

    def conflict(self, own_leader_name: str = "") -> list[str]:
        """Names of the leaders beaconing (plus ours if we are one) when there are two or more."""
        names = [i.name for i in self.instances() if i.role == "leader"]
        if own_leader_name:
            names.append(own_leader_name)
        return leader_conflict(names)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="leader-browser")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def hear(self, data: bytes, host: str) -> None:
        """Process one datagram (public so tests need no sockets)."""
        try:
            info = json.loads(data)
            if info.get("app") != _APP:
                return
            addr = f"{host}:{int(info['port'])}"
            name = str(info.get("name", ""))[:40]
            ident = str(info.get("id", "") or "")[:40]
            role = info.get("role", "leader")  # old beacons were leaders only
            state = info.get("state", "")
            inst = Instance(
                id=ident or addr,
                name=name,
                addr=addr,
                role=role if role in BEACON_ROLES else "alone",
                follows=str(info.get("follows", "") or "")[:40],
                state=state if state in BEACON_STATES else "",
                radio=str(info.get("radio", "") or "")[:20],
                version=str(info.get("ver", "") or "")[:20],
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        if self._own_id and inst.id == self._own_id:
            return
        with self._lock:
            self._seen[inst.id] = (inst, self._now())
        self.notify()

    def notify(self) -> None:
        """Tell the owner if the list changed (a core appeared, changed or expired)."""
        listed = tuple(self.instances())
        if listed != self._listed:
            self._listed = listed
            self.on_change()

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self._port))
            sock.settimeout(0.5)
        except OSError as exc:
            log.info("leader discovery unavailable: %s", exc)
            sock.close()
            return
        try:
            while not self._stop.is_set():
                try:
                    data, (host, _port) = sock.recvfrom(512)
                    self.hear(data, host)
                except socket.timeout:
                    self.notify()
                except OSError:
                    self._stop.wait(0.5)
        finally:
            sock.close()

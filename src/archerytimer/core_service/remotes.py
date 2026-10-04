"""Paired wireless remotes: the registry, the pairing window and who may do what.

The ESP32 receives a remote's radio frame, checks its signature and passes ``RemoteCommand`` to
the host; the host decides (this module) and answers with a ``PairAck`` (result 0 done, 1
denied). Emergency is always allowed for a paired remote (``mesh_types.mask_allows``). An
unknown remote, an action outside its permissions or a remote that sends too fast is denied.

Plain values and callbacks only: ``send`` receives the typed ``mesh_types`` frames meant for the
MCU (``PairOpen``, ``PairClose``, ``PairAccept``, ``PairReject``, ``PairDelete``, ``PairAck``);
the owner decides how they reach the serial worker. Time comes from an injected clock (window,
rate limit) and an injected wall clock (the persisted ``last_seen``). Nothing here touches timing.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, Clock
from archerytimer.common.compat import SLOTS
from archerytimer.core.models import Command
from archerytimer.core_service.inputs import action_to_command
from archerytimer.hardware import mesh_types as mt
from archerytimer.ipc.messages import Message, remotes_msg

log = logging.getLogger("archerytimer.core.remotes")

FILE_NAME = "core_remotes.json"
DEFAULT_PAIR_SECONDS = 60
MAX_PAIR_SECONDS = 300
RATE_LIMIT_COUNT = 5  # non-emergency commands per remote ...
RATE_LIMIT_WINDOW_NS = 1 * NS_PER_S  # ... per second
MAX_PENDING = 8
DISCOVER_SECONDS = (
    120  # one firmware window while the operator looks for new devices (max of $P,open)
)
DISCOVER_RENEW_LEFT_S = 20  # renew the window when this little is left and nobody is waiting
DISCOVER_MAX_S = 600  # discovery stops by itself this long after the last "search" press
PENDING_STALE_S = 25  # a waiting device that stopped asking (powered off) leaves the list
LAST_SEEN_SAVE_S = 60.0  # last_seen alone is written to disk at most this often
RESULT_DONE, RESULT_DENIED = 0, 1


def mask_from_perms(perms: list[str]) -> int:
    """Permission mask from action names (unknown names ignored). Emergency is implicit."""
    mask = 0
    for name in perms:
        code = mt.ACTION_CODES.get(name)
        if code is not None:
            mask |= 1 << (code - 1)
    return mask | mt.EMERGENCY_MASK_BIT


def perms_from_mask(mask: int) -> list[str]:
    return [name for code, name in mt.ACTIONS.items() if mt.mask_allows(mask, code)]


@dataclass(frozen=True, **SLOTS)
class Remote:
    mac: str
    name: str
    mask: int
    last_seen: float = 0.0  # wall-clock epoch seconds, 0 = never


@dataclass(frozen=True, **SLOTS)
class Pending:
    mac: str
    name: str
    caps: str
    seen_ns: int = 0  # clock time of its latest request (the MCU repeats it every ~10 s)


class RemoteStore:
    """``core_remotes.json``: list of remotes, atomic write, a damaged file is ignored."""

    def __init__(self, path: Optional[Path]) -> None:
        self.path = path

    def load(self) -> dict[str, Remote]:
        if self.path is None or not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            result: dict[str, Remote] = {}
            for item in data["remotes"]:
                mac = str(item["mac"])
                result[mac] = Remote(
                    mac,
                    str(item.get("name", ""))[:40] or mac,
                    int(item["mask"]) & 0x7F | mt.EMERGENCY_MASK_BIT,
                    float(item.get("last_seen", 0.0)),
                )
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            log.warning("ignoring damaged remotes file %s: %r", self.path, exc)
            return {}

    def save(self, remotes: dict[str, Remote]) -> None:
        if self.path is None:
            return
        try:
            body = {
                "remotes": [
                    {"mac": r.mac, "name": r.name, "mask": r.mask, "last_seen": r.last_seen}
                    for r in remotes.values()
                ]
            }
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("cannot save remotes: %s", exc)


class RemoteRegistry:
    def __init__(
        self,
        clock: Clock,
        *,
        store: Optional[RemoteStore] = None,
        send: Optional[Callable[[Any], None]] = None,
        on_change: Optional[Callable[[], None]] = None,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        self._store = store or RemoteStore(None)
        self._send = send or (lambda _f: None)
        self._on_change = on_change or (lambda: None)
        self._wall = wall
        self._remotes = self._store.load()
        self._pending: dict[str, Pending] = {}
        self._open_until_ns: Optional[int] = None
        self._mcu_open = False
        self._ignored: set[str] = set()  # rejected during this search: not listed again
        self._discover_until_ns: Optional[int] = (
            None  # keep the window open (and renew it) until then
        )
        self._recent: dict[str, deque[int]] = {}  # mac -> times of recent commands
        self._last_counter: dict[str, tuple[int, int]] = {}  # mac -> (counter, result)
        self._saved_seen_at = 0.0

    # ---------------------------------------------------------------- pairing window

    def set_send(self, send: Callable[[Any], None]) -> None:
        self._send = send

    def set_on_change(self, callback: Callable[[], None]) -> None:
        self._on_change = callback

    @property
    def window_active(self) -> bool:
        """True from open until ``tick``/``close_pairing`` ran, also just after it expired."""
        return self._open_until_ns is not None

    @property
    def pairing_open(self) -> bool:
        return self._open_until_ns is not None and self._clock.now_ns() < self._open_until_ns

    @property
    def seconds_left(self) -> int:
        if not self.pairing_open:
            return 0
        assert self._open_until_ns is not None
        left = self._open_until_ns - self._clock.now_ns()
        return -(-left // NS_PER_S)  # round up: "1" until it really ends

    @property
    def discovering(self) -> bool:
        return self._discover_until_ns is not None

    @property
    def needs_tick(self) -> bool:
        return self.window_active or self.discovering

    def open_pairing(
        self, seconds: int = DEFAULT_PAIR_SECONDS, *, discover: bool = False, renew: bool = False
    ) -> None:
        """Open the MCU's pairing window. ``discover`` keeps it open (renewed by ``tick``) so
        devices that power on later still show up, for at most ``DISCOVER_MAX_S``."""
        seconds = max(1, min(int(seconds), MAX_PAIR_SECONDS))
        if not renew:
            self._ignored.clear()
        if discover:
            self._discover_until_ns = self._clock.now_ns() + DISCOVER_MAX_S * NS_PER_S
        self._pending.clear()  # a new window has a new key pair: old requests cannot be answered
        self._open_until_ns = self._clock.now_ns() + seconds * NS_PER_S
        log.info("pairing window requested for %d s (discover=%s)", seconds, discover)
        self._send(mt.PairOpen(seconds))
        self._on_change()

    def close_pairing(self) -> None:
        self._discover_until_ns = None
        self._ignored.clear()
        was_open = self._open_until_ns is not None
        self._open_until_ns = None
        self._pending.clear()  # requests are only answered while the window is open
        if was_open:
            self._send(mt.PairClose())
            self._on_change()

    def tick(self) -> None:
        """Once a second while ``needs_tick``: drop waiting devices that went quiet, renew the
        discovery window, or close an expired one."""
        now = self._clock.now_ns()
        if self._discover_until_ns is not None:
            if now >= self._discover_until_ns:
                self.close_pairing()
                return
            stale = [
                m for m, p in self._pending.items() if now - p.seen_ns > PENDING_STALE_S * NS_PER_S
            ]
            for mac in stale:
                del self._pending[mac]
            if stale:
                self._on_change()
            if not self.pairing_open and self._pending:
                self._pending.clear()  # the window ended under them: they must ask again
                self._on_change()
            if not self._pending and (
                not self.pairing_open or self.seconds_left <= DISCOVER_RENEW_LEFT_S
            ):
                until = self._discover_until_ns
                self.open_pairing(DISCOVER_SECONDS, renew=True)
                self._discover_until_ns = until  # renewing never extends the search
            return
        if self._open_until_ns is not None and not self.pairing_open:
            self.close_pairing()

    def on_pair_state(self, state: mt.PairState) -> None:
        """The MCU's own view of its pairing window (it has its own timeout)."""
        if state.open != self._mcu_open:  # log the change, not the once-a-second countdown
            self._mcu_open = state.open
            log.info("MCU pairing window %s", "open" if state.open else "closed")
        if not state.open and self._open_until_ns is not None:
            self._open_until_ns = None
            self._pending.clear()
            self._on_change()
        elif state.open:
            self._open_until_ns = self._clock.now_ns() + max(0, state.seconds_left) * NS_PER_S
            self._on_change()

    def on_request(self, req: mt.PairRequest) -> None:
        """A remote asks to pair: queued for the operator, only while the window is open."""
        if not self.pairing_open:
            self._send(mt.PairReject(req.mac))
            return
        if req.mac in self._ignored:
            return
        if req.mac not in self._pending and len(self._pending) >= MAX_PENDING:
            return
        known = req.mac in self._pending
        if not known:
            log.info("radio device %s (%s) asks to join", req.mac, req.name)
        self._pending[req.mac] = Pending(
            req.mac, req.name[:40] or req.mac, req.caps, self._clock.now_ns()
        )
        if not known:
            self._on_change()

    def accept(self, mac: str, perms: list[str]) -> bool:
        pend = self._pending.pop(mac, None)
        if pend is None:
            return False
        mask = mask_from_perms(perms)
        self._remotes[mac] = Remote(mac, pend.name, mask, self._wall())
        self._store.save(self._remotes)
        self._send(mt.PairAccept(mac, mask))
        self._on_change()
        return True

    def reject(self, mac: str) -> bool:
        if self._pending.pop(mac, None) is None:
            return False
        self._ignored.add(mac)
        self._send(mt.PairReject(mac))
        self._on_change()
        return True

    def on_done(self, done: mt.PairDone) -> None:
        """The MCU finished pairing a remote (its key exchange): refresh the listing."""
        r = self._remotes.get(done.mac)
        if r is not None:
            self._remotes[done.mac] = replace(r, last_seen=self._wall())
        self._on_change()

    # ---------------------------------------------------------------- registry

    def remove(self, mac: str) -> bool:
        if self._remotes.pop(mac, None) is None:
            return False
        self._recent.pop(mac, None)
        self._last_counter.pop(mac, None)
        self._store.save(self._remotes)
        self._send(mt.PairDelete(mac))
        self._on_change()
        return True

    def set_perms(self, mac: str, perms: list[str]) -> bool:
        r = self._remotes.get(mac)
        if r is None:
            return False
        self._remotes[mac] = replace(r, mask=mask_from_perms(perms))
        self._store.save(self._remotes)
        self._on_change()
        return True

    def get(self, mac: str) -> Optional[Remote]:
        return self._remotes.get(mac)

    def macs(self) -> list[str]:
        return sorted(self._remotes)

    # ---------------------------------------------------------------- commands

    def authorize(self, rc: mt.RemoteCommand) -> tuple[Optional[Command], int]:
        """Decide one remote command: the engine command (or None) and the ack result."""
        remote = self._remotes.get(rc.mac)
        last = self._last_counter.get(rc.mac)
        if last is not None and last[0] == rc.counter:
            return None, last[1]  # radio retransmit: same answer, do not run it twice
        now = self._clock.now_ns()
        command: Optional[Command] = None
        result = RESULT_DENIED
        action = mt.ACTIONS.get(rc.action)
        allowed = (
            remote is not None
            and action is not None
            and mt.mask_allows(remote.mask, rc.action)
            and (rc.action == mt.EMERGENCY_ACTION or self._rate_ok(rc.mac, now))
        )
        if remote is not None and action is not None and allowed:
            command = action_to_command(action)
            if command is not None:
                source = f"remote:{remote.name}"
                command = Command(command.name, {**command.args, "source": source})
                log.info("remote %s: %s accepted", remote.name, action)
                result = RESULT_DONE
        if remote is None:
            log.warning("command from unknown remote %s denied", rc.mac)
        elif result == RESULT_DENIED:
            log.info("remote %s action %d denied", remote.name, rc.action)
        else:
            wall = self._wall()
            self._remotes[rc.mac] = replace(remote, last_seen=wall)
            if wall - self._saved_seen_at >= LAST_SEEN_SAVE_S:
                self._saved_seen_at = wall
                self._store.save(self._remotes)
        self._last_counter[rc.mac] = (rc.counter, result)
        return command, result

    def _rate_ok(self, mac: str, now: int) -> bool:
        q = self._recent.setdefault(mac, deque())
        while q and now - q[0] >= RATE_LIMIT_WINDOW_NS:
            q.popleft()
        if len(q) >= RATE_LIMIT_COUNT:
            return False
        q.append(now)
        return True

    def handle_command(self, rc: mt.RemoteCommand) -> Optional[Command]:
        """``authorize`` plus the ack to the MCU. Returns the command to submit, if any."""
        command, result = self.authorize(rc)
        self._send(mt.PairAck(rc.mac, rc.counter, result))
        return command

    # ---------------------------------------------------------------- UI

    def message(self) -> Message:
        now = self._wall()
        remotes = [
            {
                "id": r.mac,
                "name": r.name,
                "perms": perms_from_mask(r.mask),
                "last_seen_s": (now - r.last_seen) if r.last_seen else -1.0,
                "via": "radio",
            }
            for r in sorted(self._remotes.values(), key=lambda x: (x.name, x.mac))
        ]
        now_ns = self._clock.now_ns()
        pending = [
            {
                "id": p.mac,
                "name": p.name,
                "mac": p.mac,
                "caps": p.caps,
                "seen_s": max(0, (now_ns - p.seen_ns) // NS_PER_S),
            }
            for p in sorted(self._pending.values(), key=lambda x: x.mac)
        ]
        return remotes_msg(remotes, self.pairing_open, self.seconds_left, pending)

    def handle_ui(self, name: str, args: dict[str, Any]) -> bool:
        """The pairing commands of the UI (``pair_open`` ... ``remote_perms``). True if taken."""
        ident = str(args.get("id", ""))
        perms = [str(p) for p in args.get("perms") or []]
        if name == "pair_open":
            try:
                seconds = int(args.get("seconds", DEFAULT_PAIR_SECONDS))
            except (TypeError, ValueError):
                seconds = DEFAULT_PAIR_SECONDS
            self.open_pairing(seconds, discover=bool(args.get("discover")))
        elif name == "pair_close":
            self.close_pairing()
        elif name == "pair_accept":
            self.accept(ident, perms)
        elif name == "pair_reject":
            self.reject(ident)
        elif name == "remote_remove":
            self.remove(ident)
        elif name == "remote_perms":
            self.set_perms(ident, perms)
        else:
            return False
        return True

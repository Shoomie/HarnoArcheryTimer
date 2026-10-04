"""Leader side of follower access: who may join, who may do what (``docs/cluster.md``).

The registry knows followers (id, name, per-follower key, status, permissions, last seen), runs the
join handshake on a connection (``join`` -> pending / blocked / challenge, ``auth`` -> approved /
denied), carries out the operator's actions (approve, permissions, block, remove) and
decides for every message of a non-loopback connection whether it may pass (``allow``).
Loopback connections are the
operator and always pass. Emergency is free for everybody (``ipc.access``).

A "connection" is anything with ``send(msg)``, ``is_local`` and a ``ctx`` dict
(``ipc.server.ClientInfo``). Time: injected clock for throttling, injected wall clock for the
persisted ``last_seen``. Nothing here touches timing of the engine or the hardware.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, Clock
from archerytimer.common.compat import SLOTS
from archerytimer.ipc import access
from archerytimer.ipc.messages import (
    Message,
    access_msg,
    challenge_msg,
    denied_msg,
    followers_msg,
)

log = logging.getLogger("archerytimer.core.followers")

FILE_NAME = "core_followers.json"
MAX_FOLLOWERS = 64  # unknown ids beyond this are ignored (no flooding of the list)
LAST_SEEN_SAVE_S = 60.0
UI_COMMANDS = frozenset({"follower_approve", "follower_perms", "follower_block", "follower_remove"})


@dataclass(frozen=True, **SLOTS)
class Follower:
    id: str
    name: str
    key: str = ""  # hex, empty until approved
    status: str = "pending"  # approved | pending | blocked
    perms: tuple[str, ...] = ()
    last_seen: float = 0.0  # wall-clock epoch seconds, 0 = never


class FollowerStore:
    """``core_followers.json``: atomic write, a damaged file is ignored."""

    def __init__(self, path: Optional[Path]) -> None:
        self.path = path

    def load(self) -> dict[str, Follower]:
        if self.path is None or not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            result: dict[str, Follower] = {}
            for item in data["followers"]:
                fid = str(item["id"])
                status = str(item.get("status", "pending"))
                if status not in ("approved", "pending", "blocked"):
                    status = "pending"
                key = str(item.get("key", ""))
                if status == "approved":
                    bytes.fromhex(key)  # raises on garbage
                    if not key:
                        status = "pending"
                result[fid] = Follower(
                    fid,
                    str(item.get("name", ""))[:40] or fid,
                    key,
                    status,
                    tuple(access.clean_perms(item.get("perms", []))),
                    float(item.get("last_seen", 0.0)),
                )
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            log.warning("ignoring damaged followers file %s: %r", self.path, exc)
            return {}

    def save(self, followers: dict[str, Follower]) -> None:
        if self.path is None:
            return
        try:
            body = {
                "followers": [
                    {
                        "id": f.id,
                        "name": f.name,
                        "key": f.key,
                        "status": f.status,
                        "perms": list(f.perms),
                        "last_seen": f.last_seen,
                    }
                    for f in followers.values()
                ]
            }
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
            with contextlib.suppress(OSError):
                tmp.chmod(0o600)  # holds secrets
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("cannot save followers: %s", exc)


class FollowerRegistry:
    def __init__(
        self,
        clock: Clock,
        *,
        path: Optional[Path] = None,
        mesh_key_hex: str = "",
        leader_name: str = "",
        on_change: Optional[Callable[[], None]] = None,
        wall: Callable[[], float] = time.time,
        rng: Callable[[int], bytes] = os.urandom,
    ) -> None:
        self._clock = clock
        self._store = FollowerStore(path)
        self._mesh_key = mesh_key_hex
        self._leader = leader_name
        self._on_change = on_change or (lambda: None)
        self._wall = wall
        self._rng = rng
        self._lock = threading.RLock()
        self._followers = self._store.load()
        self._conns: dict[
            str, Any
        ] = {}  # follower id -> its live connection (approved: authenticated)
        self._saved_at_ns = 0
        self._last_published: Optional[Message] = None

    def set_on_change(self, callback: Callable[[], None]) -> None:
        self._on_change = callback

    def set_leader_name(self, name: str) -> None:
        self._leader = name

    def set_mesh_key(self, mesh_key_hex: str) -> None:
        """A new radio key (network reset): connected approved followers get it at once, so a
        follower that later runs on radio only does not hold an outdated key."""
        with self._lock:
            self._mesh_key = mesh_key_hex
            for fid, conn in list(self._conns.items()):
                f = self._followers.get(fid)
                if f is not None and f.status == "approved" and conn.ctx.get("authed"):
                    conn.send(self._access("approved", f, with_mesh=True))

    def get(self, fid: str) -> Optional[Follower]:
        with self._lock:
            return self._followers.get(fid)

    def ids(self) -> list[str]:
        with self._lock:
            return sorted(self._followers)

    # ---------------------------------------------------------------- the connection side

    def gate(self, conn: Any, msg: Message) -> bool:
        """For ``IpcServer(gate=...)``: True if the message may go on to the command handler.

        ``join``/``auth`` and the UI commands for followers are consumed here (False)."""
        kind = msg.get("type")
        if kind == "join":
            self.on_join(conn, msg)
            return False
        if kind == "auth":
            self.on_auth(conn, msg)
            return False
        if kind == "cmd" and str(msg.get("name", "")) in UI_COMMANDS:
            self.handle_ui(conn, str(msg["name"]), dict(msg.get("args") or {}))
            return False
        return self.allow(conn, msg)

    def on_disconnect(self, conn: Any) -> None:
        changed = False
        with self._lock:
            for fid, c in list(self._conns.items()):
                if c is conn:
                    del self._conns[fid]
                    changed = True
        if changed:
            self._on_change()

    def on_join(self, conn: Any, msg: Message) -> None:
        fid, name = msg.get("id"), msg.get("name")
        if not isinstance(fid, str) or not fid or len(fid) > 64 or not isinstance(name, str):
            log.warning("ignoring malformed join")
            return
        name = name[:40] or fid
        changed = False
        with self._lock:
            conn.ctx["fid"] = fid
            conn.ctx["authed"] = False
            conn.ctx.pop("nonce", None)
            f = self._followers.get(fid)
            if f is None:
                if len(self._followers) >= MAX_FOLLOWERS:
                    log.warning("follower list full, join ignored")
                    return
                f = Follower(fid, name)
                self._followers[fid] = f
                self._save()
                changed = True
                log.info("follower %s (%s) is waiting for approval", name, fid)
            if f.status == "approved":
                nonce = self._rng(16).hex().upper()
                conn.ctx["nonce"] = nonce
                conn.send(challenge_msg(nonce))
            elif f.status == "blocked":
                conn.send(self._access("blocked", f))
            else:
                if f.name != name:
                    self._followers[fid] = f = replace(f, name=name)
                    self._save()
                    changed = True
                self._conns[fid] = conn  # the approval (and key) goes to this connection
                conn.send(self._access("pending", f))
                changed = True
        if changed:
            self._on_change()

    def on_auth(self, conn: Any, msg: Message) -> None:
        fid, mac = msg.get("id"), msg.get("mac")
        nonce = conn.ctx.pop("nonce", None)  # a challenge is good for one answer
        if not isinstance(fid, str) or not isinstance(mac, str) or nonce is None:
            log.warning("ignoring auth without a challenge")
            return
        ok = False
        with self._lock:
            f = self._followers.get(fid)
            if f is not None and fid == conn.ctx.get("fid") and f.status == "approved" and f.key:
                try:
                    ok = access.macs_equal(access.auth_mac(f.key, nonce), mac)
                except (ValueError, TypeError):
                    ok = False
            if ok and f is not None:
                conn.ctx["authed"] = True
                self._conns[fid] = conn
                self._followers[fid] = replace(f, last_seen=self._wall())
                conn.send(
                    self._access("approved", f, with_mesh=True)
                )  # always the current radio key
                log.info("follower %s authenticated", f.name)
            else:
                conn.ctx["authed"] = False
                conn.send(access_msg("denied", [], "view", self._leader))
                log.warning("follower %s failed authentication", fid[:64])
        self._on_change()

    def allow(self, conn: Any, msg: Message) -> bool:
        """May this message of this connection go on? Refused ones are answered with ``denied``."""
        if getattr(conn, "is_local", False):
            return True
        perms: list[str] = []
        with self._lock:
            fid = conn.ctx.get("fid")
            f = self._followers.get(fid) if fid else None
            if f is not None and f.status == "approved" and conn.ctx.get("authed"):
                perms = list(f.perms)
        if access.allowed(perms, msg):
            return True
        name = str(msg.get("name", "")) if msg.get("type") == "cmd" else str(msg.get("type", ""))
        conn.send(denied_msg(name))
        return False

    # ---------------------------------------------------------------- operator actions

    def handle_ui(self, conn: Any, name: str, args: dict[str, Any]) -> bool:
        """``follower_approve|perms|block|remove`` from a UI, loopback only. True if taken."""
        if name not in UI_COMMANDS:
            return False
        if not getattr(conn, "is_local", False):
            conn.send(denied_msg(name))
            return True
        fid = str(args.get("id", ""))
        raw = args.get("perms")
        if name == "follower_approve":
            self.approve(fid, access.clean_perms(raw) if raw is not None else None)
        elif name == "follower_perms":
            self.set_perms(fid, access.clean_perms(raw))
        elif name == "follower_block":
            self.block(fid)
        else:
            self.remove(fid)
        return True

    def approve(self, fid: str, perms: Optional[list[str]] = None) -> bool:
        """Approve (or unblock): a new key goes once, with the mesh key, to its connection."""
        with self._lock:
            f = self._followers.get(fid)
            if f is None:
                return False
            if f.status == "approved":
                return self.set_perms(fid, list(f.perms if perms is None else perms))
            chosen = tuple(access.PRESETS["operator"] if perms is None else perms)
            f = replace(
                f,
                status="approved",
                key=self._rng(16).hex().upper(),
                perms=tuple(access.clean_perms(chosen)),
            )
            self._followers[fid] = f
            self._save()
            conn = self._conns.get(fid)
            if conn is not None:
                conn.ctx["authed"] = True
                conn.send(self._access("approved", f, with_keys=True))
            log.info("follower %s approved", f.name)
        self._on_change()
        return True

    def set_perms(self, fid: str, perms: list[str]) -> bool:
        with self._lock:
            f = self._followers.get(fid)
            if f is None:
                return False
            f = replace(f, perms=tuple(access.clean_perms(perms)))
            self._followers[fid] = f
            self._save()
            conn = self._conns.get(fid)
            if conn is not None and f.status == "approved" and conn.ctx.get("authed"):
                conn.send(self._access("approved", f))
        self._on_change()
        return True

    def block(self, fid: str) -> bool:
        with self._lock:
            f = self._followers.get(fid)
            if f is None:
                return False
            f = replace(f, status="blocked", key="", perms=())
            self._followers[fid] = f
            self._save()
            self._detach(fid, self._access("blocked", f))
        self._on_change()
        return True

    def remove(self, fid: str) -> bool:
        with self._lock:
            if self._followers.pop(fid, None) is None:
                return False
            self._save()
            self._detach(fid, access_msg("denied", [], "view", self._leader))
        self._on_change()
        return True

    def _detach(self, fid: str, notice: Message) -> None:
        conn = self._conns.pop(fid, None)
        if conn is not None:
            conn.ctx["authed"] = False
            conn.send(notice)

    # ---------------------------------------------------------------- UI and housekeeping

    def message(self) -> Message:
        now = self._wall()
        with self._lock:
            rows = []
            for f in sorted(self._followers.values(), key=lambda x: (x.name, x.id)):
                connected = f.id in self._conns
                if connected:
                    seen = 0
                elif f.last_seen:
                    seen = int(max(0.0, now - f.last_seen)) // 10 * 10  # coarse: fewer updates
                else:
                    seen = -1
                rows.append(
                    {
                        "id": f.id,
                        "name": f.name,
                        "status": f.status,
                        "connected": connected,
                        "preset": access.preset_of(list(f.perms)),
                        "perms": list(f.perms),
                        "last_seen_s": seen,
                    }
                )
        return followers_msg(rows)

    def tick(self) -> bool:
        """About once a second: refresh ``last_seen``. True if a new snapshot was published."""
        now_ns = self._clock.now_ns()
        with self._lock:
            wall = self._wall()
            for fid in self._conns:
                f = self._followers.get(fid)
                if f is not None and f.status == "approved":
                    self._followers[fid] = replace(f, last_seen=wall)
            if now_ns - self._saved_at_ns >= LAST_SEEN_SAVE_S * NS_PER_S:
                self._saved_at_ns = now_ns
                self._store.save(self._followers)
            msg = self.message()
            if msg == self._last_published:
                return False
        self._on_change()
        return True

    def published(self) -> Message:
        """The snapshot for the UIs; remembers it so ``tick`` only reports real differences."""
        msg = self.message()
        self._last_published = msg
        return msg

    def _save(self) -> None:
        self._store.save(self._followers)

    def _access(
        self, status: str, f: Follower, *, with_keys: bool = False, with_mesh: bool = False
    ) -> Message:
        return access_msg(
            status,
            list(f.perms),
            access.preset_of(list(f.perms)),
            self._leader,
            f.key if with_keys else "",
            self._mesh_key if (with_keys or with_mesh) else "",
        )

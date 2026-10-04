"""Follower access control (CONTRACT, frozen; ``docs/cluster.md`` section "Follower access").

Shared by the leader (enforces), the follower core (joins, proves its identity) and the UI. Pure
functions and constants: no I/O, no clock.

Flow on the leader link (all messages have ``type`` and ``v``; builders in ``ipc/messages.py``):

1. Follower core connects and sends ``join`` (its stable ``id`` and ``name``).
2. Leader: unknown id -> remembered as *pending*, answers ``access`` status ``pending`` (watch
only).
   Known and approved -> sends ``challenge`` (random nonce); follower answers ``auth`` with
   ``auth_mac(key, nonce)``; a correct answer gives ``access`` ``approved`` with its permissions,
   a wrong
   one ``denied`` (watch only). Blocked ids get ``access`` ``blocked`` (watch only).
3. The operator approves a pending follower on the leader: the leader creates a random per-follower
   ``key`` and sends ``access`` ``approved`` with ``key`` and the radio ``mesh_key`` (only in this
   message; over the LAN, which the project already treats as trusted). The follower stores both.
4. Every command or setting from a non-local connection is checked by ``required_perm``. Missing
   permission: dropped and answered with ``denied``. Emergency always passes. Connections from the
   leader's own machine (loopback) are the operator and always pass.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any, Optional

PERMS = (
    "primary",
    "pause",
    "resume",
    "stop_end",
    "next",
    "back",
    "reset",
    "configure",  # set up a session
    "settings",  # engine settings
    "clear_emergency",
)
PRESETS: dict[str, tuple[str, ...]] = {
    "view": (),
    "operator": ("primary", "pause", "resume", "stop_end", "next", "back"),
    "full": PERMS,
}
STATUSES = ("approved", "pending", "blocked", "denied")


def preset_of(perms: list[str]) -> str:
    """The preset name that matches exactly, else ``custom``."""
    for name, members in PRESETS.items():
        if set(perms) == set(members):
            return name
    return "custom"


def clean_perms(perms: Any) -> list[str]:
    """Only known permission names, in canonical order, no duplicates."""
    if not isinstance(perms, (list, tuple, set)):
        return []
    return [p for p in PERMS if p in perms]


def required_perm(msg: Mapping[str, Any]) -> Optional[str]:
    """The permission an IPC message needs, ``""`` if none (free), or ``None`` if the message may
    never come from a non-local client.

    ``cmd`` messages map by command name (``start`` is ``primary``); ``emergency`` is free;
    ``settings``
    need ``settings``; ``ping`` and ``join``/``auth`` are free; everything else is refused.
    """
    kind = msg.get("type")
    if kind in ("ping", "join", "auth"):
        return ""
    if kind == "settings":
        return "settings"
    if kind == "cmd":
        name = str(msg.get("name", ""))
        if name == "emergency":
            return ""
        if name == "start":
            return "primary"
        if name in PERMS:
            return name
    return None


def allowed(perms: list[str], msg: Mapping[str, Any]) -> bool:
    need = required_perm(msg)
    return need == "" or (need is not None and need in perms)


def auth_mac(key_hex: str, nonce_hex: str) -> str:
    """Proof of the per-follower key for one challenge: HMAC-SHA256 over the nonce, uppercase
    hex."""
    return (
        hmac.new(bytes.fromhex(key_hex), bytes.fromhex(nonce_hex), hashlib.sha256)
        .hexdigest()
        .upper()
    )


def macs_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.upper(), b.upper())

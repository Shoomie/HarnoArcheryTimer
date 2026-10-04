"""IPC messages: one JSON object per line, each with ``type`` and protocol ``v``.

Core to UI: ``hello``, ``state`` (full snapshot), ``link``, ``audio``, ``node``.
UI to core: ``cmd`` (``name`` + ``args``), ``settings``, ``ping`` (answered with ``pong``).
Unknown types are ignored (and logged by the receiver).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from typing import Any, Optional

from archerytimer.core.models import Buzzer, Event, Light, LightChange, Mode, Snapshot, Whistle

IPC_VERSION = 1
Message = dict[str, Any]


class MessageError(ValueError):
    pass


def encode_line(msg: Mapping[str, Any]) -> bytes:
    return json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n"


def decode_line(line: bytes) -> Message:
    try:
        msg = json.loads(line)
    except ValueError as exc:
        raise MessageError(f"bad JSON: {exc}") from None
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise MessageError("message must be an object with a string 'type'")
    return msg


def snapshot_to_dict(snap: Snapshot) -> dict[str, Any]:
    d = {f.name: getattr(snap, f.name) for f in dataclasses.fields(snap)}
    d["mode"] = snap.mode.value
    d["light"] = snap.light.value
    return d


def snapshot_from_dict(d: Mapping[str, Any]) -> Snapshot:
    try:
        kwargs = {f.name: d[f.name] for f in dataclasses.fields(Snapshot)}
        kwargs["mode"] = Mode(kwargs["mode"])
        kwargs["light"] = Light(kwargs["light"])
        return Snapshot(**kwargs)
    except (KeyError, ValueError, TypeError) as exc:
        raise MessageError(f"bad snapshot: {exc!r}") from None


def hello_msg(
    version: str,
    sequences: Mapping[str, Mapping[str, str]],
    timings: Optional[Mapping[str, Mapping[str, float]]] = None,
    master_id: int = 0,
    master_session: int = 0,
) -> Message:
    """``sequences`` maps sequence id to its localized names, for the preset cards;
    ``timings`` to its prep/shoot/warn seconds, for the setup screens."""
    return {
        "type": "hello",
        "v": IPC_VERSION,
        "version": version,
        "caps": ["state", "cmd", "settings"],
        "sequences": {sid: dict(names) for sid, names in sequences.items()},
        "timings": {sid: dict(t) for sid, t in (timings or {}).items()},
        "master_id": master_id,  # radio identity of this leader (0 = none); followers mirror it
        "master_session": master_session,  # leader's session counter (u32 >= 1, 0 = none)
    }


def state_msg(snap: Snapshot) -> Message:
    return {"type": "state", "v": IPC_VERSION, "state": snapshot_to_dict(snap)}


def link_msg(
    status: str,
    fw: str = "",
    chip: str = "",
    espnow: Optional[Mapping[str, Any]] = None,
    upstream: str = "up",
    via: str = "",
) -> Message:
    """``status`` is this node's lights hardware link. ``upstream`` is ``down`` on a follower
    core that has lost its leader (UIs then treat the timer as lost); ``via`` says how the
    timer arrives (``radio`` for a radio-only follower) so the UI can explain a lost feed.
    ``espnow`` is the MCU's ESP-NOW status (``mode``, ``peers``, ``src``) when known."""
    msg: Message = {
        "type": "link",
        "v": IPC_VERSION,
        "status": status,
        "fw": fw,
        "chip": chip,
        "upstream": upstream,
    }
    if espnow is not None:
        msg["espnow"] = dict(espnow)
    if via:
        msg["via"] = via
    return msg


def event_msg(ev: Event) -> Optional[Message]:
    """A hardware event (light, whistle, buzzer) for follower cores. None for snapshots."""
    base: Message = {"type": "event", "v": IPC_VERSION}
    if isinstance(ev, LightChange):
        return {**base, "kind": "light", "light": ev.light.value}
    if isinstance(ev, Whistle):
        return {**base, "kind": "whistle", "count": ev.count, "blast_ms": ev.blast_ms,
                "gap_ms": ev.gap_ms}  # fmt: skip
    if isinstance(ev, Buzzer):
        return {**base, "kind": "buzzer", "on": ev.on}
    return None


def event_from_msg(msg: Mapping[str, Any]) -> Optional[Event]:
    try:
        kind = msg["kind"]
        if kind == "light":
            return LightChange(Light(msg["light"]))
        if kind == "whistle":
            return Whistle(int(msg["count"]), int(msg["blast_ms"]), int(msg["gap_ms"]))
        if kind == "buzzer":
            return Buzzer(bool(msg["on"]))
    except (KeyError, ValueError, TypeError):
        pass
    return None


def audio_msg(
    *,
    local: bool,
    mcu: bool,
    volume: float,
    device: str,
    devices: list[str],
    local_available: bool,
    busy: bool,
    testing: bool,
) -> Message:
    """Sound state of the core, sent on connect and on every change. ``busy``: an end runs or an
    emergency is active (the sound test is refused). UIs change it with ``settings`` values
    ``sound_local``, ``sound_mcu``, ``volume``, ``audio_device`` and the ``sound_test`` command."""
    return {
        "type": "audio",
        "v": IPC_VERSION,
        "local": local,
        "mcu": mcu,
        "volume": volume,
        "device": device,
        "devices": list(devices),
        "local_available": local_available,
        "busy": busy,
        "testing": testing,
    }


def node_msg(
    *,
    role: str,
    active_role: str,
    leader: str,
    leaders: list[dict[str, str]],
    espnow: str,
    lights: bool,
    locked: bool,
    busy: bool,
    restart_needed: bool,
) -> Message:
    """Network role of the core, sent on connect and on every change. ``role`` is the stored
    choice, ``active_role`` what runs now (they differ until ``apply_network``). ``leaders`` are
    the leaders found on the LAN. UIs change it with ``settings`` values ``node_role``
    (standalone|leader|follower), ``node_leader`` ("" = automatic) and ``espnow``
    (off|bridge|follow|auto), ``lights`` (bool: this device's own lamps),
    and apply it with the ``apply_network`` command."""
    return {
        "type": "node",
        "v": IPC_VERSION,
        "role": role,
        "active_role": active_role,
        "leader": leader,
        "leaders": list(leaders),
        "espnow": espnow,
        "lights": lights,
        "locked": locked,
        "busy": busy,
        "restart_needed": restart_needed,
    }


def cmd_msg(name: str, args: Optional[Mapping[str, Any]] = None) -> Message:
    return {"type": "cmd", "v": IPC_VERSION, "name": name, "args": dict(args or {})}


def ping_msg(ping_id: int, t0: int) -> Message:
    return {"type": "ping", "v": IPC_VERSION, "id": ping_id, "t0": t0}


def pong_msg(ping_id: int, t0: int, t1: int) -> Message:
    """``t1`` is the core's monotonic clock when it handled the ping."""
    return {"type": "pong", "v": IPC_VERSION, "id": ping_id, "t0": t0, "t1": t1}


def settings_msg(values: Mapping[str, Any]) -> Message:
    return {"type": "settings", "v": IPC_VERSION, "values": dict(values)}


# --- mesh messages (docs/mesh.md, docs/decisions/0002) ---------------------------------------
# Core to UI. ``devices`` entries have the keys: id (stable string: mac or core id), name, kind
# ("core"|"module"|"remote"), role ("leader"|"follower"|"alone"|"node"|"mirror"|"remote"|"radio"),
# via ("self"|"lan"|"radio"|"usb"), follows (name of the main timer it follows, "" if none),
# state ("idle"|"running"|"waiting"|"finished"|""), signal ("good"|"weak"|""), fw,
# last_seen_s (float),
# caps (str), this (bool, true for the device the UI is connected to).
# UI to core commands: ``pair_open`` {seconds}, ``pair_close``,
# ``pair_accept`` {id, perms: [action names]},
# ``pair_reject`` {id}, ``remote_remove`` {id}, ``remote_perms`` {id, perms}, ``radio_reset_key``,
# ``take_over`` (this device becomes the main timer; the UI confirms first).
# Settings value ``node_name``.


def roster_msg(devices: list[dict[str, Any]], master: str, conflict: list[str]) -> Message:
    """The timer network as this core sees it. ``master`` is the main timer's name ("" if none),
    ``conflict`` the names of the masters involved when there is more than one (else empty)."""
    return {
        "type": "roster",
        "v": IPC_VERSION,
        "devices": [dict(d) for d in devices],
        "master": master,
        "conflict": list(conflict),
    }


def remotes_msg(
    remotes: list[dict[str, Any]],
    pairing_open: bool,
    seconds_left: int,
    pending: list[dict[str, Any]],
) -> Message:
    """Paired remotes (``id``, ``name``, ``perms`` list of action names, ``last_seen_s``, ``via``),
    the pairing window state, and requests waiting for the operator (``id``, ``name``, ``mac``,
    ``caps``, ``seen_s``: seconds since its latest request)."""
    return {
        "type": "remotes",
        "v": IPC_VERSION,
        "remotes": [dict(r) for r in remotes],
        "pairing_open": pairing_open,
        "seconds_left": seconds_left,
        "pending": [dict(p) for p in pending],
    }


# --- follower access (ipc/access.py, docs/cluster.md) -----------------------------------------
# Follower core to leader: ``join`` {id, name}, ``auth`` {id, mac}. Leader to follower:
# ``challenge``
# {nonce}, ``access`` {status, perms, preset, leader (name), key?, mesh_key?}, ``denied`` {name}.
# Leader to UI: ``followers``. Follower core to its UIs: ``follower`` (its own access state).
# UI to leader commands: ``follower_approve`` {id, perms}, ``follower_perms`` {id, perms},
# ``follower_block`` {id}, ``follower_remove`` {id}. ``link`` gains ``leader_rtt_ms`` and
# ``leader_offset_ms`` on a follower core (None until the first clock samples).


def join_msg(node_id: str, name: str) -> Message:
    return {"type": "join", "v": IPC_VERSION, "id": node_id, "name": name}


def challenge_msg(nonce_hex: str) -> Message:
    return {"type": "challenge", "v": IPC_VERSION, "nonce": nonce_hex}


def auth_msg(node_id: str, mac_hex: str) -> Message:
    return {"type": "auth", "v": IPC_VERSION, "id": node_id, "mac": mac_hex}


def access_msg(
    status: str,
    perms: list[str],
    preset: str,
    leader: str = "",
    key: str = "",
    mesh_key: str = "",
) -> Message:
    """The leader's verdict for one follower. ``key`` (per-follower secret) and ``mesh_key`` (radio)
    are only set in the message that follows the operator's approval."""
    msg: Message = {
        "type": "access",
        "v": IPC_VERSION,
        "status": status,
        "perms": list(perms),
        "preset": preset,
        "leader": leader,
    }
    if key:
        msg["key"] = key
    if mesh_key:
        msg["mesh_key"] = mesh_key
    return msg


def denied_msg(name: str) -> Message:
    """A command was refused for lack of permission (``name`` = the command)."""
    return {"type": "denied", "v": IPC_VERSION, "name": name}


def followers_msg(followers: list[dict[str, Any]]) -> Message:
    """Followers known to the leader. Entries: ``id``, ``name``, ``status``
    (approved|pending|blocked),
    ``connected`` (bool), ``preset`` (view|operator|full|custom), ``perms`` (list),
    ``last_seen_s``."""
    return {"type": "followers", "v": IPC_VERSION, "followers": [dict(f) for f in followers]}


def follower_state_msg(status: str, perms: list[str], preset: str, leader: str = "") -> Message:
    """A follower core's own access state for its UIs. ``status``: approved|pending|blocked|denied|
    waiting (no leader link yet). A UI shows 'waiting for approval' / 'watch only' and greys out
    buttons whose permission is missing."""
    return {
        "type": "follower",
        "v": IPC_VERSION,
        "status": status,
        "perms": list(perms),
        "preset": preset,
        "leader": leader,
    }

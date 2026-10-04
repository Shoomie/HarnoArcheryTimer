"""The timer network as this core sees it: one list of devices for the UI's "who is in the
network" screen (``roster_msg``, keys documented in ``ipc/messages.py``).

Merges three sources: this device, the other cores heard on the LAN (``netdisco.Instance``) and
the devices the attached ESP32 hears on the radio (``RosterEntry`` / ``RosterGone`` /
``MeshStatus``). Pure logic: no threads, no sockets; the owner feeds it and publishes
``message()`` when ``changed`` reports a difference. Nothing here touches timing.

Radio kinds map to device dicts as: ``N`` light box -> module/node, ``R`` remote -> remote/remote,
``F`` mirror -> module/mirror, ``M`` and ``E`` (another master, a radio-fed device) -> module/radio.
LAN instances are ``core`` devices (via ``lan``), this device is via ``self``.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional, Union

from archerytimer.core_service.netdisco import Instance, leader_conflict
from archerytimer.hardware import mesh_types as mt
from archerytimer.ipc.messages import Message, roster_msg

WEAK_RSSI = 75  # RosterEntry.rssi is a dBm magnitude: above this the link is weak

_RADIO_KIND = {
    mt.KIND_NODE: ("module", "node"),
    mt.KIND_REMOTE: ("remote", "remote"),
    mt.KIND_MIRROR: ("module", "mirror"),
    mt.KIND_MASTER: ("module", "radio"),
    mt.KIND_RADIO_FED: ("module", "radio"),
}
_ROLE_FROM_NODE = {"standalone": "alone", "leader": "leader", "follower": "follower"}


def signal_label(rssi: int) -> str:
    """``good``/``weak`` for a dBm magnitude; ``""`` if the radio gave none (0)."""
    if rssi <= 0:
        return ""
    return "weak" if rssi > WEAK_RSSI else "good"


class Roster:
    def __init__(self, self_id: str, now: Callable[[], float] = time.monotonic) -> None:
        self._self_id = self_id
        self._now = now
        self._name = ""
        self._role = "alone"
        self._follows = ""
        self._state = ""
        self._fw = ""
        self._caps = ""
        self._instances: tuple[Instance, ...] = ()
        self._radio: dict[str, tuple[mt.RosterEntry, float]] = {}
        self._status: Optional[mt.MeshStatus] = None
        self._last: Optional[tuple[object, ...]] = None

    # ---------------------------------------------------------------- inputs

    def set_self(
        self,
        name: str,
        role: str,
        follows: str = "",
        state: str = "",
        fw: str = "",
        caps: str = "",
    ) -> None:
        """``role`` is the node role (``standalone|leader|follower``) or already ``alone``."""
        self._name = name
        self._role = _ROLE_FROM_NODE.get(role, role)
        self._follows = follows
        self._state = state
        self._fw = fw
        self._caps = caps

    def set_instances(self, instances: list[Instance]) -> None:
        self._instances = tuple(i for i in instances if i.id != self._self_id)

    def on_mesh(self, item: Union[mt.RosterEntry, mt.RosterGone, mt.MeshStatus]) -> None:
        """Feed what the MCU reports (``$D``, gone, ``$O``)."""
        if isinstance(item, mt.RosterEntry):
            self._radio[item.mac] = (item, self._now())
        elif isinstance(item, mt.RosterGone):
            self._radio.pop(item.mac, None)
        elif isinstance(item, mt.MeshStatus):
            self._status = item

    def clear_radio(self) -> None:
        """The MCU went away or restarted: forget its roster."""
        self._radio.clear()
        self._status = None

    # ---------------------------------------------------------------- results

    def _lan_leaders(self) -> list[Instance]:
        return [i for i in self._instances if i.role == "leader"]

    def followers(self) -> list[str]:
        """Names of the cores that follow this one (meaningful on a leader)."""
        return [
            i.name
            for i in self._instances
            if i.role == "follower" and self._name and i.follows in (self._name, self._self_id)
        ]

    def _radio_masters(self) -> list[str]:
        return [e.name or e.mac for e, _t in self._radio.values() if e.kind == mt.KIND_MASTER]

    def conflict(self) -> list[str]:
        names = [i.name for i in self._lan_leaders()]
        if self._role == "leader":
            names.append(self._name)
        found = leader_conflict(names)
        if not found and self._status is not None and self._status.conflict:
            return sorted({*names, *self._radio_masters()})  # radio saw two masters
        return found

    def master(self) -> str:
        """Name of the main timer this device runs under ("" if none is known)."""
        if self._role in ("leader", "alone"):
            return self._name
        for i in self._lan_leaders():
            if self._follows in (i.name, i.addr, i.id):
                return i.name
        if self._follows:
            return self._follows
        leaders = self._lan_leaders()
        if leaders:
            return leaders[0].name
        masters = self._radio_masters()
        return masters[0] if masters else ""

    def devices(self) -> list[dict[str, Any]]:
        now = self._now()
        out: list[dict[str, Any]] = [
            {
                "id": self._self_id,
                "name": self._name,
                "kind": "core",
                "role": self._role,
                "via": "self",
                "follows": self._follows if self._role == "follower" else "",
                "state": self._state,
                "signal": "",
                "fw": self._fw,
                "last_seen_s": 0.0,
                "caps": self._caps,
                "this": True,
            }
        ]
        for i in sorted(self._instances, key=lambda x: (x.name, x.id)):
            out.append(
                {
                    "id": i.id,
                    "name": i.name,
                    "kind": "core",
                    "role": i.role,
                    "via": "lan",
                    "follows": i.follows if i.role == "follower" else "",
                    "state": i.state,
                    "signal": "",
                    "fw": i.version,
                    "last_seen_s": 0.0,  # the browser drops cores that went quiet
                    "caps": "",
                    "this": False,
                }
            )
        for mac in sorted(self._radio):
            e, t = self._radio[mac]
            kind, role = _RADIO_KIND.get(e.kind, ("module", "radio"))
            out.append(
                {
                    "id": e.mac,
                    "name": e.name or e.mac,
                    "kind": kind,
                    "role": role,
                    "via": "radio",
                    "follows": "",
                    "state": "",
                    "signal": signal_label(e.rssi),
                    "fw": e.fw,
                    "last_seen_s": max(0.0, now - t),
                    "caps": e.caps,
                    "this": False,
                }
            )
        return out

    def message(self) -> Message:
        return roster_msg(self.devices(), self.master(), self.conflict())

    def changed(self) -> bool:
        """True once after the visible content changed (``last_seen_s`` ageing is ignored)."""
        rows = [tuple((k, v) for k, v in d.items() if k != "last_seen_s") for d in self.devices()]
        key = (*rows, self.master(), tuple(self.conflict()))
        if key == self._last:
            return False
        self._last = key
        return True

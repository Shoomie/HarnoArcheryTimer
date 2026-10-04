"""This device's place in a multi-device setup, and the control that changes it.

Roles (``docs/cluster.md``): ``standalone`` (a leader nobody else can reach, the default),
``leader`` (the one device whose engine runs the session; reachable on the network and
announced by a beacon) and ``follower`` (mirrors a leader's lights and sound, forwards
commands). The ESP-NOW role of the attached ESP32 (``off|bridge|follow|auto``) is part of it.
Every device can have a screen, lights and sound whatever its role.

Changing the role needs a new service object, so ``NodeControl`` only *stores* the wish and
tells the UI that a restart is needed; ``apply_network`` (refused while a session is in
progress) hands over to the entry point, which rebuilds the service in-process. Command-line
flags win over the stored choice and lock it.

Mesh v2 additions: ``node_name`` (the name shown in the network list and beacon), ``take_over``
(this device becomes the main timer: refused while a session runs unless ``force``), and the
hand-through of the roster, the paired remotes and the pairing commands of the UI. Roster and
remotes are plain collaborators (``Roster``, ``RemoteRegistry``); the serial side feeds
``on_mesh`` with the typed frames from the MCU.
"""

from __future__ import annotations

import json
import logging
import socket
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

from archerytimer.common.compat import SLOTS
from archerytimer.core import models as m
from archerytimer.core_service.netdisco import LeaderBrowser
from archerytimer.core_service.remotes import RemoteRegistry
from archerytimer.core_service.roster import Roster
from archerytimer.hardware import mesh_types as mt
from archerytimer.hardware.protocol import ESPNOW_MODE_NAMES
from archerytimer.hardware.serial_worker import SerialWorker
from archerytimer.ipc.messages import Message, node_msg

log = logging.getLogger("archerytimer.core.node")

FILE_NAME = "core_node.json"
ROLES = ("standalone", "leader", "follower")
ESPNOW_NAMES = tuple(ESPNOW_MODE_NAMES)  # off, bridge, follow, auto
SETTING_KEYS = frozenset({"node_role", "node_leader", "espnow", "lights", "node_name"})
RESTART_KEYS = frozenset({"node_role", "node_leader", "espnow"})  # locked by start flags
UI_COMMANDS = frozenset(
    {"pair_open", "pair_close", "pair_accept", "pair_reject", "remote_remove", "remote_perms"}
)
NAME_MAX = 40


@dataclass(frozen=True, **SLOTS)
class NodeSettings:
    role: str = "standalone"
    leader: str = ""  # "host:port"; "" = use the only leader found on the network
    espnow: str = "off"
    lights: bool = True  # this device's own lights (the MCU lamps) on or dark
    name: str = ""  # shown in the network list and beacon; "" = the host name

    def updated(self, values: Mapping[str, Any]) -> NodeSettings:
        """Apply UI ``settings`` values (``node_role``, ``node_leader``, ``espnow``);
        anything invalid is ignored."""
        changes: dict[str, Any] = {}
        if values.get("node_role") in ROLES:
            changes["role"] = values["node_role"]
        leader = values.get("node_leader")
        if isinstance(leader, str) and len(leader) <= 80:
            changes["leader"] = leader.strip()
        if values.get("espnow") in ESPNOW_NAMES:
            changes["espnow"] = values["espnow"]
        if isinstance(values.get("lights"), bool):
            changes["lights"] = values["lights"]
        name = values.get("node_name")
        if isinstance(name, str) and name.strip():
            changes["name"] = name.strip()[:NAME_MAX]
        return replace(self, **changes)


def from_table(table: Mapping[str, Any]) -> NodeSettings:
    """Defaults from ``[node]`` of the settings TOML (a ``leader`` there means follower)."""
    leader = str(table.get("leader", "") or "")
    return NodeSettings().updated(
        {
            "node_role": "follower" if leader else table.get("role"),
            "node_leader": leader,
            "espnow": table.get("espnow"),
            "lights": table.get("lights"),
            "node_name": table.get("name"),
        }
    )


class NodeStore:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path

    def load(self, default: NodeSettings) -> NodeSettings:
        if self.path is None or not self.path.exists():
            return default
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return default.updated(
                {
                    "node_role": data.get("role"),
                    "node_leader": data.get("leader"),
                    "espnow": data.get("espnow"),
                    "lights": data.get("lights"),
                    "node_name": data.get("name"),
                }
            )
        except (OSError, ValueError, AttributeError) as exc:
            log.warning("ignoring damaged node settings %s: %r", self.path, exc)
            return default

    def save(self, settings: NodeSettings) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(settings), indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("cannot save node settings: %s", exc)


class NodeControl:
    """Settings, status and the apply step of this node's role."""

    def __init__(
        self,
        active: NodeSettings,
        *,
        store: Optional[NodeStore] = None,
        browser: Optional[LeaderBrowser] = None,
        beacon: Optional[Any] = None,
        locked: bool = False,
        on_apply: Optional[Callable[[], None]] = None,
        node_id: str = "",
        roster: Optional[Roster] = None,
        remotes: Optional[RemoteRegistry] = None,
        submit_command: Optional[Callable[[m.Command], None]] = None,
        on_reset_key: Optional[Callable[[], None]] = None,
        version: str = "",
    ) -> None:
        self.active = active  # what is running now
        self.wanted = active  # what is stored; differs until applied
        self._store = store or NodeStore(None)
        self._browser = browser
        self._beacon = beacon
        self._locked = locked
        self._on_apply = on_apply or (lambda: None)
        self._node_id = node_id
        self._roster = roster
        self._remotes = remotes
        self._submit_command = submit_command or (lambda _c: None)
        self._on_reset_key = on_reset_key or (lambda: None)
        self._version = version
        self._state = ""  # session state for the beacon and roster
        self._publish: Callable[[Message], None] = lambda _m: None
        self._worker: Optional[SerialWorker] = None
        self._busy = False

    # ---------------------------------------------------------------- lifecycle

    def bind(self, publish: Callable[[Message], None], worker: Optional[SerialWorker]) -> None:
        self._publish = publish
        self._worker = worker
        if self._browser is not None:
            self._browser.on_change = self._network_changed
        if self._remotes is not None:
            self._remotes.set_on_change(self.publish_remotes)
            if worker is not None:
                self._remotes.set_send(worker.send_mesh)

    def start(self) -> None:
        if self._worker is not None:
            self._worker.set_lights(self.wanted.lights)
        if self._browser is not None:
            self._browser.start()
        if self._beacon is not None:
            self._beacon.start()
        self._refresh_mesh()
        self._publish(self.status_msg())
        self.publish_remotes()

    def stop(self) -> None:
        if self._beacon is not None:
            self._beacon.stop()
        if self._browser is not None:
            self._browser.stop()

    # ---------------------------------------------------------------- messages

    def submit(self, event: m.Event) -> None:
        """Snapshots tell us whether a session is in progress (role changes wait then)."""
        if isinstance(event, m.Snapshot):
            busy = event.emergency or event.mode in (m.Mode.RUNNING, m.Mode.WAITING)
            state = event.mode.value if isinstance(event.mode, m.Mode) else ""
            busy_changed = busy != self._busy
            if busy_changed or state != self._state:
                self._busy = busy
                self._state = state
                self._refresh_mesh()
                if busy_changed:
                    self._publish(self.status_msg())

    def handle_message(self, msg: Message) -> bool:
        """Take the network parts of a UI message. True if the whole message was ours."""
        if msg.get("type") == "settings":
            values = dict(msg.get("values") or {})
            self.on_settings({k: values[k] for k in SETTING_KEYS if k in values})
            return not (set(values) - SETTING_KEYS)
        if msg.get("type") == "cmd":
            name = str(msg.get("name"))
            args = dict(msg.get("args") or {})
            if name == "apply_network":
                self.apply()
                return True
            if name == "take_over":
                self.take_over(force=bool(args.get("force")))
                return True
            if name == "radio_reset_key":
                self._on_reset_key()
                return True
            if name in UI_COMMANDS and self._remotes is not None:
                return self._remotes.handle_ui(name, args)
        return False

    def on_settings(self, values: dict[str, Any]) -> None:
        if self._locked:  # start flags fix the role and ESP-NOW mode, not the lights
            values = {k: v for k, v in values.items() if k not in RESTART_KEYS}
        new = self.wanted.updated(values)
        if new == self.wanted:
            return
        if new.espnow != self.wanted.espnow and self._worker is not None:
            self._worker.set_espnow_mode(ESPNOW_MODE_NAMES[new.espnow])  # live, no restart
        if new.lights != self.wanted.lights and self._worker is not None:
            self._worker.set_lights(new.lights)
        self.active = replace(self.active, espnow=new.espnow, lights=new.lights, name=new.name)
        self.wanted = new
        self._store.save(new)
        self._refresh_mesh()
        self._publish(self.status_msg())

    @property
    def restart_needed(self) -> bool:
        return (self.wanted.role, self.wanted.leader) != (self.active.role, self.active.leader)

    def apply(self) -> bool:
        """Hand over to the entry point to rebuild the service. False if refused."""
        if self._locked or self._busy or not self.restart_needed:
            return False
        log.info("applying network change: %s -> %s", self.active, self.wanted)
        self._on_apply()
        return True

    def take_over(self, force: bool = False) -> str:
        """Make this device the main timer (leader). Returns what happened: ``restart`` (stored,
        the entry point must rebuild the service as leader; ``on_apply`` was called), ``already``
        (nothing to do), ``locked`` (start flags fix the role) or ``busy`` (a session runs here and
        ``force`` is not set). An old leader that still runs shows up as a conflict until it is
        told to follow or stopped."""
        if self.active.role == "leader" and self.wanted.role == "leader":
            return "already"
        if self._locked:
            return "locked"
        if self._busy and not force:
            return "busy"
        self.wanted = replace(self.wanted, role="leader", leader="")
        self._store.save(self.wanted)
        log.info("taking over as leader (force=%s)", force)
        self._on_apply()
        return "restart"

    # ---------------------------------------------------------------- mesh

    @property
    def name(self) -> str:
        return self.wanted.name or socket.gethostname()[:NAME_MAX]

    def _refresh_mesh(self) -> None:
        """Push our name, role and state into the beacon and the roster; publish if changed."""
        role = self.active.role
        if self._roster is not None:
            if self._browser is not None:
                self._roster.set_instances(self._browser.instances())
            self._roster.set_self(self.name, role, self.active.leader, self._state, self._version)
        if self._beacon is not None:
            self._beacon.update(
                name=self.name,
                role="alone" if role == "standalone" else role,
                follows=self._roster.master() if (self._roster and role == "follower") else "",
                state=self._state,
            )
        if self._roster is not None and self._roster.changed():
            self._publish(self._roster.message())

    def _network_changed(self) -> None:
        self._refresh_mesh()
        self._publish(self.status_msg())

    def publish_roster(self) -> None:
        if self._roster is not None:
            self._refresh_mesh()
            self._publish(self._roster.message())

    def publish_remotes(self) -> None:
        if self._remotes is not None:
            self._publish(self._remotes.message())

    def on_mesh(self, frame: object) -> None:
        """A typed frame from the MCU (roster, mesh status, pairing, remote command)."""
        if isinstance(frame, (mt.RosterEntry, mt.RosterGone, mt.MeshStatus)):
            if self._roster is not None:
                self._roster.on_mesh(frame)
                self._refresh_mesh()
        elif self._remotes is not None:
            if isinstance(frame, mt.PairRequest):
                self._remotes.on_request(frame)
            elif isinstance(frame, mt.PairDone):
                self._remotes.on_done(frame)
            elif isinstance(frame, mt.PairState):
                self._remotes.on_pair_state(frame)
            elif isinstance(frame, mt.RemoteCommand):
                command = self._remotes.handle_command(frame)
                if command is not None:
                    self._submit_command(command)

    def tick(self) -> None:
        """About once a second: closes an expired pairing window and refreshes the countdown."""
        if self._remotes is not None and self._remotes.needs_tick:
            self._remotes.tick()
            self.publish_remotes()

    def status_msg(self) -> Message:
        return node_msg(
            role=self.wanted.role,
            active_role=self.active.role,
            leader=self.wanted.leader,
            leaders=self._browser.leaders() if self._browser is not None else [],
            espnow=self.wanted.espnow,
            lights=self.wanted.lights,
            locked=self._locked,
            busy=self._busy,
            restart_needed=self.restart_needed,
        )

"""Follower core: one device in a multi-device timer network.

A cluster has one **leader** (a normal ``CoreService``, the only place the engine runs, so
there is one timeline and no conflicting state) and any number of **followers**. A follower:

- mirrors the leader's hardware events onto its *own* lights and sound (serial / ESP-NOW),
  and re-asserts the leader's light state with every snapshot, so a missed event heals;
- republishes the leader's state to its own UI clients, with deadlines translated into this
  machine's clock (using the measured clock offset), so local screens count the same instant;
- accepts commands from anywhere on the device (UI clients, MCU buttons, GPIO) and forwards
  them to the leader, so every device can run the session;
- fails safe: with no leader for 1 s it forces its lights RED and silences sound.

If the leader dies, followers go RED and silent. Starting a different device as leader is a
manual step (see docs/cluster.md).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, Clock
from archerytimer.core.models import Buzzer, Command, Event, Light, LightChange, Whistle
from archerytimer.core_service.audio_control import AudioControl
from archerytimer.core_service.inputs import Binding, ButtonMap, GpioInput, GpioUnavailable
from archerytimer.core_service.node import NodeControl
from archerytimer.core_service.radio_keys import RadioKeys
from archerytimer.hardware.mesh_types import ROLE_MIRROR, Role
from archerytimer.hardware.protocol import ESPNOW_MODE_NAMES, EspNowStatus
from archerytimer.hardware.serial_worker import SerialWorker
from archerytimer.hardware.sim_device import Port
from archerytimer.ipc import access
from archerytimer.ipc.link import CoreLink
from archerytimer.ipc.messages import (
    Message,
    auth_msg,
    cmd_msg,
    event_from_msg,
    follower_state_msg,
    join_msg,
    link_msg,
    snapshot_from_dict,
    snapshot_to_dict,
    state_msg,
)
from archerytimer.ipc.server import IpcServer
from archerytimer.ipc.transport import Connection, Listener

log = logging.getLogger("archerytimer.cluster")

LEADER_GRACE_NS = NS_PER_S  # no leader for this long: RED and silent
LOCAL_SETTINGS = frozenset({"espnow"})  # applied on this node; everything else goes to the leader
FOLLOW_FILE = "core_follow.json"
SYNC_LOG_NS = 10 * NS_PER_S  # how often the leader clock-sync values go to the log
REJOIN_DELAY_S = 2.0  # after the leader refused us, ask to join again after this long
REJOIN_MIN_NS = 20 * NS_PER_S  # never more often than this (a key that keeps failing must not spam)


class FollowStore:
    """The per-follower key the leader gave this device, and which leader it belongs to.

    One small JSON file, written atomically; a damaged or missing file means "not approved yet".
    """

    def __init__(self, path: Optional[Path]) -> None:
        self._path = path
        self.key = ""
        self.leader = ""  # the leader's name, as it told us
        self.leader_id = ""
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                key = str(data.get("key", "")).upper()
                bytes.fromhex(key)
                if key and len(key) != 64:
                    raise ValueError("bad key length")
                self.key = key
                self.leader = str(data.get("leader", ""))
                self.leader_id = str(data.get("leader_id", ""))
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                log.warning("ignoring damaged %s: %r", path, exc)
                self.key = self.leader = self.leader_id = ""

    def save(self, key: str, leader: str, leader_id: str) -> None:
        self.key, self.leader, self.leader_id = key.upper(), leader, leader_id
        if self._path is None:
            return
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"key": self.key, "leader": leader, "leader_id": leader_id}),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError as exc:
            log.warning("cannot save %s: %s", self._path, exc)


class FollowerService:
    def __init__(
        self,
        clock: Clock,
        connect_leader: Callable[[], Connection],
        listener: Listener,
        *,
        port_factory: Optional[Callable[[], Port]] = None,
        bindings: Optional[Mapping[str, Binding]] = None,
        espnow: Optional[str] = None,
        audio: Optional[AudioControl] = None,
        node: Optional[NodeControl] = None,
        version: str = "0.0.1",
        mesh_config: Optional[Mapping[str, str]] = None,
        node_id: str = "",
        node_name: str = "",
        access_store: Optional[FollowStore] = None,
        radio_keys: Optional[RadioKeys] = None,
    ) -> None:
        self._clock = clock
        self._node_id = node_id
        self._node_name = node_name or node_id
        self._store = access_store or FollowStore(None)
        self._radio_keys = radio_keys
        # Leader verdict; None until it sends ``access`` (a leader that never does is not gated).
        self._access: Optional[dict[str, Any]] = None
        self._last_denied = ""
        self._pub_connected = False
        self._leader_id_seen = self._store.leader_id
        self._last_sync_log_ns = 0
        self._last_rejoin_ns = -REJOIN_MIN_NS
        self._synced_published = False
        self.server = IpcServer(
            listener,
            {
                "type": "hello",
                "v": 1,
                "version": version,
                "caps": ["state", "cmd"],
                "sequences": {},
            },
            self._on_local_message,
            clock,
        )
        self.buttons = ButtonMap(bindings or {}, self._forward_command, clock)
        self.worker: Optional[SerialWorker] = (
            SerialWorker(
                port_factory,
                clock,
                lambda _s: self._publish_link(),
                on_button=lambda i, down: self.buttons.on_event("mcu", i, down),
                on_espnow=lambda _s: self._publish_link(),
                espnow_mode=ESPNOW_MODE_NAMES.get(espnow or ""),
                config=mesh_config,
                on_mesh_status=self._on_mesh,
                on_roster=self._on_mesh,
                on_pairing=self._on_mesh,
                on_remote_command=self._on_mesh,
            )
            if port_factory
            else None
        )
        self.audio = audio
        if audio is not None:
            audio.bind(self.server.publish, self.worker)
        self.node = node
        if node is not None:
            node.bind(self.server.publish, self.worker)
        self.leader = CoreLink(
            connect_leader,
            clock=clock,
            ping_interval_s=1.0,
            backoff_s=(0.2, 0.5, 1.0),
            on_message=self._on_leader_message,
            on_connect=self._on_leader_connect,
        )
        self._raw_state: Optional[dict[str, Any]] = None
        self._last_light: Optional[Light] = None
        self._leader_ok = False
        self._failed_safe = False
        self._stop = threading.Event()
        self._watchdog: Optional[threading.Thread] = None
        self._gpio: Optional[GpioInput] = None
        pins = [int(k.split(":")[1]) for k in (bindings or {}) if k.startswith("gpio:")]
        if pins:
            try:
                self._gpio = GpioInput(pins, self.buttons.on_event)
            except GpioUnavailable as exc:
                log.warning("GPIO inputs disabled: %s", exc)

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self.worker:
            self.worker.start()
        if self.audio:
            self.audio.start()
        if self.node:
            self.node.start()
        self.leader.start()
        self.server.start()
        self._watchdog = threading.Thread(target=self._watch, name="leader-watchdog")
        self._watchdog.start()

    def stop(self) -> None:
        self._stop.set()
        if self._gpio:
            self._gpio.close()
        if self._watchdog:
            self._watchdog.join(timeout=2.0)
        self.leader.stop()
        if self.node:
            self.node.stop()
        if self.audio:
            self.audio.stop()
        if self.worker:
            self.worker.stop()  # RED and silence
        self.server.stop()

    def _on_mesh(self, frame: object) -> None:
        if self.node:
            self.node.on_mesh(frame)

    # ---------------------------------------------------------------- from the leader

    def _on_leader_connect(self, send: Callable[[Message], bool]) -> None:
        if self._node_id:
            send(join_msg(self._node_id, self._node_name))
        self._publish_follower()

    def _on_access(self, msg: Message) -> None:
        status = str(msg.get("status", ""))
        perms = access.clean_perms(msg.get("perms")) if status == "approved" else []
        leader = str(msg.get("leader", ""))
        self._access = {
            "status": status,
            "perms": perms,
            "preset": str(msg.get("preset") or access.preset_of(perms)),
            "leader": leader,
        }
        if status == "denied" and self._node_id:
            self._forget_and_rejoin()
        key = str(msg.get("key") or "")
        if key:
            try:
                bytes.fromhex(key)
                self._store.save(key, leader, self._leader_id_seen)
                log.info("approved by leader %r: access key stored", leader)
            except ValueError:
                log.warning("leader sent an invalid access key")
        mesh_key = str(msg.get("mesh_key") or "")
        if mesh_key and self._radio_keys is not None:
            try:
                self._radio_keys.set_mesh_key(mesh_key)
                if self.worker:
                    self.worker.set_config("mkey", mesh_key.upper())
            except Exception as exc:  # ValueError, ProtocolError
                log.warning("leader sent an unusable mesh key: %r", exc)
        log.info("access from leader: %s (%s)", status, self._access["preset"])
        self._publish_follower()

    def _forget_and_rejoin(self) -> None:
        """The leader removed this device (or its key no longer fits): forget the key and ask
        again, so the operator sees a new request instead of a silent refusal."""
        now = self._clock.now_ns()
        if now - self._last_rejoin_ns < REJOIN_MIN_NS:
            return
        self._last_rejoin_ns = now
        self._store.save("", self._store.leader, self._store.leader_id)
        log.info("leader refused this follower: key forgotten, asking to join again")

        def ask() -> None:
            self.leader.send(join_msg(self._node_id, self._node_name))

        timer = threading.Timer(REJOIN_DELAY_S, ask)
        timer.daemon = True
        timer.start()

    def _on_challenge(self, msg: Message) -> None:
        if not self._store.key or not self._node_id:
            return  # not approved yet: the leader will answer ``pending``
        try:
            mac = access.auth_mac(self._store.key, str(msg.get("nonce", "")))
        except ValueError:
            log.warning("bad challenge from leader")
            return
        self.leader.send(auth_msg(self._node_id, mac))

    def _publish_follower(self) -> None:
        a = self._access
        if a is None or not self.leader.connected:
            # no leader link or verdict yet: cached rights keep gating, the UI shows "waiting"
            status = "waiting"
            perms: list[str] = list(a["perms"]) if a else []
            preset = str(a["preset"]) if a else "view"
            leader = str(a["leader"]) if a else self._store.leader
        else:
            status, perms, preset, leader = a["status"], a["perms"], a["preset"], a["leader"]
        msg = follower_state_msg(status, perms, preset, leader)
        if self._last_denied:
            msg["last_denied"] = self._last_denied  # additive: the command that was refused
        self.server.publish(msg)

    def _permitted(self, msg: Message) -> bool:
        """Whether the cached rights allow forwarding ``msg``; tells the UI if not."""
        a = self._access
        if a is None or msg.get("type") not in ("cmd", "settings"):
            return True  # no verdict yet: the leader enforces
        if a["status"] == "approved" and access.allowed(a["perms"], msg):
            return True
        if access.allowed([], msg):
            return True  # emergency
        self._last_denied = str(msg.get("name", msg.get("type", "")))
        log.info("not forwarded (no permission): %s", self._last_denied)
        self._publish_follower()
        return False

    def _log_sync(self) -> None:
        now = self._clock.now_ns()
        if self.leader.connected and now - self._last_sync_log_ns >= SYNC_LOG_NS:
            self._last_sync_log_ns = now
            log.info(
                "leader clock sync: rtt %s ms, offset %s ms",
                self.leader.rtt_ms,
                self.leader.offset_ms,
            )
            self._publish_link()  # carries the same values to the UIs

    def _on_leader_message(self, msg: Message) -> None:
        """Runs on the leader link's reader thread, in arrival order."""
        kind = msg.get("type")
        if kind == "access":
            self._on_access(msg)
        elif kind == "challenge":
            self._on_challenge(msg)
        elif kind == "denied":
            self._last_denied = str(msg.get("name", ""))
            log.info("leader refused: %s", self._last_denied)
            self._publish_follower()
        elif kind == "hello":
            self.server.set_hello(msg)
            self.server.publish(msg)
            leader_id = int(msg.get("master_id") or 0)
            if leader_id:
                self._leader_id_seen = f"{leader_id:x}"
            leader_session = int(msg.get("master_session") or 0)
            if self.worker and leader_id and leader_session:
                # this MCU mirrors the leader on the radio (rank 1) with the leader's session
                self.worker.set_role(Role(ROLE_MIRROR, leader_id, leader_session))
        elif kind == "event":
            ev = event_from_msg(msg)
            if ev is not None:
                if isinstance(ev, LightChange):
                    self._last_light = ev.light
                self._out(ev)
        elif kind == "state":
            self._on_leader_state(msg["state"])
        elif kind == "pong":
            self._republish_state()  # the first pong makes the clock offset usable
            if not self._synced_published and self.leader.estimator.synced:
                self._synced_published = True
                self._publish_link()

    def _on_leader_state(self, raw: dict[str, Any]) -> None:
        self._raw_state = raw
        self._failed_safe = False
        if not self._leader_ok:
            self._leader_ok = True
            self._publish_link()
        snap = snapshot_from_dict(raw)
        if snap.light is not self._last_light:  # state assertion: heals a missed event
            self._last_light = snap.light
            self._out(LightChange(snap.light))
        self._out(snap)  # carries the line group
        self._republish_state()

    def _republish_state(self) -> None:
        raw = self._raw_state
        if raw is None or not self.leader.estimator.synced:
            return
        offset = self.leader.estimator.offset_ns  # leader clock minus ours
        d = dict(raw)
        d["phase_start_ns"] = int(raw["phase_start_ns"]) - offset
        d["deadline_ns"] = int(raw["deadline_ns"]) - offset
        d["link"] = self.worker.link if self.worker else "down"  # *this* node's lights
        self.server.publish(state_msg(snapshot_from_dict(d)))

    def _watch(self) -> None:
        while not self._stop.wait(0.1):
            if self.leader.connected != self._pub_connected:
                self._pub_connected = self.leader.connected
                self._publish_follower()
            self._log_sync()
            lost = self.leader.lost_since_ns
            if (
                self.leader.ever_connected
                and not self.leader.connected
                and lost is not None
                and self._clock.now_ns() - lost >= LEADER_GRACE_NS
                and not self._failed_safe
            ):
                self._fail_safe()

    def _fail_safe(self) -> None:
        log.warning("leader lost: forcing RED and silence")
        self._failed_safe = True
        self._leader_ok = False
        self._last_light = Light.RED
        self._silence()
        self._publish_link()

    def _out(self, ev: Event) -> None:
        """An event for this node's own outputs: its MCU and its speakers."""
        if self.worker:
            self.worker.submit(ev)
        if self.audio:
            self.audio.submit(ev)
        if self.node:
            self.node.submit(ev)

    def _silence(self) -> None:
        self._out(LightChange(Light.RED))
        self._out(Whistle(0, 0, 0))
        self._out(Buzzer(False))

    # ---------------------------------------------------------------- from local clients

    def _on_local_message(self, msg: Message) -> None:
        kind = msg.get("type")
        if self.node and self.node.handle_message(msg):
            return  # network role and ESP-NOW mode belong to this node
        if self.audio and self.audio.handle_message(msg):
            return  # sound settings and the sound test belong to this node, not the leader
        if kind == "settings":
            values = dict(msg.get("values") or {})
            mode = values.pop("espnow", None)
            if mode in ESPNOW_MODE_NAMES and self.worker:
                self.worker.set_espnow_mode(ESPNOW_MODE_NAMES[mode])
            if not values:
                return
            msg = {**msg, "values": values}
        if not self._permitted(msg):
            return
        if not self.leader.send(msg):
            self._local_emergency_if_needed(msg)

    def send(self, cmd: Command) -> None:
        """A command from a paired remote at this node: goes to the leader like any other."""
        self._forward_command(cmd)

    def _forward_command(self, cmd: Command) -> None:
        self._on_local_message(cmd_msg(cmd.name, dict(cmd.args)))

    def _local_emergency_if_needed(self, msg: Message) -> None:
        """No leader to tell: an emergency still stops this device's own lights and sound."""
        if msg.get("name") == "emergency":
            log.warning("emergency with no leader: stopping local outputs")
            self._last_light = Light.RED
            self._out(LightChange(Light.RED))
            self._out(Whistle(5, 500, 500))

    # ---------------------------------------------------------------- status

    def _publish_link(self) -> None:
        w = self.worker
        esp: Optional[EspNowStatus] = w.espnow if w else None
        msg = link_msg(
            w.link if w else "down",
            w.info.fw if w and w.info else "",
            espnow={"mode": esp.mode, "peers": esp.peers, "src": esp.src} if esp else None,
            upstream="up" if self._leader_ok else "down",
        )
        msg["leader_rtt_ms"] = self.leader.rtt_ms  # None until the first clock samples
        msg["leader_offset_ms"] = self.leader.offset_ms
        self.server.publish(msg)


__all__ = ["FollowerService", "snapshot_to_dict"]

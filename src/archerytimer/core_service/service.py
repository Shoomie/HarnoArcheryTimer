"""Core service: wires engine, serial worker and IPC server together.

Engine events fan out in the order the engine emitted them: hardware first (serial
worker), then the state snapshot (IPC). All cross-thread hand-offs are queue puts.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, Clock
from archerytimer.core.engine import Engine
from archerytimer.core.engine_runner import EngineRunner
from archerytimer.core.models import (
    Command,
    EngineSettings,
    Event,
    Sequence,
    SessionConfig,
    Snapshot,
)
from archerytimer.core.rules import timing_info
from archerytimer.core_service.audio_control import AudioControl
from archerytimer.core_service.followers import FollowerRegistry
from archerytimer.core_service.inputs import (
    Binding,
    ButtonMap,
    GpioInput,
    GpioUnavailable,
)
from archerytimer.core_service.meshfeed import session_info, timer_state
from archerytimer.core_service.node import NodeControl
from archerytimer.hardware.mesh_types import ROLE_MASTER, Role
from archerytimer.hardware.protocol import ESPNOW_MODE_NAMES, EspNowStatus
from archerytimer.hardware.serial_worker import SerialWorker
from archerytimer.hardware.sim_device import Port
from archerytimer.ipc.messages import Message, event_msg, hello_msg, link_msg, state_msg
from archerytimer.ipc.server import IpcServer
from archerytimer.ipc.transport import Listener

log = logging.getLogger("archerytimer.core")

SIMPLE_COMMANDS = frozenset(
    {"primary", "start", "pause", "resume", "stop_end", "next", "back", "reset", "emergency"}
)


def _opt_ns(seconds: Any) -> Optional[int]:
    return None if seconds is None else round(float(seconds) * NS_PER_S)


def config_from_args(args: Mapping[str, Any]) -> SessionConfig:
    return SessionConfig(
        sequence_id=str(args["sequence_id"]),
        groups=tuple(str(g) for g in args.get("groups", ("AB",))),
        total_ends=int(args.get("total_ends", 1)),
        practice_ends=int(args.get("practice_ends", 0)),
        alternate_order=bool(args.get("alternate_order", True)),
        auto_advance=bool(args.get("auto_advance", False)),
        auto_advance_delay_ns=round(float(args.get("auto_advance_delay_s", 5)) * NS_PER_S),
        prep_ns=_opt_ns(args.get("prep_s")),
        shoot_ns=_opt_ns(args.get("shoot_s")),
        warn_ns=_opt_ns(args.get("warn_s")),
    )


def translate(msg: Message) -> Optional[Command]:
    """IPC ``cmd``/``settings`` message to an engine ``Command``; None if invalid."""
    try:
        if msg["type"] == "settings":
            return Command("settings", dict(msg.get("values", {})))
        name = str(msg["name"])
        args = msg.get("args") or {}
        if name == "configure":
            return Command("configure", {"config": config_from_args(args)})
        if name == "clear_emergency":
            return Command(name, {"mode": args.get("mode", "continue")})
        if name in SIMPLE_COMMANDS:
            return Command(name)
    except (KeyError, TypeError, ValueError):
        pass
    log.warning("ignoring invalid command %r", msg)
    return None


class CoreService:
    def __init__(
        self,
        clock: Clock,
        sequences: Mapping[str, Sequence],
        listener: Listener,
        *,
        port_factory: Optional[Callable[[], Port]] = None,
        settings: Optional[EngineSettings] = None,
        bindings: Optional[Mapping[str, Binding]] = None,
        espnow: Optional[str] = None,
        audio: Optional[AudioControl] = None,
        node: Optional[NodeControl] = None,
        version: str = "0.0.1",
        master_id: int = 0,
        master_session: int = 1,
        session_bump: Optional[Callable[[], int]] = None,
        mesh_config: Optional[Mapping[str, str]] = None,
        followers: Optional[FollowerRegistry] = None,
        mesh_key_hex: str = "",
        leader_name: str = "",
    ) -> None:
        self._clock = clock
        self._sequences = dict(sequences)
        self._groups: tuple[str, ...] = ()
        self._session_rev = 0
        self._stop_tick = threading.Event()
        self._ticker: Optional[threading.Thread] = None
        names = {sid: seq.name for sid, seq in sequences.items()}
        timings = {sid: timing_info(seq) for sid, seq in sequences.items()}
        self._hello_args = (version, names, timings, master_id)
        self._session_bump = session_bump
        self.followers = followers
        if followers is not None:
            if mesh_key_hex:
                followers.set_mesh_key(mesh_key_hex)
            if leader_name:
                followers.set_leader_name(leader_name)
        self.server = IpcServer(
            listener,
            hello_msg(version, names, timings, master_id, master_session),
            self._on_message,
            clock,
            gate=followers.gate if followers is not None else None,
            on_disconnect=followers.on_disconnect if followers is not None else None,
        )
        if followers is not None:
            followers.set_on_change(self._publish_followers)
        self.engine = Engine(clock, sequences, self._emit, settings, on_late=self._on_late)
        self.runner = EngineRunner(self.engine, clock)
        self.buttons = ButtonMap(bindings or {}, self.runner.send, clock)
        self.worker: Optional[SerialWorker] = (
            SerialWorker(
                port_factory,
                clock,
                self._on_link,
                on_button=lambda i, down: self.buttons.on_event("mcu", i, down),
                on_espnow=self._on_espnow,
                espnow_mode=ESPNOW_MODE_NAMES.get(espnow or ""),
                role=Role(ROLE_MASTER, master_id, master_session) if master_id else None,
                on_connect=self._on_serial_connect,
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
        self._gpio: Optional[GpioInput] = None
        gpio_pins = [int(k.split(":")[1]) for k in (bindings or {}) if k.startswith("gpio:")]
        if gpio_pins:
            try:
                self._gpio = GpioInput(gpio_pins, self.buttons.on_event)
            except GpioUnavailable as exc:
                log.warning("GPIO inputs disabled: %s", exc)

    def start(self) -> None:
        self.server.publish(state_msg(self.engine.snapshot()))
        self._publish_followers()
        if self.worker:
            self.worker.start()
        if self.audio:
            self.audio.start()
        if self.node:
            self.node.start()
        self.runner.start()
        self.server.start()
        self._ticker = threading.Thread(target=self._tick, name="node-tick")
        self._ticker.start()

    def stop(self) -> None:
        """Fail-safe order: stop the engine, then force RED and silence on the hardware."""
        if self._gpio:
            self._gpio.close()
        self._stop_tick.set()
        if self._ticker:
            self._ticker.join(timeout=2.0)
        self.runner.stop()
        if self.node:
            self.node.stop()
        if self.audio:
            self.audio.stop()  # silence the speakers
        if self.worker:
            self.worker.stop()
        self.server.stop()

    def send(self, cmd: Command) -> None:
        self.runner.send(cmd)

    # ---------------------------------------------------------------- callbacks

    def _emit(self, ev: Event) -> None:
        if self.worker:
            self.worker.submit(ev)
        if self.audio:
            self.audio.submit(ev)
        if self.node:
            self.node.submit(ev)
        if isinstance(ev, Snapshot):
            if self.worker:
                self.worker.send_timer_state(
                    timer_state(
                        ev, self._sequences, self._groups, self._session_rev, self._clock.now_ns()
                    )
                )
            log.info(
                "state seq=%d %s %s light=%s group=%s end=%d/%d",
                ev.seq,
                ev.mode.value,
                ev.phase_id,
                ev.light.name,
                ev.group,
                ev.end_no,
                ev.total_ends,
            )
            self.server.publish(state_msg(ev))
        else:
            log.info("event %s", ev)
            msg = event_msg(ev)
            if msg is not None:
                self.server.publish(msg)  # follower cores mirror these onto their own hardware

    def _on_message(self, msg: Message) -> None:
        if self.node and self.node.handle_message(msg):
            return
        if self.audio and self.audio.handle_message(msg):
            return
        if msg.get("type") == "settings":
            values = dict(msg.get("values") or {})
            name = values.pop("espnow", None)
            if name in ESPNOW_MODE_NAMES and self.worker:
                self.worker.set_espnow_mode(ESPNOW_MODE_NAMES[name])
            msg = {**msg, "values": values}
            if not values:
                return
        cmd = translate(msg)
        if cmd is not None:
            log.info("command %s", cmd.name)
            if cmd.name == "configure":
                self._send_session(cmd.args["config"])  # type: ignore[arg-type]
            self.runner.send(cmd)

    def _on_serial_connect(self, role: Role) -> Role:
        """Worker thread, at every serial (re)connect: a new persisted session counter is used for
        ``$R`` (so for every TIMER/SOUND the MCU sends), and mirrors learn it from a new hello."""
        if self._session_bump is None or role.master_id is None:
            return role
        session = self._session_bump()
        version, names, timings, master_id = self._hello_args
        hello = hello_msg(version, names, timings, master_id, session)
        self.server.set_hello(hello)
        self.server.publish(hello)
        return Role(role.role, role.master_id, session)

    def _send_session(self, config: SessionConfig) -> None:
        """A new session: tell the radio (SESSION frame) before the first snapshot of it."""
        self._groups = tuple(config.groups)
        self._session_rev = (self._session_rev + 1) % 256
        if self.worker:
            self.worker.send_session(session_info(config, self._session_rev))

    def _on_mesh(self, frame: object) -> None:
        """Roster, radio status, pairing and remote commands from the MCU (serial reader thread)."""
        if self.node:
            self.node.on_mesh(frame)

    def _tick(self) -> None:
        while not self._stop_tick.wait(1.0):
            if self.node:
                self.node.tick()
            if self.followers:
                self.followers.tick()

    def _publish_followers(self) -> None:
        if self.followers is not None:
            self.server.publish(self.followers.published())

    def _on_link(self, status: str) -> None:
        self.runner.send(Command("link", {"status": status}))
        self.server.publish(self._link_msg(status))

    def _on_espnow(self, status: EspNowStatus) -> None:
        self.server.publish(self._link_msg(self.worker.link if self.worker else "down"))

    def _link_msg(self, status: str) -> Message:
        info = self.worker.info if self.worker else None
        esp = self.worker.espnow if self.worker else None
        return link_msg(
            status,
            info.fw if info else "",
            espnow={"mode": esp.mode, "peers": esp.peers, "src": esp.src} if esp else None,
        )

    def _on_late(self, kind: str, late_ns: int) -> None:
        log.warning("late wake: %s by %.2f ms", kind, late_ns / 1e6)

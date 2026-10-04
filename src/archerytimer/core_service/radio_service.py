"""A core whose timer comes from the radio only (serial role ``E``): no LAN, no leader link.

The attached ESP32 drives this device's lights and horn from the main timer's radio frames; this
service rebuilds the timer for the UI from the frames the MCU forwards (``MeshFollower``) and sends
the operator's commands back over the radio as a paired remote. See ``docs/mesh.md`` section 6.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Callable, Optional

from archerytimer.common.clock import Clock
from archerytimer.core.models import Command, Sequence
from archerytimer.core_service.audio_control import AudioControl
from archerytimer.core_service.inputs import Binding, ButtonMap
from archerytimer.core_service.mesh_follower import MeshFollower
from archerytimer.core_service.node import NodeControl
from archerytimer.hardware.mesh_types import ROLE_RADIO_FED, MeshStatus, Role
from archerytimer.hardware.serial_worker import SerialWorker
from archerytimer.hardware.sim_device import Port
from archerytimer.ipc.messages import Message
from archerytimer.ipc.transport import Listener

log = logging.getLogger("archerytimer.radio_service")


class RadioFollowerService:
    def __init__(
        self,
        clock: Clock,
        sequences: Mapping[str, Sequence],
        listener: Listener,
        port_factory: Callable[[], Port],
        *,
        bindings: Optional[Mapping[str, Binding]] = None,
        mesh_config: Optional[Mapping[str, str]] = None,
        audio: Optional[AudioControl] = None,
        node: Optional[NodeControl] = None,
        version: str = "0.0.1",
    ) -> None:
        self.node = node
        self.audio = audio
        self.worker = SerialWorker(
            port_factory,
            clock,
            lambda _s: self.follower.on_serial_link(),
            on_button=lambda i, down: self.buttons.on_event("mcu", i, down),
            role=Role(ROLE_RADIO_FED),
            config=mesh_config,
            on_feed=lambda f: self.follower.on_feed(f),
            on_mesh_status=self._on_status,
            on_roster=self._on_mesh,
            on_pairing=self._on_mesh,
            on_remote_command=self._on_mesh,
        )
        self.follower = MeshFollower(
            clock,
            listener,
            sequences,
            self.worker,
            serial_link=lambda: self.worker.link,
            on_sound=audio.submit if audio is not None else None,
            version=version,
            local_handler=self._local,
        )
        self.buttons = ButtonMap(bindings or {}, self.follower.forward_command, clock)
        self.server = self.follower.server
        if audio is not None:
            audio.bind(self.server.publish, self.worker)
        if node is not None:
            node.bind(self.server.publish, self.worker)

    def send(self, cmd: Command) -> None:  # a command from a paired remote at this node
        self.follower.forward_command(cmd)

    def start(self) -> None:
        self.worker.start()
        if self.audio:
            self.audio.start()
        if self.node:
            self.node.start()
        self.follower.start()

    def stop(self) -> None:
        """RED and silence first: the worker's stop sends them to the MCU."""
        if self.node:
            self.node.stop()
        if self.audio:
            self.audio.stop()
        self.worker.stop()
        self.follower.stop()

    def _on_status(self, status: MeshStatus) -> None:
        self.follower.on_status(status)
        self._on_mesh(status)

    def _on_mesh(self, frame: object) -> None:
        if self.node:
            self.node.on_mesh(frame)

    def _local(self, msg: Message) -> bool:
        if self.node and self.node.handle_message(msg):
            return True
        return bool(self.audio and self.audio.handle_message(msg))

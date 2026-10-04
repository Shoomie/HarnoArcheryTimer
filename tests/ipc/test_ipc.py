from __future__ import annotations

import time
from typing import Callable, Optional

import pytest

from archerytimer.common.clock import NS_PER_S, MonotonicClock
from archerytimer.core.models import Light, Mode, PhaseSpec, Sequence, Snapshot
from archerytimer.core_service.service import CoreService, translate
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair
from archerytimer.ipc.messages import (
    cmd_msg,
    decode_line,
    encode_line,
    snapshot_from_dict,
    state_msg,
)
from archerytimer.ipc.server import IpcClient
from archerytimer.ipc.transport_inproc import InprocListener
from archerytimer.ipc.transport_socket import SocketListener, connect_socket

SEQ = Sequence(
    "t",
    {"sv": "Test", "en": "Test"},
    (
        PhaseSpec("PREP", NS_PER_S // 4, Light.RED, whistle_on_start=2),
        PhaseSpec("SHOOT", 60 * NS_PER_S, Light.GREEN, 1, warn_at_ns=30 * NS_PER_S),
        PhaseSpec("END", 0, Light.RED, 3),
    ),
)
CONFIGURE = cmd_msg("configure", {"sequence_id": "t", "groups": ["AB", "CD"], "total_ends": 2})


def wait_for(cond: Callable[[], bool], timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def next_state(client: IpcClient, pred: Callable[[Snapshot], bool] = lambda s: True) -> Snapshot:
    end = time.monotonic() + 3
    while time.monotonic() < end:
        msg = client.get(0.2)
        if msg and msg["type"] == "state":
            snap = snapshot_from_dict(msg["state"])
            if pred(snap):
                return snap
    raise AssertionError("expected state message not received")


class Rig:
    def __init__(self, transport: str, with_device: bool = False):
        self.transport = transport
        self.listener = (
            InprocListener() if transport == "inproc" else SocketListener("127.0.0.1", 0)
        )
        self.device: Optional[SimDevice] = None
        self.runner: Optional[SimDeviceRunner] = None
        factory = None
        if with_device:
            self.device = SimDevice()
            host, dev = memory_port_pair()
            self.runner = SimDeviceRunner(self.device, dev, poll_s=0.002).start()
            factory = lambda: host  # noqa: E731
        self.svc = CoreService(MonotonicClock(), {"t": SEQ}, self.listener, port_factory=factory)
        self.clients: list[IpcClient] = []

    def client(self) -> IpcClient:
        if self.transport == "inproc":
            conn = self.listener.connect()  # type: ignore[attr-defined]
        else:
            conn = connect_socket(*self.listener.address)  # type: ignore[attr-defined]
        c = IpcClient(conn)
        self.clients.append(c)
        return c

    def __enter__(self):
        self.svc.start()
        return self

    def __exit__(self, *exc):
        for c in self.clients:
            c.close()
        self.svc.stop()
        if self.runner:
            self.runner.stop()


@pytest.fixture(params=["inproc", "socket"])
def transport(request):
    return request.param


def test_message_roundtrip():
    snap = Snapshot(
        3,
        Mode.RUNNING,
        "t",
        "SHOOT",
        1,
        2,
        False,
        0,
        Light.GREEN,
        "AB",
        1,
        2,
        False,
        0,
        4,
        False,
        "up",
    )
    assert snapshot_from_dict(decode_line(encode_line(state_msg(snap)))["state"]) == snap


def test_translate():
    assert translate(cmd_msg("start")).name == "start"
    assert translate(cmd_msg("bogus")) is None
    assert translate({"type": "cmd", "name": "configure", "args": {}}) is None
    cfg = translate(CONFIGURE).args["config"]
    assert cfg.groups == ("AB", "CD") and cfg.total_ends == 2


def test_connect_gets_hello_then_state(transport):
    with Rig(transport) as rig:
        c = rig.client()
        hello = c.get()
        assert hello["type"] == "hello" and "t" in hello["sequences"]
        assert next_state(c).mode is Mode.IDLE


def test_commands_drive_engine_and_clients_see_state(transport):
    with Rig(transport) as rig:
        c = rig.client()
        c.send(CONFIGURE)
        next_state(c, lambda s: s.mode is Mode.WAITING)
        c.send(cmd_msg("start"))
        snap = next_state(c, lambda s: s.mode is Mode.RUNNING)
        assert snap.group == "AB" and snap.phase_id == "PREP"
        c.send(cmd_msg("emergency"))
        assert next_state(c, lambda s: s.emergency).light is Light.RED
        c.send(
            {"type": "cmd", "name": "configure", "args": {"sequence_id": "nope"}}
        )  # bad: ignored
        c.send({"type": "weird"})  # unknown: ignored
        c.send(cmd_msg("clear_emergency", {"mode": "restart"}))
        assert next_state(c, lambda s: not s.emergency).mode is Mode.WAITING


def test_client_killed_and_restarted_recovers_exact_state(transport):
    with Rig(transport) as rig:
        c1 = rig.client()
        c1.send(CONFIGURE)
        c1.send(cmd_msg("start"))
        next_state(c1, lambda s: s.mode is Mode.RUNNING and s.phase_id == "SHOOT")
        before = rig.svc.server.latest_state
        c1.close()  # UI "crashes"
        assert wait_for(lambda: rig.svc.server.client_count == 0)
        time.sleep(0.1)  # the end keeps running without a UI
        c2 = rig.client()
        c2.get()  # hello
        snap = next_state(c2)
        assert snapshot_from_dict(before["state"]) == snap  # same deadline, same everything
        assert snap.deadline_ns - snap.phase_start_ns == 60 * NS_PER_S
        c2.send(cmd_msg("pause"))
        assert next_state(c2, lambda s: s.paused).phase_id == "SHOOT"


def test_slow_or_dead_clients_never_block_the_engine(transport):
    with Rig(transport) as rig:
        dead = rig.client()
        dead.close()
        c = rig.client()
        c.send(CONFIGURE)
        c.send(cmd_msg("start"))
        next_state(c, lambda s: s.mode is Mode.RUNNING)


def test_hardware_gets_events_and_link_is_reported(transport):
    with Rig(transport, with_device=True) as rig:
        c = rig.client()
        c.send(CONFIGURE)
        c.send(cmd_msg("start"))
        next_state(c, lambda s: s.link == "up" and s.mode is Mode.RUNNING)
        assert rig.device is not None
        assert wait_for(lambda: rig.device.sound_events[:1] == [2])
        next_state(c, lambda s: s.phase_id == "SHOOT")
        assert wait_for(lambda: rig.device.lights == "G")
        c.send(cmd_msg("emergency"))
        assert wait_for(lambda: rig.device.sound_events[-1] == 5 and rig.device.lights == "R")

"""The replay-protection session counter: persisted by RadioKeys, bumped at every serial connect,
sent in ``$R``, passed in the IPC hello and mirrored by follower cores."""

from __future__ import annotations

import json
import time
from pathlib import Path

from archerytimer.common.clock import MonotonicClock
from archerytimer.core.models import Light, PhaseSpec, Sequence
from archerytimer.core_service.cluster import FollowerService
from archerytimer.core_service.radio_keys import FILE_NAME, RadioKeys
from archerytimer.core_service.service import CoreService
from archerytimer.hardware.mesh_types import Role
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair
from archerytimer.ipc.messages import hello_msg
from archerytimer.ipc.transport_inproc import InprocListener

CAPS = "LSBGTKNWR"
SEQ = Sequence("t", {"en": "Test"}, (PhaseSpec("END", 0, Light.RED, 3),))


def wait_for(cond, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def test_session_starts_at_1_and_rises_at_every_start_and_bump(tmp_path: Path) -> None:
    path = tmp_path / FILE_NAME
    first = RadioKeys(path)
    assert first.session == 1
    assert first.bump() == 2
    assert json.loads(path.read_text(encoding="utf-8"))["session"] == 2  # written before use
    second = RadioKeys(path)  # core restart
    assert (second.node_id, second.mesh_key) == (first.node_id, first.mesh_key)
    assert second.session == 3
    assert second.bump() == 4
    assert RadioKeys(path).session == 5
    second.rotate()  # a new mesh key keeps the counter
    assert json.loads(path.read_text(encoding="utf-8"))["session"] == 4


def test_missing_or_damaged_file_gives_a_new_master_identity(tmp_path: Path) -> None:
    path = tmp_path / FILE_NAME
    old = RadioKeys(path)
    old.bump()
    path.write_text("{ not json", encoding="utf-8")
    fresh = RadioKeys(path)
    assert fresh.node_id != old.node_id and fresh.session == 1
    path.unlink()
    again = RadioKeys(path)
    assert again.node_id not in (old.node_id, fresh.node_id) and again.session == 1
    path.write_text(json.dumps({"node_id": "ab", "mesh_key": "00" * 16, "session": -3}))
    assert RadioKeys(path).session == 1  # a bad counter is a damaged file


def test_old_file_without_session_continues_with_1(tmp_path: Path) -> None:
    path = tmp_path / FILE_NAME
    path.write_text(json.dumps({"node_id": "abcd1234", "mesh_key": "00" * 16}), encoding="utf-8")
    keys = RadioKeys(path)
    assert keys.node_id == "abcd1234" and keys.session == 1


def test_hello_carries_master_session() -> None:
    hello = hello_msg("1", {}, None, 0xAB, 9)
    assert hello["master_id"] == 0xAB and hello["master_session"] == 9
    assert hello_msg("1", {})["master_session"] == 0


def test_connect_bumps_session_and_follower_mirrors_it(tmp_path: Path) -> None:
    clock = MonotonicClock()
    keys = RadioKeys(tmp_path / FILE_NAME)
    dev_l, dev_f = SimDevice(caps=CAPS), SimDevice(caps=CAPS)
    runners, ports = [], []
    for dev in (dev_l, dev_f):
        host, d = memory_port_pair()
        runners.append(SimDeviceRunner(dev, d, poll_s=0.002).start())
        ports.append(host)
    leader_listener, follower_listener = InprocListener(), InprocListener()
    leader = CoreService(
        clock,
        {"t": SEQ},
        leader_listener,
        port_factory=lambda: ports[0],
        master_id=0xAB,
        master_session=keys.session,
        session_bump=keys.bump,
    )
    follower = FollowerService(
        clock, leader_listener.connect, follower_listener, port_factory=lambda: ports[1]
    )
    leader.start()
    follower.start()
    try:
        assert wait_for(lambda: dev_l.role == Role("M", 0xAB, 2))  # core start 1, first connect 2
        assert wait_for(lambda: dev_f.role == Role("F", 0xAB, 2))
        assert keys.session == 2
        leader.worker.set_session(7)  # the worker can change the session while running
        assert wait_for(lambda: dev_l.role == Role("M", 0xAB, 7))
    finally:
        follower.stop()
        leader.stop()
        for r in runners:
            r.stop()

from __future__ import annotations

import time

from archerytimer.common.clock import NS_PER_S, MonotonicClock
from archerytimer.core.models import Light, Mode, PhaseSpec, Sequence
from archerytimer.core_service.cluster import FollowerService
from archerytimer.core_service.service import CoreService
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair
from archerytimer.ipc.link import CoreLink
from archerytimer.ipc.messages import cmd_msg, snapshot_from_dict
from archerytimer.ipc.server import IpcClient
from archerytimer.ipc.transport_inproc import InprocListener

SEQ = Sequence(
    "t",
    {"en": "Test"},
    (
        PhaseSpec("PREP", NS_PER_S // 5, Light.RED, whistle_on_start=2),
        PhaseSpec("SHOOT", 60 * NS_PER_S, Light.GREEN, 1),
        PhaseSpec("END", 0, Light.RED, 3),
    ),
)


def wait_for(cond, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def test_follower_mirrors_leader_forwards_commands_and_fails_safe():
    clock = MonotonicClock()
    dev_l, dev_f = SimDevice(), SimDevice()
    runners = []
    ports = []
    for dev in (dev_l, dev_f):
        host, d = memory_port_pair()
        runners.append(SimDeviceRunner(dev, d, poll_s=0.002).start())
        ports.append(host)
    leader_listener, follower_listener = InprocListener(), InprocListener()
    leader = CoreService(clock, {"t": SEQ}, leader_listener, port_factory=lambda: ports[0])
    follower = FollowerService(
        clock, leader_listener.connect, follower_listener, port_factory=lambda: ports[1]
    )
    leader.start()
    follower.start()
    ui = IpcClient(follower_listener.connect())  # a screen attached to the *follower*
    try:
        from archerytimer.core.models import Command, SessionConfig

        leader.send(Command("configure", {"config": SessionConfig("t", total_ends=1)}))
        assert wait_for(lambda: follower.worker and follower.worker.link == "up")
        # a command given on the follower runs the session on the leader
        assert wait_for(lambda: follower.leader.connected and follower.leader.estimator.synced)
        ui.send(cmd_msg("primary"))
        # both devices get the whistle and the green light
        assert wait_for(lambda: dev_l.sound_events[:1] == [2] and dev_f.sound_events[:1] == [2])
        assert wait_for(lambda: dev_l.lights == "G" and dev_f.lights == "G")
        # the follower's screen gets the state with deadlines in its own clock
        snap = None
        end = time.monotonic() + 3
        while time.monotonic() < end and (snap is None or snap.phase_id != "SHOOT"):
            msg = ui.get(0.2)
            if msg and msg["type"] == "state":
                snap = snapshot_from_dict(msg["state"])
        assert snap is not None and snap.mode is Mode.RUNNING
        remaining = snap.deadline_ns - clock.now_ns()
        assert 50 * NS_PER_S < remaining <= 60 * NS_PER_S
        # emergency from the follower stops both
        ui.send(cmd_msg("emergency"))
        assert wait_for(lambda: dev_l.lights == "R" and dev_f.lights == "R")
        assert wait_for(lambda: dev_f.sound_events[-1] == 5)
        # leader dies: the follower goes RED by itself
        ui.send(cmd_msg("clear_emergency", {"mode": "continue"}))
        ui.send(cmd_msg("resume"))
        assert wait_for(lambda: dev_f.lights == "G")
        leader.stop()
        assert wait_for(lambda: dev_f.lights == "R", timeout=4.0)
    finally:
        ui.close()
        follower.stop()
        leader.stop()
        for r in runners:
            r.stop()
    assert isinstance(follower.leader, CoreLink)

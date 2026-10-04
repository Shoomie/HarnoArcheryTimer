"""Scenario tests on the discrete-event mesh simulator (fake clock, seeded, no sleeping)."""

from __future__ import annotations

from typing import Any

import pytest
from tools.mesh_sim.arbiter import LIGHT_BITS
from tools.mesh_sim.sim import (
    MESH_KEY,
    US,
    BurstChannel,
    FollowerNode,
    MasterNode,
    Radio,
    RemoteNode,
    Sim,
    mac_of,
)

from archerytimer.hardware import mesh_codec as mc
from archerytimer.hardware.mesh_types import ACTION_CODES

G, R = LIGHT_BITS["G"], LIGHT_BITS["R"]
REMOTE_KEY = bytes(range(0x10, 0x20))
ALL_MASK = 0x7F


def build(
    seed: int, followers: int = 4, loss: float = 0.0, burst: bool = False, **radio_kw: Any
) -> tuple[Sim, Radio, MasterNode, list[FollowerNode]]:
    sim = Sim(seed)
    ch = BurstChannel(sim.rng, 300, 30) if burst else None
    radio = Radio(sim, loss=loss, burst=ch, **radio_kw)
    master = MasterNode(sim, radio, mac_of(1), master_id=0xA1)
    fl = [FollowerNode(sim, radio, mac_of(10 + i)) for i in range(followers)]
    return sim, radio, master, fl


def test_followers_track_master() -> None:
    sim, _, master, fl = build(1, loss=0.1)
    master.host.lights = G
    sim.run_for(2000)
    assert all(f.lights_at_now() == G for f in fl)
    master.host.lights = R
    master.host_changed()
    sim.run_for(250)
    assert all(f.lights_at_now() == R for f in fl)


def test_no_flip_flop_with_two_masters() -> None:
    sim, radio, a, fl = build(2, followers=5, loss=0.15)
    a.host.lights = G
    a.host_changed()
    sim.run_for(100)  # A is clearly first
    b = MasterNode(sim, radio, mac_of(2), master_id=0xB2)
    b.host.lights = R
    b.host_changed()
    sim.run_for(20000)
    for f in fl:
        assert [x for _, x in f.follow_log if x is not None] == [0xA1], f.follow_log  # never flips
        assert f.lights_log[-1][1] == G
        assert f.arb.conflict(sim.now_ms)
    assert a.arb.conflict(sim.now_ms) and b.arb.conflict(sim.now_ms)
    # when the followed master dies, followers move on to the other one
    a.host.alive = False
    a.host_changed()
    sim.run_for(3000)
    for f in fl:
        picks = [x for _, x in f.follow_log if x is not None]
        assert picks == [0xA1, 0xB2], f.follow_log
        assert f.lights_log[-1][1] == R


def test_rebooted_transmitter_accepted_again_within_1s() -> None:
    sim, _, master, fl = build(3, loss=0.1)
    master.host.lights = G
    sim.run_for(5000)
    for _ in range(3):
        master.host_changed()
    sim.run_for(1000)
    old_epoch, old_seq = master.epoch, master.seq
    assert old_seq > 20  # the old epoch is far ahead of the restarted counter
    t_reboot = sim.now_us
    master.reboot(down_ms=100)
    master.host.lights = R  # the new boot shows something different, so acceptance is visible
    master.host_changed()
    sim.run_for(1000)
    assert master.epoch != old_epoch and master.seq < old_seq
    for f in fl:
        t_first = min(t for t, p in f.rx_log if t > t_reboot + 100 * US and p == mc.T_TIMER)
        assert (t_first - t_reboot) / US < 1000
        assert f.lights_at_now() == R


def test_seq_only_filter_would_reject_reboot_negative_control() -> None:
    d = mc.Dedupe()
    m = mac_of(1)
    assert d.accept(m, 111, 9000)
    assert d.accept(m, 222, 1)  # new epoch, lower seq: accepted at once
    assert not mc.seq_newer(1, 9000)  # what a v1 style seq-only check would have said


def _emergency_delay_ms(seed: int, loss: float, burst: bool) -> float:
    sim, _, master, fl = build(seed, followers=5, loss=loss, burst=burst)
    master.host.lights = G
    sim.run_for(1000 + sim.rng.uniform(0, 200))  # random heartbeat phase
    t0 = sim.now_us
    master.set_emergency(True)
    sim.run_for(600)
    worst = 0.0
    for f in fl:
        assert f.first_emergency_us is not None, f"seed {seed}: follower never saw it"
        worst = max(worst, (f.first_emergency_us - t0) / US)
    return worst


def test_emergency_delivered_within_250ms_at_30pct_loss() -> None:
    worst = max(_emergency_delay_ms(s, 0.30, False) for s in range(200))
    assert worst < 250, worst


def test_emergency_delivered_under_500ms_in_every_burst_run() -> None:
    # 5 followers, 30 % independent loss plus global bursts (mean 30 ms about every 300 ms, 100 % loss
    # inside a burst); the safety-direction repeats (TIMER every 50 ms for 500 ms) must close the tail.
    delays = [_emergency_delay_ms(s, 0.30, True) for s in range(2000)]
    over_250 = sum(d > 250 for d in delays)
    print(f"emergency delivery over 2000 runs: worst {max(delays):.1f} ms, >250 ms: {over_250}")
    assert max(delays) < 500, max(delays)


def test_emergency_delivered_under_500ms_with_bursts_only() -> None:
    delays = [_emergency_delay_ms(s, 0.0, True) for s in range(500)]
    print(
        f"bursts only, 500 runs: worst {max(delays):.1f} ms, >250 ms: {sum(d > 250 for d in delays)}"
    )
    assert max(delays) < 500, max(delays)


def test_lights_to_red_and_sound_stop_are_repeated_for_500ms() -> None:
    sim, radio, master, _ = build(5)
    master.host.lights = G
    master.host_changed()
    sim.run_for(1000)

    def timers_since(t0: int) -> list[bytes]:
        return [
            d for t, s, d in radio.capture if t >= t0 and s == master.mac and d[2] == mc.T_TIMER
        ]

    t0 = sim.now_us
    master.host.lights = R
    master.host_changed()
    sim.run_for(100)
    first = next(d for d in timers_since(t0) if d[17] == R)  # lights byte
    assert timers_since(t0).count(first) == 4 + 2  # 0/3/15/40 plus 50 and 100 ms, one frame
    sim.run_for(600)
    assert timers_since(t0).count(first) == 4 + 10  # every 50 ms for 500 ms, then it stops
    t1 = sim.now_us
    master.stop_sound()
    sim.run_for(40)
    first = timers_since(t1)[0]
    assert timers_since(t1).count(first) == 4
    sim.run_for(70)
    assert timers_since(t1).count(first) == 6


def _two_sessions(seed: int) -> tuple[Sim, Radio, MasterNode, list[FollowerNode], bytes]:
    sim, radio, master, fl = build(seed)
    master.host.lights = R  # the old session's frame says RED ...
    master.host_changed()
    sim.run_for(300)
    old = next(d for _, s, d in reversed(radio.capture) if s == master.mac and d[2] == mc.T_TIMER)
    master.session = 2  # ... the core restarted: new session, lights GREEN now
    master.reboot(50)
    master.host.lights = G
    master.host_changed()
    sim.run_for(1000)
    assert all(f.lights_at_now() == G for f in fl)
    return sim, radio, master, fl, old


def test_replayed_old_session_timer_cannot_flip_a_node() -> None:
    sim, radio, master, fl, old = _two_sessions(21)
    radio.inject(master.mac, old)  # new epoch of the reboot: dedupe alone would accept it
    t_replay = sim.now_us
    sim.run_for(5)
    assert all(f.lights_at_now() == G for f in fl)
    sim.run_for(500)
    for f in fl:
        assert f.lights_at_now() == G
        assert not any(t >= t_replay and lt == R for t, lt in f.lights_log)
        assert [x for _, x in f.follow_log if x is not None] == [0xA1]


def test_replayed_old_session_timer_rejected_also_after_node_reboot() -> None:
    sim, radio, master, fl, old = _two_sessions(22)
    radio.partition([[master.mac], [f.mac for f in fl]])  # the real master is out of range
    for f in fl:
        f.reboot(20)
    sim.run_for(50)
    radio.inject(master.mac, old)
    sim.run_for(100)
    assert all(f.arb.followed_timer(sim.now_ms) is None for f in fl)  # nothing was heard
    assert all(f.arb.sessions[master.master_id] == 2 for f in fl)  # persisted across the reboot
    radio.heal()
    sim.run_for(400)
    assert all(f.lights_at_now() == G for f in fl)


def test_emergency_latch_forces_red_on_followers() -> None:
    sim, _, master, fl = build(4, loss=0.1)
    master.host.lights = G
    sim.run_for(1000)
    master.set_emergency(True)
    master.host.lights = G  # host lights say green, the latch must win
    master.send_timer()
    sim.run_for(500)
    assert all(f.lights_at_now() == R for f in fl)


def test_sound_heals_from_timer_when_sound_frame_lost() -> None:
    sim, radio, master, fl = build(5, loss=0.2)
    radio.drop_filter = lambda src, dst, data: data[2] == mc.T_SOUND  # every SOUND frame lost
    sim.run_for(1000)
    master.play_sound(3)
    sim.run_for(1000)
    for f in fl:
        assert len(f.sound_log) == 1, f.sound_log  # started once, from TIMER
        t, count = f.sound_log[0]
        assert count == 3 and t > master.sound_log[0]
        assert (t - master.sound_log[0]) / US < 400  # inside the replay guard


def test_sound_stop_reaches_all_followers_within_500ms_at_30pct_loss() -> None:
    for seed in range(1, 9):
        sim, _, master, fl = build(seed, followers=5, loss=0.3)
        sim.run_for(1000)
        master.play_sound(5)
        sim.run_for(300)
        t0 = sim.now_us
        master.stop_sound()
        sim.run_for(600)
        for f in fl:
            stops = [t for t in f.stop_log if t >= t0]
            assert stops, (seed, f.name)
            assert (stops[0] - t0) / US < 500, (seed, stops[0] - t0)
            assert not f.arb.sound_active(sim.now_ms)


def test_sound_frame_and_timer_start_once() -> None:
    sim, _, master, fl = build(6, loss=0.1)
    sim.run_for(1000)
    master.play_sound(2)
    sim.run_for(1500)
    master.play_sound(1)
    sim.run_for(1500)
    for f in fl:
        assert [c for _, c in f.sound_log] == [2, 1]


def _remote_setup(
    seed: int, **kw: Any
) -> tuple[Sim, Radio, MasterNode, list[FollowerNode], RemoteNode]:
    sim, radio, master, fl = build(seed, followers=2, **kw)
    remote = RemoteNode(sim, radio, mac_of(50), REMOTE_KEY)
    master.pair_remote(remote.mac, REMOTE_KEY, ALL_MASK)
    sim.run_for(500)
    return sim, radio, master, fl, remote


def test_cmd_executed_exactly_once_with_duplicates_and_loss() -> None:
    for seed in range(20):
        sim, _, master, _, remote = _remote_setup(seed, loss=0.3, dup=0.5)
        c = remote.send_named("pause")
        sim.run_for(500)
        runs = [e for e in master.host.executed if e[3] == c]
        assert len(runs) == 1, seed
        assert c in remote.acked and remote.acked[c][1] == mc.RESULT_DONE, seed


def test_cmd_same_counter_resent_later_is_reacked_not_reexecuted() -> None:
    sim, _, master, _, remote = _remote_setup(7)
    c = remote.send_named("next")
    sim.run_for(300)
    assert len(master.host.executed) == 1 and c in remote.acked
    remote.acked.clear()
    remote.send_cmd(ACTION_CODES["next"], counter=c)  # the remote never saw the ACK
    sim.run_for(300)
    assert len(master.host.executed) == 1
    assert remote.acked[c][1] == mc.RESULT_DONE


def test_cmd_from_rebooted_remote_continues_counter() -> None:
    sim, _, master, _, remote = _remote_setup(8)
    remote.send_named("pause")
    sim.run_for(300)
    remote.reboot(50)
    sim.run_for(100)
    remote.send_named("resume")
    sim.run_for(300)
    assert [e[3] for e in master.host.executed] == [1, 2]


def test_unauthorized_cmd_rejected() -> None:
    sim, radio, master, _, remote = _remote_setup(9)
    stranger = RemoteNode(sim, radio, mac_of(60), bytes(range(0x30, 0x40)))  # never paired
    stranger.send_named("emergency")
    forged = RemoteNode(sim, radio, mac_of(61), REMOTE_KEY)  # right key, not on the roster
    forged.send_named("emergency")
    liar = RemoteNode(sim, radio, remote.mac[:5] + b"\x77", bytes(16))  # wrong key
    liar.send_named("emergency")
    sim.run_for(500)
    assert master.host.executed == []
    assert not master.host.flags
    assert not stranger.acked and not forged.acked and not liar.acked


def test_cmd_denied_by_permission_mask_and_emergency_always_allowed() -> None:
    sim, radio, master, fl = build(10, followers=2)
    limited = RemoteNode(sim, radio, mac_of(51), REMOTE_KEY)
    master.pair_remote(limited.mac, REMOTE_KEY, 1 << (ACTION_CODES["primary"] - 1))
    sim.run_for(300)
    c = limited.send_named("next")
    sim.run_for(300)
    assert master.host.executed == []
    assert limited.acked[c][1] == mc.RESULT_DENIED
    e = limited.send_named("emergency")
    sim.run_for(300)
    assert [x[3] for x in master.host.executed] == [e]
    assert all(f.first_emergency_us is not None for f in fl)


def test_replayed_cmd_rejected() -> None:
    sim, radio, master, _, remote = _remote_setup(11)
    remote.send_named("pause")
    sim.run_for(300)
    first_cmd = next(d for _, s, d in radio.capture if s == remote.mac and d[2] == mc.T_CMD)
    remote.send_named("resume")
    sim.run_for(300)
    assert len(master.host.executed) == 2
    # replay of the captured frame: same epoch and seq (frame dedupe stops it); again after the
    # remote rebooted (its new epoch makes the frame dedupe forget, the counter check must stop it);
    # and a tampered copy (tag fails)
    radio.inject(remote.mac, first_cmd)
    remote.reboot(50)
    sim.run_for(100)
    radio.inject(remote.mac, first_cmd)
    tampered = bytearray(first_cmd)
    tampered[8] ^= 0xFF
    radio.inject(remote.mac, bytes(tampered))
    sim.run_for(300)
    assert [x[3] for x in master.host.executed] == [1, 2]


def test_cmd_refused_while_host_dead() -> None:
    sim, _, master, _, remote = _remote_setup(12)
    master.host.alive = False
    master.host_changed()
    remote.send_named("pause")
    sim.run_for(400)
    assert master.host.executed == [] and not remote.acked


def test_partition_goes_red_and_heals() -> None:
    sim, radio, master, fl = build(13, loss=0.05)
    master.host.lights = G
    sim.run_for(2000)
    assert all(f.lights_at_now() == G for f in fl)
    radio.partition([[master.mac], [f.mac for f in fl]])
    sim.run_for(1100)
    assert all(f.lights_at_now() == R and f.arb.failsafe(sim.now_ms) for f in fl)
    radio.heal()
    sim.run_for(400)
    assert all(f.lights_at_now() == G for f in fl)


def test_follower_reboot_recovers() -> None:
    sim, _, master, fl = build(14, loss=0.1)
    master.host.lights = G
    sim.run_for(1500)
    fl[0].reboot(50)
    sim.run_for(530)
    assert fl[0].lights_at_now() == G


@pytest.mark.parametrize("seed", range(3))
def test_deterministic_per_seed(seed: int) -> None:
    def trace() -> list[tuple[int, int]]:
        sim, _, master, fl = build(seed, loss=0.3, burst=True)
        master.host.lights = G
        sim.run_for(3000)
        return fl[0].lights_log

    assert trace() == trace()


def test_mesh_key_is_16_bytes() -> None:
    assert len(MESH_KEY) == 16

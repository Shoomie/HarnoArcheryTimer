"""The leader's radio feed (meshfeed) decoded by the radio follower: same timer on both ends."""

from __future__ import annotations

from pathlib import Path

from archerytimer.common.clock import NS_PER_MS, NS_PER_S, FakeClock
from archerytimer.core.engine import Engine
from archerytimer.core.models import Command, Event, Light, Mode, SessionConfig
from archerytimer.core.rules import load_sequences
from archerytimer.core_service.mesh_follower import MeshFollower
from archerytimer.core_service.meshfeed import (
    master_id_from,
    radio_name,
    session_info,
    timer_state,
)
from archerytimer.hardware.mesh_types import (
    KEEP,
    FeedSession,
    FeedTimer,
    RadioSession,
    RadioTimer,
)
from archerytimer.ipc.messages import snapshot_from_dict
from archerytimer.ipc.transport_inproc import InprocListener

SEQS = load_sequences(Path(__file__).resolve().parents[2] / "config" / "sequences")
CFG = SessionConfig("indoor_3arrows", ("AB", "CD"), total_ends=3, practice_ends=1, warn_ns=0)
MASTER = master_id_from("abcd1234")
LIGHT_BITS = {Light.GREEN: 1, Light.YELLOW: 2, Light.RED: 4}


def radio_frames(snap, info, groups, clock):
    """What the MCU would put on the radio for the host's last $U and $J."""
    ts = timer_state(snap, SEQS, groups, info.rev, clock.now_ns())
    timer = RadioTimer(
        MASTER, 2, LIGHT_BITS.get(snap.light, 0), ts.flags, ts.mode, ts.phase, ts.remaining_ms,
        ts.end_no, ts.total_ends, ts.group, ts.round, ts.total_rounds, ts.rev, 0, 0, 0, 0,
    )  # fmt: skip
    session = RadioSession(
        MASTER, info.rev, info.alternate_order, info.auto_advance, info.total_ends,
        info.practice_ends, info.prep_ms, info.shoot_ms, info.warn_ms, info.auto_delay_ms,
        info.sequence_id, info.groups,
    )  # fmt: skip
    return FeedSession(session.to_bytes()), FeedTimer(timer.to_bytes())


def test_follower_decodes_what_the_leader_encodes():
    clock = FakeClock()
    events: list[Event] = []
    engine = Engine(clock, SEQS, events.append)
    engine.configure(CFG)
    info = session_info(CFG, 1)
    follower = MeshFollower(clock, InprocListener(), SEQS, tx=_Tx())
    engine.handle(Command("primary"))
    for step_s in (0, 9.9, 0.2, 60, 35, 24.9, 0.2):
        clock.advance(round(step_s * NS_PER_S))
        engine.poll()
        clock.advance(2 * NS_PER_MS)  # radio latency
        sess, timer = radio_frames(engine.snapshot(), info, CFG.groups, clock)
        follower.on_feed(sess)
        follower.on_feed(timer)
        leader = engine.snapshot()
        got = snapshot_from_dict(follower.server.latest_state["state"])
        assert got.mode is leader.mode
        for name in ("phase_id", "light", "group", "end_no", "round_index", "paused", "emergency"):
            assert getattr(got, name) == getattr(leader, name), (step_s, name)
        if leader.mode is Mode.RUNNING:
            assert abs(got.deadline_ns - leader.deadline_ns) <= 5 * NS_PER_MS


def test_emergency_and_pause_carry_the_frozen_time():
    clock = FakeClock()
    engine = Engine(clock, SEQS, lambda _e: None)
    engine.configure(CFG)
    engine.handle(Command("primary"))
    clock.advance(12 * NS_PER_S)
    engine.poll()
    engine.handle(Command("pause"))
    snap = engine.snapshot()
    ts = timer_state(snap, SEQS, CFG.groups, 1, clock.now_ns())
    assert ts.flags & 1 and ts.remaining_ms == snap.remaining_at_pause_ns // NS_PER_MS
    clock.advance(30 * NS_PER_S)  # time passing while paused changes nothing
    assert timer_state(snap, SEQS, CFG.groups, 1, clock.now_ns()).remaining_ms == ts.remaining_ms


def test_session_info_units():
    info = session_info(
        SessionConfig("free", ("AB",), prep_ns=None, shoot_ns=90 * NS_PER_S, warn_ns=0), 300
    )
    assert info.rev == 300 % 256
    assert info.prep_ms == KEEP and info.shoot_ms == 90_000 and info.warn_ms == 0
    assert info.auto_delay_ms == 5000 and info.groups == ("AB",)


def test_identity_helpers():
    assert master_id_from("abcd1234") == master_id_from("abcd1234") != master_id_from("abcd1235")
    assert 0 < master_id_from("x") < 2**32
    assert radio_name("Simon's PC!") == "Simon-s-PC" and radio_name("???") == "timer"
    assert len(radio_name("a" * 40)) == 12


class _Tx:
    def send_pair_tx(self, action: int) -> None:  # pragma: no cover - unused here
        pass

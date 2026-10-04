from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

from archerytimer.common.clock import NS_PER_MS, NS_PER_S, FakeClock
from archerytimer.core.engine import Engine
from archerytimer.core.models import (
    Command,
    Event,
    Light,
    Mode,
    SessionConfig,
    Snapshot,
    Whistle,
)
from archerytimer.core.rules import apply_overrides, load_sequences
from archerytimer.core_service.mesh_follower import MeshFollower
from archerytimer.hardware.mesh_types import (
    ACTION_CODES,
    FLAG_EMERGENCY,
    FLAG_PAUSED,
    KEEP,
    MODES,
    FeedSession,
    FeedSound,
    FeedTimer,
    RadioSession,
    RadioSound,
    RadioTimer,
)
from archerytimer.ipc.messages import cmd_msg, snapshot_from_dict
from archerytimer.ipc.transport_inproc import InprocListener

SEQS = load_sequences(Path(__file__).resolve().parents[2] / "config" / "sequences")
SEQ_ID = "indoor_3arrows"
MASTER = 0xA1B2C3D4
LIGHT_BITS = {Light.GREEN: 1, Light.YELLOW: 2, Light.RED: 4}


class Tx:
    def __init__(self) -> None:
        self.sent: list[int] = []

    def send_pair_tx(self, action: int) -> None:
        self.sent.append(action)


def make(clock: FakeClock, **kw):
    tx = Tx()
    f = MeshFollower(clock, InprocListener(), SEQS, tx, **kw)
    return f, tx


def latest(f: MeshFollower) -> Optional[Snapshot]:
    msg = f.server.latest_state
    return snapshot_from_dict(msg["state"]) if msg else None


class Leader:
    """The real engine plus the encoding the master's MCU would put on the radio."""

    def __init__(self, clock: FakeClock, cfg: SessionConfig, rev: int = 1) -> None:
        self.clock = clock
        self.cfg = cfg
        self.rev = rev
        self.events: list[Event] = []
        self.engine = Engine(clock, SEQS, self.events.append)
        self.engine.configure(cfg)
        self.seq = apply_overrides(SEQS[cfg.sequence_id], cfg.prep_ns, cfg.shoot_ns, cfg.warn_ns)

    def session(self) -> RadioSession:
        c = self.cfg

        def ms(v: Optional[int]) -> int:
            return KEEP if v is None else v // NS_PER_MS

        return RadioSession(
            MASTER, self.rev, c.alternate_order, c.auto_advance, c.total_ends, c.practice_ends,
            ms(c.prep_ns), ms(c.shoot_ns), ms(c.warn_ns), c.auto_advance_delay_ns // NS_PER_MS,
            c.sequence_id, c.groups,
        )  # fmt: skip

    def timer(self) -> RadioTimer:
        s = self.engine.snapshot()
        now = self.clock.now_ns()
        running = s.mode is Mode.RUNNING
        if s.paused or (s.emergency and running):
            rem = s.remaining_at_pause_ns
        elif running:
            rem = max(0, s.deadline_ns - now)
        else:
            rem = 0
        flags = (FLAG_PAUSED if s.paused else 0) | (FLAG_EMERGENCY if s.emergency else 0)
        ids = [p.id for p in self.seq.phases]
        return RadioTimer(
            MASTER, 2, LIGHT_BITS[s.light], flags, MODES.index(s.mode.value),
            ids.index(s.phase_id), rem // NS_PER_MS, s.end_no, s.total_ends,
            self.cfg.groups.index(s.group), s.round_index, s.total_rounds, self.rev,
            0, 0, 0, 0,
        )  # fmt: skip

    def feed(self, f: MeshFollower, session: bool = True) -> None:
        if session:
            f.on_feed(FeedSession(self.session().to_bytes()))
        f.on_feed(FeedTimer(self.timer().to_bytes()))


def assert_same(leader: Snapshot, got: Snapshot) -> None:
    assert got.mode is leader.mode
    for name in (
        "sequence_id", "phase_id", "paused", "light", "group", "end_no", "total_ends",
        "practice", "round_index", "total_rounds", "emergency", "planned_ns",
    ):  # fmt: skip
        assert getattr(got, name) == getattr(leader, name), name
    if leader.mode is Mode.RUNNING:
        assert abs(got.deadline_ns - leader.deadline_ns) <= 5 * NS_PER_MS
        assert abs(got.phase_start_ns - leader.phase_start_ns) <= 5 * NS_PER_MS
    if leader.mode is Mode.RUNNING and (leader.paused or leader.emergency):
        assert got.remaining_at_pause_ns == leader.remaining_at_pause_ns // NS_PER_MS * NS_PER_MS


CFG = SessionConfig(SEQ_ID, ("AB", "CD"), total_ends=3, practice_ends=1)


def test_snapshot_matches_leader_through_a_round():
    clock = FakeClock()
    leader = Leader(clock, CFG)
    f, _ = make(clock)
    assert f.waiting_for_main_timer
    leader.feed(f)
    assert not f.waiting_for_main_timer
    assert_same(leader.engine.snapshot(), latest(f))

    leader.engine.handle(Command("primary"))  # PREP, RED
    leader.feed(f)
    assert_same(leader.engine.snapshot(), latest(f))
    for step_s in (9.9, 0.2, 60, 35, 24.9, 0.2, 5):  # PREP end, SHOOT, warning, END, waiting
        clock.advance(round(step_s * NS_PER_S))
        leader.engine.poll()
        clock.advance(3 * NS_PER_MS)  # radio latency
        leader.feed(f)
        assert_same(leader.engine.snapshot(), latest(f))
    assert latest(f).round_index == 1


def test_overrides_practice_and_group_rotation():
    clock = FakeClock()
    cfg = SessionConfig(
        SEQ_ID, ("AB", "CD"), total_ends=2, practice_ends=1,
        prep_ns=4 * NS_PER_S, shoot_ns=90 * NS_PER_S, warn_ns=0,
    )  # fmt: skip
    leader = Leader(clock, cfg)
    f, _ = make(clock)
    leader.feed(f)
    for _ in range(3):  # three rounds: practice AB, practice CD, end 1 CD (rotated)
        leader.engine.handle(Command("primary"))
        clock.advance(2 * NS_PER_S)
        leader.engine.poll()
        leader.feed(f)
        assert_same(leader.engine.snapshot(), latest(f))
        clock.advance(100 * NS_PER_S)
        leader.engine.poll()
        leader.feed(f)
        assert_same(leader.engine.snapshot(), latest(f))
    snap = latest(f)
    assert snap.practice is False and snap.end_no == 1 and snap.round_index == 3
    assert snap.group == "AB"  # end 1 rotates: CD then AB


def test_pause_resume_and_emergency():
    clock = FakeClock()
    leader = Leader(clock, CFG)
    f, _ = make(clock)
    leader.feed(f)
    leader.engine.handle(Command("primary"))
    clock.advance(15 * NS_PER_S)
    leader.engine.poll()
    leader.feed(f)
    leader.engine.handle(Command("pause"))
    leader.feed(f)
    paused = latest(f)
    assert paused.paused and paused.light is Light.RED
    assert_same(leader.engine.snapshot(), paused)
    clock.advance(30 * NS_PER_S)  # paused: nothing moves
    leader.feed(f)
    again = latest(f)
    assert again.deadline_ns == paused.deadline_ns
    assert again.remaining_at_pause_ns == paused.remaining_at_pause_ns
    leader.engine.handle(Command("resume"))
    leader.feed(f)
    assert_same(leader.engine.snapshot(), latest(f))
    clock.advance(10 * NS_PER_S)
    leader.engine.handle(Command("emergency"))
    leader.feed(f)
    snap = latest(f)
    assert snap.emergency and snap.light is Light.RED
    assert_same(leader.engine.snapshot(), snap)


def test_repeated_frames_do_not_move_the_deadline_or_spam():
    clock = FakeClock()
    leader = Leader(clock, CFG)
    f, _ = make(clock)
    leader.feed(f)
    leader.engine.handle(Command("primary"))
    clock.advance(11 * NS_PER_S)
    leader.engine.poll()
    frame = FeedTimer(leader.timer().to_bytes())
    f.on_feed(frame)
    first = latest(f)
    for delay_ms in (3, 12, 25):  # TIMER repeats (0, 3, 15, 40 ms) carry the same value
        clock.advance(delay_ms * NS_PER_MS)
        f.on_feed(frame)
    assert latest(f).deadline_ns == first.deadline_ns
    assert latest(f).seq == first.seq


def test_feed_lost_goes_red_and_upstream_down_then_recovers():
    clock = FakeClock()
    leader = Leader(clock, CFG)
    f, _ = make(clock)
    leader.feed(f)
    leader.engine.handle(Command("primary"))
    clock.advance(11 * NS_PER_S)
    leader.engine.poll()
    leader.feed(f)
    assert latest(f).light is Light.GREEN
    assert f.server._latest["link"]["upstream"] == "up"
    clock.advance(900 * NS_PER_MS)
    f.check()
    assert latest(f).light is Light.GREEN
    clock.advance(150 * NS_PER_MS)
    f.check()
    assert latest(f).light is Light.RED
    assert f.server._latest["link"]["upstream"] == "down"
    leader.feed(f)  # the master is back
    assert latest(f).light is Light.GREEN
    assert f.server._latest["link"]["upstream"] == "up"


def test_missing_unknown_and_changed_session():
    clock = FakeClock()
    leader = Leader(clock, CFG)
    f, _ = make(clock)
    leader.feed(f, session=False)  # TIMER only
    snap = latest(f)
    assert f.waiting_for_main_timer
    assert snap.mode is Mode.IDLE and snap.sequence_id == "" and snap.light is Light.RED

    unknown = RadioSession(MASTER, 1, True, False, 3, 1, KEEP, KEEP, KEEP, 5000, "nope", ("AB",))
    f.on_feed(FeedSession(unknown.to_bytes()))
    assert f.waiting_for_main_timer

    leader.feed(f)
    assert not f.waiting_for_main_timer
    leader.rev = 2  # session_rev changed in TIMER, new SESSION not yet heard
    f.on_feed(FeedTimer(leader.timer().to_bytes()))
    assert f.waiting_for_main_timer
    leader.feed(f)
    assert not f.waiting_for_main_timer
    f.on_feed(FeedTimer(b"short"))  # garbage never raises
    f.on_feed(FeedSession(b"\x00"))


def test_commands_map_to_radio_actions_and_others_are_refused(caplog):
    clock = FakeClock()
    f, tx = make(clock)
    for name in ("primary", "pause", "resume", "stop_end", "next", "back", "emergency"):
        f._on_local_message(cmd_msg(name))
    assert tx.sent == [ACTION_CODES[n] for n in
                       ("primary", "pause", "resume", "stop_end", "next", "back", "emergency")]  # fmt: skip
    tx.sent.clear()
    with caplog.at_level("WARNING"):
        for name in ("reset", "clear_emergency", "configure", "start", "quit"):
            f._on_local_message(cmd_msg(name))
        f._on_local_message({"type": "settings", "values": {"x": 1}})
    assert tx.sent == []
    assert "not allowed from a radio follower" in caplog.text
    f.forward_command(Command("pause"))
    assert tx.sent == [2]


def test_sound_dedup_and_replay_guard():
    clock = FakeClock()
    played: list[Whistle] = []
    leader = Leader(clock, CFG)
    f, _ = make(clock, on_sound=played.append)

    def timer(seq: int, count: int = 0, age: int = 0xFFFF) -> FeedTimer:
        t = leader.timer()
        t = replace(
            t, sound_seq=seq, sound_count=count, sound_blast=50, sound_gap=50, sound_age=age
        )
        return FeedTimer(t.to_bytes())

    f.on_feed(FeedSession(leader.session().to_bytes()))
    f.on_feed(timer(5, 2, 100))  # first TIMER ever: an old sound id, not played
    assert played == []
    f.on_feed(timer(6, 1, 100))  # new and young
    assert played == [Whistle(1, 500, 500)]
    f.on_feed(FeedSound(RadioSound(MASTER, 6, 1, 50, 50).to_bytes()))  # same id: duplicate
    f.on_feed(FeedSound(RadioSound(MASTER, 7, 3, 50, 50).to_bytes()))
    f.on_feed(timer(7, 3, 20))  # already played via SOUND
    assert [w.count for w in played] == [1, 3]
    f.on_feed(timer(8, 5, 900))  # too old
    assert [w.count for w in played] == [1, 3]


def test_one_late_frame_is_not_a_jump_but_a_persistent_later_deadline_is():
    clock = FakeClock()
    leader = Leader(clock, CFG)
    f, _ = make(clock)
    leader.feed(f)
    leader.engine.handle(Command("primary"))
    clock.advance(11 * NS_PER_S)
    leader.engine.poll()
    f.on_feed(FeedTimer(leader.timer().to_bytes()))
    base = latest(f).deadline_ns
    clock.advance(200 * NS_PER_MS)
    t = leader.timer()
    late = replace(t, remaining_ms=t.remaining_ms + 130)  # one frame that arrived 130 ms late
    f.on_feed(FeedTimer(late.to_bytes()))
    assert latest(f).deadline_ns == base
    clock.advance(200 * NS_PER_MS)
    f.on_feed(FeedTimer(leader.timer().to_bytes()))  # the next frame is on time again
    assert abs(latest(f).deadline_ns - base) <= 5 * NS_PER_MS
    # A real extension (the next frames all report a later end) is followed after the confirm time.
    for _ in range(4):
        clock.advance(200 * NS_PER_MS)
        t = leader.timer()
        f.on_feed(FeedTimer(replace(t, remaining_ms=t.remaining_ms + 5000).to_bytes()))
    assert latest(f).deadline_ns >= base + 4_900 * NS_PER_MS

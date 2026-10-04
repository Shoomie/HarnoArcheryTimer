from __future__ import annotations

from typing import List

import pytest

from archerytimer.common.clock import NS_PER_S, FakeClock
from archerytimer.core.engine import Engine, EngineError
from archerytimer.core.models import (
    Buzzer,
    Command,
    EngineSettings,
    Event,
    Light,
    LightChange,
    Mode,
    PhaseSpec,
    Sequence,
    SessionConfig,
    Snapshot,
    Whistle,
)

S = NS_PER_S
SEQ = Sequence(
    "t",
    {},
    (
        PhaseSpec("PREP", 10 * S, Light.RED, whistle_on_start=2),
        PhaseSpec("SHOOT", 120 * S, Light.GREEN, 1, warn_at_ns=30 * S),
        PhaseSpec("END", 0, Light.RED, 3),
    ),
)


def make(settings=None, **cfg):
    clock = FakeClock(0)
    events: List[Event] = []
    eng = Engine(clock, {"t": SEQ}, events.append, settings)
    eng.configure(SessionConfig("t", **cfg))
    return clock, eng, events


def run_until(clock, eng, t_ns):
    while True:
        due = eng.next_due_ns()
        if due is None or due > t_ns:
            break
        clock.set(due)
        eng.poll()
    clock.set(t_ns)
    eng.poll()


def play_rounds(clock, eng, n):
    for _ in range(n):
        eng.handle(Command("start"))
        clock.advance_s(1000)
        eng.poll()


def test_full_end_timeline():
    clock, eng, ev = make()
    eng.handle(Command("start"))
    s = eng.snapshot()
    assert s.phase_id == "PREP" and s.deadline_ns == 10 * S and s.light is Light.RED
    clock.set(500 * S)  # one very late wake still fires everything in order
    eng.poll()
    assert eng.snapshot().mode is Mode.FINISHED
    assert [e.light for e in ev if isinstance(e, LightChange)] == [
        Light.GREEN,
        Light.YELLOW,
        Light.RED,
    ]
    assert [e.count for e in ev if isinstance(e, Whistle)] == [2, 1, 3]


def test_late_wake_chains_deadlines():
    clock, eng, _ = make(total_ends=2)
    eng.handle(Command("start"))
    clock.set(10 * S + 7_000_000)  # 7 ms late
    eng.poll()
    s = eng.snapshot()
    assert s.phase_id == "SHOOT" and s.phase_start_ns == 10 * S and s.deadline_ns == 130 * S


def test_no_drift_over_many_late_boundaries():
    clock, eng, _ = make(total_ends=1)
    eng.handle(Command("start"))
    run_until(clock, eng, 10 * S + 3_000_000)
    assert eng.snapshot().deadline_ns == 130 * S


def test_warn_light_at_threshold():
    clock, eng, _ = make()
    eng.handle(Command("start"))
    run_until(clock, eng, 99 * S)
    assert eng.snapshot().light is Light.GREEN
    run_until(clock, eng, 100 * S)
    assert eng.snapshot().light is Light.YELLOW


def test_pause_resume_exact_remaining():
    clock, eng, _ = make()
    eng.handle(Command("start"))
    run_until(clock, eng, 40 * S)
    eng.handle(Command("pause"))
    s = eng.snapshot()
    assert s.paused and s.remaining_at_pause_ns == 90 * S and s.light is Light.RED
    clock.advance_s(1000)
    eng.poll()
    assert eng.snapshot().phase_id == "SHOOT"
    eng.handle(Command("resume"))
    s = eng.snapshot()
    assert not s.paused and s.deadline_ns == clock.now_ns() + 90 * S and s.light is Light.GREEN


def test_resume_inside_warn_window_is_yellow():
    clock, eng, _ = make()
    eng.handle(Command("start"))
    run_until(clock, eng, 105 * S)
    eng.handle(Command("pause"))
    eng.handle(Command("resume"))
    assert eng.snapshot().light is Light.YELLOW


def test_emergency_and_continue():
    clock, eng, ev = make(total_ends=2)
    eng.handle(Command("start"))
    run_until(clock, eng, 40 * S)
    ev.clear()
    eng.handle(Command("emergency"))
    s = eng.snapshot()
    assert s.emergency and s.light is Light.RED
    assert Whistle(5, 500, 500) in ev
    clock.advance_s(60)
    eng.poll()
    assert eng.snapshot().phase_id == "SHOOT"  # frozen
    eng.handle(Command("start"))  # locked out
    eng.handle(Command("clear_emergency", {"mode": "continue"}))
    s = eng.snapshot()
    assert not s.emergency and s.paused and s.remaining_at_pause_ns == 90 * S
    eng.handle(Command("resume"))
    assert eng.snapshot().light is Light.GREEN


def test_emergency_restart_returns_to_waiting_same_round():
    clock, eng, _ = make(total_ends=2)
    eng.handle(Command("start"))
    run_until(clock, eng, 40 * S)
    eng.handle(Command("emergency"))
    eng.handle(Command("clear_emergency", {"mode": "restart"}))
    s = eng.snapshot()
    assert s.mode is Mode.WAITING and s.round_index == 0 and s.light is Light.RED


def test_emergency_while_waiting_keeps_round():
    _, eng, _ = make(total_ends=2)
    eng.handle(Command("emergency"))
    eng.handle(Command("clear_emergency", {"mode": "continue"}))
    s = eng.snapshot()
    assert s.mode is Mode.WAITING and not s.emergency and not s.paused


def test_stop_end_goes_to_end_phase():
    clock, eng, ev = make(total_ends=2)
    eng.handle(Command("start"))
    run_until(clock, eng, 40 * S)
    ev.clear()
    eng.handle(Command("stop_end"))
    assert Whistle(3, 500, 500) in ev
    s = eng.snapshot()
    assert s.mode is Mode.WAITING and s.round_index == 1 and s.light is Light.RED
    assert eng.next_due_ns() is None


def test_line_rotation_and_alternating_order():
    clock, eng, _ = make(groups=("AB", "CD"), total_ends=2)
    seen = []
    for _ in range(4):
        seen.append((eng.snapshot().end_no, eng.snapshot().group))
        play_rounds(clock, eng, 1)
    assert seen == [(1, "AB"), (1, "CD"), (2, "CD"), (2, "AB")]
    assert eng.snapshot().mode is Mode.FINISHED


def test_no_alternation():
    clock, eng, _ = make(groups=("AB", "CD"), total_ends=2, alternate_order=False)
    order = []
    for _ in range(4):
        order.append(eng.snapshot().group)
        play_rounds(clock, eng, 1)
    assert order == ["AB", "CD", "AB", "CD"]


def test_practice_ends_counted_separately():
    clock, eng, _ = make(total_ends=2, practice_ends=1)
    s = eng.snapshot()
    assert s.practice and s.end_no == 1 and s.total_ends == 1 and s.total_rounds == 3
    play_rounds(clock, eng, 1)
    s = eng.snapshot()
    assert not s.practice and s.end_no == 1 and s.total_ends == 2


def test_auto_advance():
    clock, eng, _ = make(total_ends=2, auto_advance=True, auto_advance_delay_ns=5 * S)
    eng.handle(Command("start"))
    run_until(clock, eng, 134 * S)  # round ended at 130 s
    assert eng.snapshot().mode is Mode.WAITING
    run_until(clock, eng, 136 * S)
    s = eng.snapshot()
    assert s.mode is Mode.RUNNING and s.phase_start_ns == 135 * S


def test_skip_back_reset():
    _, eng, _ = make(total_ends=3)
    eng.handle(Command("next"))
    assert eng.snapshot().round_index == 1
    eng.handle(Command("back"))
    assert eng.snapshot().round_index == 0
    eng.handle(Command("start"))
    eng.handle(Command("next"))  # skip while running
    s = eng.snapshot()
    assert s.mode is Mode.WAITING and s.round_index == 1 and eng.next_due_ns() is None
    eng.handle(Command("reset"))
    s = eng.snapshot()
    assert s.round_index == 0 and s.mode is Mode.WAITING


def test_configure_rejected_while_running():
    _, eng, _ = make()
    eng.handle(Command("start"))
    with pytest.raises(EngineError):
        eng.configure(SessionConfig("t"))


def test_hardware_events_precede_snapshot():
    _, eng, ev = make()
    ev.clear()
    eng.handle(Command("start"))
    kinds = [type(e).__name__ for e in ev]
    assert kinds[-1] == "Snapshot" and kinds.count("Snapshot") == 1
    assert kinds.index("Whistle") < kinds.index("Snapshot")


def test_host_timed_whistle_uses_buzzer_events():
    clock, eng, ev = make(EngineSettings(whistle_timing="host", blast_ms=100, gap_ms=100))
    eng.handle(Command("start"))  # PREP: 2 blasts
    run_until(clock, eng, S)
    assert [e.on for e in ev if isinstance(e, Buzzer)] == [False, True, False, True, False]
    assert not any(isinstance(e, Whistle) for e in ev)


def test_shutdown_is_red_and_silent():
    _, eng, ev = make()
    eng.handle(Command("start"))
    ev.clear()
    eng.shutdown()
    assert LightChange(Light.RED) in ev and Whistle(0, 0, 0) in ev


def test_late_callback():
    clock = FakeClock(0)
    late = []
    eng = Engine(clock, {"t": SEQ}, lambda e: None, on_late=lambda k, ns: late.append((k, ns)))
    eng.configure(SessionConfig("t"))
    eng.handle(Command("start"))
    clock.set(10 * S + 5_000_000)
    eng.poll()
    assert late == [("phase_end", 5_000_000)]


def test_primary_starts_then_resumes_but_never_mid_round_or_in_emergency():
    clock, eng, _ = make(total_ends=2)
    eng.handle(Command("primary"))
    assert eng.snapshot().mode is Mode.RUNNING
    run_until(clock, eng, 40 * S)
    eng.handle(Command("primary"))  # mid-round: ignored
    assert not eng.snapshot().paused and eng.snapshot().phase_id == "SHOOT"
    eng.handle(Command("pause"))
    eng.handle(Command("primary"))
    assert not eng.snapshot().paused
    eng.handle(Command("emergency"))
    eng.handle(Command("primary"))  # locked out
    assert eng.snapshot().emergency


def test_back_is_published_to_the_screens():
    _, eng, events = make(total_ends=3)
    eng.handle(Command("next"))
    snaps = [e for e in events if isinstance(e, Snapshot)]
    before = len(snaps)
    eng.handle(Command("back"))
    snaps = [e for e in events if isinstance(e, Snapshot)]
    assert len(snaps) == before + 1 and snaps[-1].round_index == 0

from __future__ import annotations

import time

from archerytimer.common.clock import NS_PER_S, MonotonicClock
from archerytimer.core.engine import Engine
from archerytimer.core.engine_runner import EngineRunner
from archerytimer.core.models import Command, Light, Mode, PhaseSpec, Sequence, SessionConfig


def test_runner_real_thread():
    clock = MonotonicClock()
    seq = Sequence(
        "t",
        {},
        (PhaseSpec("A", NS_PER_S // 20, Light.GREEN), PhaseSpec("END", 0, Light.RED, 3)),
    )
    eng = Engine(clock, {"t": seq}, lambda e: None)
    eng.configure(SessionConfig("t"))
    r = EngineRunner(eng, clock)
    r.start()
    r.send(Command("start"))
    deadline = time.monotonic() + 2
    while eng.snapshot().mode is not Mode.FINISHED and time.monotonic() < deadline:
        time.sleep(0.01)
    r.stop()
    assert eng.snapshot().mode is Mode.FINISHED

"""Run a session headless and print events: ``python -m archerytimer.core.cli``.

Default is an instant simulation on a fake clock. ``--realtime`` runs on the real
clock through ``EngineRunner``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

from archerytimer.common.clock import NS_PER_S, Clock, FakeClock, MonotonicClock
from archerytimer.core.engine import Engine
from archerytimer.core.engine_runner import EngineRunner
from archerytimer.core.models import Command, Event, Mode, SessionConfig, Snapshot
from archerytimer.core.rules import load_sequences

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "config" / "sequences"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sequence", default="indoor_3arrows")
    ap.add_argument("--groups", default="AB,CD")
    ap.add_argument("--ends", type=int, default=2)
    ap.add_argument("--practice", type=int, default=0)
    ap.add_argument("--auto", action="store_true", help="auto-advance to the next group")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--config-dir", type=Path, default=DEFAULT_DIR)
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    fake = FakeClock(0)
    clock: Clock = MonotonicClock() if args.realtime else fake
    t0 = clock.now_ns()

    def show(ev: Event) -> None:
        stamp = f"{(clock.now_ns() - t0) / NS_PER_S:9.3f}s"
        if isinstance(ev, Snapshot):
            practice = " practice" if ev.practice else ""
            print(
                f"{stamp}  [{ev.mode.value}] {ev.phase_id} group={ev.group} "
                f"end={ev.end_no}/{ev.total_ends}{practice} light={ev.light.name}"
            )
        else:
            print(f"{stamp}  {ev}")

    engine = Engine(clock, load_sequences(args.config_dir), show)
    engine.configure(
        SessionConfig(
            sequence_id=args.sequence,
            groups=tuple(args.groups.split(",")),
            total_ends=args.ends,
            practice_ends=args.practice,
            auto_advance=args.auto,
        )
    )

    if args.realtime:
        runner = EngineRunner(engine, clock)
        runner.start()
        try:
            while engine.snapshot().mode is not Mode.FINISHED:
                if engine.snapshot().mode is Mode.WAITING:
                    runner.send(Command("start"))
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        runner.stop()
        return 0

    while engine.snapshot().mode is not Mode.FINISHED:
        due = engine.next_due_ns()
        if due is None:
            if engine.snapshot().mode is not Mode.WAITING:
                break
            engine.handle(Command("start"))
            continue
        fake.set(due)
        engine.poll()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

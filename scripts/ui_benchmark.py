"""UI frame cost on the real section code: ``python scripts/ui_benchmark.py [--size 1920x1080]``.

Runs the app's ``step()`` for a simulated 120 s end (one countdown update per second, the
wall clock ticking too) and reports mean/p99/max CPU time per presented frame. Uses the
configured SDL video driver, so on the Pi run it with ``SDL_VIDEODRIVER=kmsdrm``.
Presents are driven by a fake clock: this measures the cost of a frame, not wall time.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from archerytimer.common.clock import NS_PER_S, FakeClock
from archerytimer.common.i18n import Translator
from archerytimer.core.models import Light, Mode, Snapshot
from archerytimer.ipc.clocksync import OffsetEstimator
from archerytimer.ui_client.app import UiApp
from archerytimer.ui_client.renderer import DisplayConfig, open_renderer


class _Link:
    connected = ever_connected = upstream_ok = True
    lost_since_ns = None

    def __init__(self, snap: Snapshot) -> None:
        self.snapshot = snap
        self.estimator = OffsetEstimator()

    def send(self, msg: dict) -> bool:
        return True

    def sequence_names(self, _id: str) -> dict:
        return {"sv": "Inomhus 18 m", "en": "Indoor 18 m"}


def run(kind: str, size: tuple[int, int], fullscreen: bool, seconds: int) -> None:
    renderer = open_renderer(DisplayConfig(kind=kind, size=size, fullscreen=fullscreen))
    clock = FakeClock(1000 * NS_PER_S)
    now = clock.now_ns()
    snap = Snapshot(1, Mode.RUNNING, "t", "SHOOT", now, now + seconds * NS_PER_S, False, 0,
                    Light.GREEN, "AB", 3, 12, False, 0, 24, False, "up")  # fmt: skip
    app = UiApp(
        _Link(snap), renderer, Translator("sv"), clock=clock, wall=lambda: clock.now_ns() / 1e9
    )  # type: ignore[arg-type]
    app.build()
    app.step(force=True)
    times: list[int] = []
    cpu0 = time.process_time()
    for _ in range(seconds):
        clock.advance(NS_PER_S)
        t = time.perf_counter_ns()
        app.step()
        times.append(time.perf_counter_ns() - t)
    cpu = time.process_time() - cpu0
    times.sort()
    print(f"{renderer.name:8s} {renderer.logical_size[0]}x{renderer.logical_size[1]}: "
          f"mean {statistics.mean(times) / 1e6:6.2f} ms  p99 {times[int(len(times) * .99)] / 1e6:6.2f} ms  "
          f"max {times[-1] / 1e6:6.2f} ms  | {len(times)} frames, {cpu / seconds * 1000:.2f} ms CPU/s "
          f"({cpu / seconds * 100:.2f} % of one core at 1 frame/s)")  # fmt: skip
    renderer.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--seconds", type=int, default=100)
    a = ap.parse_args()
    w, _, h = a.size.partition("x")
    for kind in ("software", "gpu"):
        run(kind, (int(w), int(h)), a.fullscreen, a.seconds)

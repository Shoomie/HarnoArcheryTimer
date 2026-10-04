#!/usr/bin/env python3
"""M0 jitter benchmark: how late does a deadline-scheduled engine wake under UI load?

A dummy engine schedules an event every --period-ms (default 100 ms) by absolute
deadline, waiting on a threading.Event with a timeout (the design planned for
the real engine). For each event it records:
  lateness  actual wake time minus deadline
  handoff   time from enqueueing a "hardware event" to a worker thread blocked
            on SimpleQueue.get() receiving it (stand-in for the serial worker)

UI load profiles (rendering the benchmark screen, see _scene.py):
  none       no UI at all (baseline)
  idle       sectioned, 1 Hz updates
  animating  sectioned, one section at 60 fps
  overload   full redraw every frame, uncapped, plus ~8 ms/frame of pure-Python
             GIL-holding work with allocation churn

Topologies:
  threaded   engine is a thread inside the UI process (shares the GIL)
  process    engine runs in its own process (the planned architecture)

Wait strategies:
  event      plain Event.wait(timeout) until the deadline
  hybrid     Event.wait until --hybrid-margin-ms before the deadline, then
             0.5 ms high-resolution sleeps that still poll for commands
             (Windows' Event.wait is only as fine as the system timer tick)

Each case runs in a fresh subprocess. On Windows every case also runs with a
1 ms system timer resolution (timeBeginPeriod) requested by the engine.
Target: lateness p99 < 2 ms on the Pi 2B.

Examples:
  python scripts/jitter_benchmark.py                    # full matrix, 20 s per case
  python scripts/jitter_benchmark.py --duration 60 --hogs 4 --engine-cpu 3 --engine-nice -5
  python scripts/jitter_benchmark.py --topology process --load overload
  python scripts/jitter_benchmark.py --headless --duration 2   # CI smoke test
"""

from __future__ import annotations

import argparse
import gc
import json
import multiprocessing as mp
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any

import _benchutil as bu
from archerytimer.common.clock import Clock, MonotonicClock

LOADS = ("none", "idle", "animating", "overload")
TOPOLOGIES = ("threaded", "process")
TARGET_P99_MS = 2.0
WARMUP_S = 1.0
OVERLOAD_PYTHON_MS = 8.0


# --------------------------------------------------------------------------- engine side


def engine_run(cfg: dict[str, Any]) -> dict[str, Any]:
    """The dummy engine. Runs in a thread or as the body of a separate process."""
    tuning = bu.apply_linux_tuning(cfg.get("engine_nice"), cfg.get("engine_cpu"))
    if cfg["switchinterval"] > 0:
        sys.setswitchinterval(cfg["switchinterval"])

    with bu.windows_timer_resolution(cfg["timer_res"]) as timer_res_active:
        clock: Clock = MonotonicClock()
        wake = threading.Event()  # set by "commands" in the real engine; never set here
        hw_queue: queue.SimpleQueue[int | None] = queue.SimpleQueue()
        handoff: list[int] = []

        def worker() -> None:
            while True:
                item = hw_queue.get()
                if item is None:
                    return
                handoff.append(clock.now_ns() - item)

        worker_thread = threading.Thread(target=worker, name="fake-serial")
        worker_thread.start()

        period = int(cfg["period_ms"] * bu.NS_PER_MS)
        n_events = int(cfg["duration"] * 1000 / cfg["period_ms"])
        lateness: list[int] = []
        gc.collect()
        gc.freeze()

        hybrid = cfg["wait"] == "hybrid"
        margin = int(cfg["hybrid_margin_ms"] * bu.NS_PER_MS)
        fine_step_s = 0.0005
        t0 = clock.now_ns() + int(WARMUP_S * 1e9)
        for k in range(n_events):
            deadline = t0 + k * period
            while True:
                now = clock.now_ns()
                if now >= deadline:
                    break
                remaining = deadline - now
                if hybrid and remaining <= margin:
                    # Final stretch: short high-resolution sleeps, still polling for commands.
                    if wake.is_set():
                        break
                    time.sleep(min(fine_step_s, remaining / 1e9))
                else:
                    clock.wait(wake, remaining - margin if hybrid else remaining)
            lateness.append(now - deadline)
            hw_queue.put(clock.now_ns())

        hw_queue.put(None)
        worker_thread.join()

    return {
        "lateness": bu.summarize_ms(lateness),
        "handoff": bu.summarize_ms(handoff),
        "timer_res_active": timer_res_active,
        "tuning": tuning,
    }


def engine_process_main(cfg: dict[str, Any], out: Any) -> None:
    out.put(engine_run(cfg))


# --------------------------------------------------------------------------- UI side


def run_case(cfg: dict[str, Any]) -> dict[str, Any]:
    """Child-process body: run the UI load and the engine, return combined stats."""
    hogs = [mp.get_context("spawn").Process(target=_hog, daemon=True) for _ in range(cfg["hogs"])]
    for h in hogs:
        h.start()

    backend = None
    driver = None
    if cfg["load"] != "none":
        import pygame

        import _scene

        try:
            backend = _scene.open_backend(cfg["backend"], (1920, 1080), cfg["fullscreen"], False)
        except Exception:
            backend = _scene.open_backend("software", (1920, 1080), cfg["fullscreen"], False)
        driver = f"{pygame.display.get_driver()}/{backend.name}"

    cpu = bu.CpuMeter()
    result: dict[str, Any] = {}
    if cfg["topology"] == "threaded":
        box: dict[str, Any] = {}
        engine = threading.Thread(target=lambda: box.update(engine_run(cfg)), name="engine")
        engine.start()
        done = lambda: not engine.is_alive()  # noqa: E731
    else:
        ctx = mp.get_context("spawn")
        out = ctx.Queue()
        proc = ctx.Process(target=engine_process_main, args=(cfg, out))
        proc.start()
        done = lambda: not proc.is_alive() or not out.empty()  # noqa: E731

    if backend is None:
        while not done():
            time.sleep(0.05)
    else:
        import _scene

        mode = {"idle": "C", "animating": "B", "overload": "A"}[cfg["load"]]
        fps = 0.0 if cfg["load"] == "overload" else 60.0
        extra = OVERLOAD_PYTHON_MS if cfg["load"] == "overload" else 0.0
        frames = _scene.run_frames(backend, mode, fps, done, extra_python_ms=extra)
        result["ui_frames"] = len(frames["work"])
        backend.close()

    if cfg["topology"] == "threaded":
        engine.join()
        result.update(box)
    else:
        result.update(out.get(timeout=30))
        proc.join()

    result["ui_cpu_percent"] = cpu.percent()
    result["driver"] = driver
    for h in hogs:
        h.terminate()
    return result


def _hog() -> None:
    while True:
        pass


# --------------------------------------------------------------------------- orchestration


def run_child(cfg: dict[str, Any]) -> dict[str, Any]:
    cmd = [sys.executable, os.path.abspath(__file__), "--child", json.dumps(cfg)]
    env = dict(os.environ)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=cfg["duration"] + WARMUP_S + 90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("{"):
            parsed: dict[str, Any] = json.loads(line)
            return parsed
    return {"error": (proc.stderr.strip().splitlines() or [f"exit {proc.returncode}"])[-1]}


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--topology", choices=(*TOPOLOGIES, "all"), default="all")
    p.add_argument("--load", choices=(*LOADS, "all"), default="all")
    p.add_argument("--duration", type=float, default=20.0, help="seconds per case (default 20)")
    p.add_argument("--period-ms", type=float, default=100.0, help="event period (default 100)")
    p.add_argument(
        "--backend", choices=("gpu", "software"), default="gpu", help="UI render backend"
    )
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--headless", action="store_true", help="SDL dummy video driver (CI)")
    p.add_argument(
        "--switchinterval",
        type=float,
        default=0.0005,
        help="sys.setswitchinterval for the engine's process; 0 = leave default",
    )
    p.add_argument(
        "--timer-res",
        choices=("off", "on", "both"),
        default="both",
        help="Windows only: request 1 ms timer resolution (default both)",
    )
    p.add_argument(
        "--wait",
        choices=("event", "hybrid", "both"),
        default="both",
        help="engine wait strategy: plain Event.wait, or Event.wait until "
        "--hybrid-margin-ms before the deadline then 0.5 ms sleeps (default both)",
    )
    p.add_argument(
        "--hybrid-margin-ms", type=float, default=20.0 if sys.platform == "win32" else 2.0
    )
    p.add_argument(
        "--hogs", type=int, default=0, help="extra busy-loop processes to load all cores"
    )
    p.add_argument("--engine-nice", type=int, default=None, help="Linux: nice increment for engine")
    p.add_argument("--engine-cpu", type=int, default=None, help="Linux: pin engine to this CPU")
    p.add_argument("--json", metavar="PATH", help="also write results as JSON")
    p.add_argument("--child", metavar="CFG", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    if args.child:
        print(json.dumps(run_case(json.loads(args.child))), flush=True)
        return 0

    timer_variants = [False]
    if sys.platform == "win32":
        timer_variants = {"off": [False], "on": [True], "both": [False, True]}[args.timer_res]

    bu.print_header(
        "archerytimer jitter benchmark (M0)",
        {
            "period": f"{args.period_ms:g} ms",
            "duration/case": (
                f"{args.duration:g} s (~{int(args.duration * 1000 / args.period_ms)} events)"
            ),
            "switchinterval": args.switchinterval or "(default)",
            "wait strategy": f"{args.wait} (hybrid margin {args.hybrid_margin_ms:g} ms)",
            "UI backend": args.backend,
            "hog processes": args.hogs,
            "engine nice/cpu": f"{args.engine_nice} / {args.engine_cpu}",
        },
    )

    topologies = TOPOLOGIES if args.topology == "all" else (args.topology,)
    loads = LOADS if args.load == "all" else (args.load,)
    waits = ("event", "hybrid") if args.wait == "both" else (args.wait,)
    cases = []
    for wait in waits:
        for timer_res in timer_variants:
            for topology in topologies:
                for load in loads:
                    cfg = {
                        "topology": topology,
                        "load": load,
                        "timer_res": timer_res,
                        "wait": wait,
                        "hybrid_margin_ms": args.hybrid_margin_ms,
                        "duration": args.duration,
                        "period_ms": args.period_ms,
                        "backend": args.backend,
                        "fullscreen": args.fullscreen,
                        "switchinterval": args.switchinterval,
                        "hogs": args.hogs,
                        "engine_nice": args.engine_nice,
                        "engine_cpu": args.engine_cpu,
                    }
                    label = f"{wait:<6} {topology:<8} {load:<9}" + (
                        " timer=1ms" if timer_res else ""
                    )
                    print(f"  running {label} ...", flush=True)
                    cases.append((cfg, run_child(cfg)))

    print()
    rows = []
    for cfg, r in cases:
        timer = "1ms" if cfg["timer_res"] else "default"
        head = [cfg["wait"], cfg["topology"], cfg["load"]]
        if sys.platform == "win32":
            head.append(timer)
        if "error" in r:
            rows.append([*head, "-", "-", "-", "-", "-", "FAILED"])
            continue
        lat, hand = r["lateness"], r["handoff"]
        ok = lat["p99_ms"] < TARGET_P99_MS
        rows.append(
            [
                *head,
                lat["p50_ms"],
                lat["p99_ms"],
                lat["max_ms"],
                hand["p99_ms"],
                f"{r['ui_cpu_percent']:.0f}%",
                "PASS" if ok else "FAIL",
            ]
        )
    headers = ["wait", "topology", "load"]
    if sys.platform == "win32":
        headers.append("timer")
    bu.print_table(
        [
            *headers,
            "late p50",
            "late p99",
            "late max",
            "handoff p99",
            "CPU",
            f"p99<{TARGET_P99_MS:g}ms",
        ],
        rows,
    )
    print("  times in ms. late = engine wake lateness vs deadline;")
    print("  handoff = engine enqueue -> worker thread dequeue (serial worker stand-in);")
    print("  CPU = UI-side process CPU as % of one core.")
    for cfg, r in cases:
        if "error" in r:
            print(f"  {cfg['topology']} {cfg['load']} error: {r['error']}")
        elif r.get("tuning"):
            print(f"  {cfg['topology']} {cfg['load']} engine tuning: {r['tuning']}")
    drivers = {r.get("driver") for _, r in cases if r.get("driver")}
    if drivers:
        print(f"  UI driver/backend: {', '.join(sorted(drivers))}")
    bu.write_json(
        args.json,
        {
            "system": bu.system_info(),
            "args": vars(args),
            "results": [{"case": cfg, **r} for cfg, r in cases],
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""M0 render benchmark: frame time and CPU cost of the candidate render strategies.

Runs every (backend, mode) combination in its own subprocess, so a crashing
backend (e.g. GPU path on a Pi) cannot take the rest down, then prints a summary.

  Modes:    A = full redraw every frame, B = sectioned + cached with one section
            animating, C = sectioned idle with 1 Hz updates.
  Backends: gpu (SDL renderer + textures), software (display surface + flip).

Examples:
  python scripts/render_benchmark.py                        # windowed 1920x1080, 10 s each
  python scripts/render_benchmark.py --fullscreen           # Pi OS Lite (KMSDRM)
  python scripts/render_benchmark.py --backend gpu --mode B --duration 30
  python scripts/render_benchmark.py --json bench-results/render-pi2b.json

Press Esc in the benchmark window to abort the current run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any

import _benchutil as bu

MODES = ("A", "B", "C")
BACKENDS = ("gpu", "software")
MODE_DESC = {
    "A": "full redraw/frame",
    "B": "sectioned, 1 animating",
    "C": "sectioned idle, 1 Hz",
}


def parse_size(text: str) -> tuple[int, int]:
    w, h = text.lower().split("x")
    return int(w), int(h)


def child(args: argparse.Namespace) -> dict[str, Any]:
    import pygame

    import _scene

    size = parse_size(args.resolution)
    backend = _scene.open_backend(args.backend, size, args.fullscreen, args.vsync)
    driver = pygame.display.get_driver()
    cpu = bu.CpuMeter()
    end = time.perf_counter() + args.duration
    raw = _scene.run_frames(backend, args.mode, args.fps, lambda: time.perf_counter() >= end)
    cpu_pct = cpu.percent()
    canvas = backend.size
    backend.close()

    frames = len(raw["work"])
    elapsed = args.duration
    total = [w + p for w, p in zip(raw["work"], raw["present"])]
    return {
        "backend": args.backend,
        "mode": args.mode,
        "video_driver": driver,
        "render_driver_hint": os.environ.get("SDL_RENDER_DRIVER", "(SDL default)"),
        "canvas": f"{canvas[0]}x{canvas[1]}",
        "fps_cap": args.fps,
        "vsync": args.vsync,
        "frames": frames,
        "fps": frames / elapsed if elapsed else 0.0,
        "cpu_percent": cpu_pct,
        "work": bu.summarize_ms(raw["work"]),
        "present": bu.summarize_ms(raw["present"]),
        "frame_total": bu.summarize_ms(total),
        "interval": bu.summarize_ms(raw["interval"]),
        "aborted": raw["aborted"],
    }


def run_child(args: argparse.Namespace, backend: str, mode: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        os.path.abspath(__file__),
        "--child",
        "--backend",
        backend,
        "--mode",
        mode,
        "--duration",
        str(args.duration),
        "--resolution",
        args.resolution,
        "--fps",
        str(args.fps),
    ]
    if args.fullscreen:
        cmd.append("--fullscreen")
    if args.vsync:
        cmd.append("--vsync")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=args.duration + 60, check=False
        )
    except subprocess.TimeoutExpired:
        return {"backend": backend, "mode": mode, "error": "timed out"}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("{"):
            result: dict[str, Any] = json.loads(line)
            return result
    err = (proc.stderr.strip().splitlines() or [f"exit code {proc.returncode}"])[-1]
    return {"backend": backend, "mode": mode, "error": err}


def verdict(r: dict[str, Any]) -> str:
    if "error" in r:
        return "FAILED"
    if r["mode"] == "C":
        return "idle (see CPU)"
    target = r["fps_cap"] if r["fps_cap"] > 0 else 60
    budget_ms = 1000 / target
    ok = r["fps"] >= 0.95 * target and r["frame_total"]["p99_ms"] < budget_ms
    return f"OK @{target:g}" if ok else f"MISSES {target:g} fps"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--backend", choices=(*BACKENDS, "all"), default="all")
    p.add_argument("--mode", choices=(*MODES, "all"), default="all")
    p.add_argument("--duration", type=float, default=10.0, help="seconds per run (default 10)")
    p.add_argument(
        "--resolution", default="1920x1080", help="logical canvas WxH (default 1920x1080)"
    )
    p.add_argument("--fps", type=float, default=60.0, help="frame cap for modes A/B; 0 = uncapped")
    p.add_argument("--fullscreen", action="store_true", help="fullscreen on the native display")
    p.add_argument("--vsync", action="store_true", help="request vsync (gpu backend)")
    p.add_argument("--headless", action="store_true", help="use SDL dummy video driver (CI)")
    p.add_argument("--json", metavar="PATH", help="also write results as JSON")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    if args.child:
        print(json.dumps(child(args)), flush=True)
        return 0

    bu.print_header(
        "archerytimer render benchmark (M0)",
        {
            "SDL_VIDEODRIVER": os.environ.get("SDL_VIDEODRIVER", "(default)"),
            "SDL_RENDER_DRIVER": os.environ.get("SDL_RENDER_DRIVER", "(default)"),
            "resolution": args.resolution + (" fullscreen" if args.fullscreen else " windowed"),
            "fps cap": args.fps or "uncapped",
            "vsync": args.vsync,
            "duration/run": f"{args.duration:g} s",
        },
    )

    backends = BACKENDS if args.backend == "all" else (args.backend,)
    modes = MODES if args.mode == "all" else (args.mode,)
    results = []
    for backend in backends:
        for mode in modes:
            print(f"  running {backend:<8} mode {mode} ({MODE_DESC[mode]}) ...", flush=True)
            results.append(run_child(args, backend, mode))

    print()
    rows = []
    for r in results:
        if "error" in r:
            rows.append([r["backend"], r["mode"], "-", "-", "-", "-", "-", "-", "-", verdict(r)])
            continue
        rows.append(
            [
                r["backend"],
                r["mode"],
                f"{r['fps']:.1f}",
                r["work"]["p50_ms"],
                r["work"]["p99_ms"],
                r["present"]["p50_ms"],
                r["present"]["p99_ms"],
                r["frame_total"]["max_ms"],
                f"{r['cpu_percent']:.0f}%",
                verdict(r),
            ]
        )
    print_rows_header = [
        "backend",
        "mode",
        "fps",
        "work p50",
        "work p99",
        "pres p50",
        "pres p99",
        "frame max",
        "CPU",
        "verdict",
    ]
    bu.print_table(print_rows_header, rows)
    print("  times in ms; work = CPU drawing + texture upload, pres = present/flip;")
    print("  CPU = process CPU as % of one core (4 cores on a Pi 2B = 400% max).")
    for r in results:
        if "error" in r:
            print(f"  {r['backend']} {r['mode']} error: {r['error']}")
        elif r.get("aborted"):
            print(f"  {r['backend']} {r['mode']}: aborted by user (Esc)")
    drivers = {r.get("video_driver") for r in results if "video_driver" in r}
    print(f"  SDL video driver used: {', '.join(sorted(d for d in drivers if d)) or '?'}")
    bu.write_json(args.json, {"system": bu.system_info(), "args": vars(args), "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())

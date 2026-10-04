#!/usr/bin/env python3
"""Environment probe: can this machine run the archery timer, and how?

Reports Python/OS/board, which pygame flavor and SDL version are installed,
which SDL video, render and audio drivers actually work (each tried in an
isolated subprocess, so a hanging KMSDRM init can't block the probe), timer
granularity, and serial support. Answers the M0 open question
"pygame-ce pip wheel with KMSDRM, or apt python3-pygame?" when run on the Pi.

  python scripts/env_probe.py
  python scripts/env_probe.py --json bench-results/env-pi2b.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any

import _benchutil as bu

VIDEO_DRIVERS = ["kmsdrm", "x11", "wayland", "windows", "cocoa", "offscreen", "dummy"]
AUDIO_DRIVERS = ["alsa", "pulseaudio", "pipewire", "wasapi", "directsound", "coreaudio", "dummy"]

_VIDEO_CHILD = r"""
import json, os, sys
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
out = {}
try:
    import pygame
    pygame.display.init()
    out["driver"] = pygame.display.get_driver()
    try:
        out["desktop_sizes"] = [list(s) for s in pygame.display.get_desktop_sizes()]
    except Exception:
        pass
    from pygame._sdl2 import video
    win = video.Window("probe", size=(64, 64))
    ren = video.Renderer(win)
    tex = video.Texture(ren, (16, 16), streaming=True)
    ren.clear(); tex.draw(); ren.present()
    out["gpu_renderer"] = "ok"
    win.destroy()
    pygame.display.quit()
except Exception as exc:
    out["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(out))
"""

_AUDIO_CHILD = r"""
import json, os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
out = {}
try:
    import pygame
    pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=512)
    out["init"] = list(pygame.mixer.get_init())
    pygame.mixer.quit()
except Exception as exc:
    out["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(out))
"""


def try_child(code: str, env_var: str, value: str, timeout: float = 10.0) -> dict[str, Any]:
    env = dict(os.environ)
    env[env_var] = value
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("{"):
            parsed: dict[str, Any] = json.loads(line)
            return parsed
    return {"error": (proc.stderr.strip().splitlines() or [f"exit {proc.returncode}"])[-1]}


def pygame_info() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        import pygame

        info["module_path"] = os.path.dirname(pygame.__file__)
        info["flavor"] = "pygame-ce" if getattr(pygame, "IS_CE", False) else "pygame"
        info["version"] = pygame.version.ver
        info["sdl_linked"] = ".".join(map(str, pygame.get_sdl_version()))
        info["sdl_compiled"] = ".".join(map(str, pygame.get_sdl_version(linked=False)))
        try:
            from pygame._sdl2 import video

            info["render_drivers"] = [d.name for d in video.get_drivers()]
        except Exception as exc:
            info["render_drivers"] = f"unavailable ({exc})"
    except Exception as exc:
        info["error"] = f"pygame not importable: {exc}"
    return info


def timer_granularity() -> dict[str, float]:
    """Median actual duration of 1 ms waits (shows the OS timer tick)."""

    def measure(fn: Any, n: int = 30) -> float:
        samples = []
        for _ in range(n):
            t0 = time.perf_counter_ns()
            fn()
            samples.append(time.perf_counter_ns() - t0)
        samples.sort()
        return samples[n // 2] / bu.NS_PER_MS

    ev = threading.Event()
    result = {
        "event_wait_1ms": measure(lambda: ev.wait(0.001)),
        "sleep_1ms": measure(lambda: time.sleep(0.001)),
    }
    with bu.windows_timer_resolution(True) as active:
        if active:
            result["event_wait_1ms_timer1ms"] = measure(lambda: ev.wait(0.001))
            result["sleep_1ms_timer1ms"] = measure(lambda: time.sleep(0.001))
    return result


def serial_info() -> dict[str, Any]:
    try:
        import serial
        from serial.tools import list_ports

        ports = [
            {
                "device": p.device,
                "description": p.description,
                "vid_pid": f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else None,
            }
            for p in list_ports.comports()
        ]
        return {"pyserial": serial.__version__, "ports": ports}
    except Exception as exc:
        return {"error": f"pyserial not importable: {exc}"}


def linux_groups() -> list[str] | None:
    if not hasattr(os, "getgroups"):
        return None
    try:
        import grp

        return sorted(grp.getgrgid(g).gr_name for g in os.getgroups())
    except Exception:
        return None


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--json", metavar="PATH", help="also write results as JSON")
    args = p.parse_args()

    bu.print_header("archerytimer environment probe")
    report: dict[str, Any] = {"system": bu.system_info()}

    pg = pygame_info()
    report["pygame"] = pg
    print("pygame")
    for k, v in pg.items():
        print(f"  {k:<16} {v}")
    print()

    print("SDL video drivers (display init + GPU renderer + streaming texture)")
    video: dict[str, Any] = {}
    for drv in VIDEO_DRIVERS:
        r = try_child(_VIDEO_CHILD, "SDL_VIDEODRIVER", drv)
        video[drv] = r
        if "error" in r:
            status = f"no   ({r['error'][:60]})"
        else:
            status = f"yes  gpu_renderer={r.get('gpu_renderer', 'FAILED')}"
            if r.get("desktop_sizes"):
                status += f"  desktop={r['desktop_sizes']}"
        print(f"  {drv:<10} {status}")
    report["video"] = video
    print()

    print("SDL audio drivers (mixer init 48 kHz, 512-sample buffer)")
    audio: dict[str, Any] = {}
    for drv in AUDIO_DRIVERS:
        r = try_child(_AUDIO_CHILD, "SDL_AUDIODRIVER", drv)
        audio[drv] = r
        status = f"no   ({r['error'][:60]})" if "error" in r else f"yes  {r['init']}"
        print(f"  {drv:<12} {status}")
    report["audio"] = audio
    print()

    tg = timer_granularity()
    report["timer"] = tg
    print("Timer granularity (median actual duration of a 1 ms wait)")
    for k, v in tg.items():
        print(f"  {k:<26} {v:.3f} ms")
    print()

    si = serial_info()
    report["serial"] = si
    print("Serial")
    if "error" in si:
        print(f"  {si['error']}")
    else:
        print(f"  pyserial {si['pyserial']}, {len(si['ports'])} port(s)")
        for port in si["ports"]:
            print(f"    {port['device']:<14} {port['vid_pid'] or '-':<10} {port['description']}")
    print()

    groups = linux_groups()
    if groups is not None:
        needed = {"video", "input", "audio", "dialout"}
        missing = sorted(needed - set(groups))
        report["groups"] = groups
        print(f"User groups: {', '.join(groups)}")
        print(f"  missing for kiosk use: {', '.join(missing) or 'none'}")
        print()

    print("Summary")
    kms = video.get("kmsdrm", {})
    if "error" not in kms:
        print(f"  KMSDRM works with this pygame ({pg.get('flavor')} {pg.get('version')}).")
    elif sys.platform.startswith("linux"):
        print("  KMSDRM NOT available with this pygame build. On Pi OS Lite, try apt's")
        print("  python3-pygame in a venv created with --system-site-packages.")
    working = [d for d, r in video.items() if "error" not in r and d not in ("dummy", "offscreen")]
    print(f"  usable display drivers: {', '.join(working) or 'none'}")
    gpu_ok = [
        d
        for d, r in video.items()
        if r.get("gpu_renderer") == "ok" and d not in ("dummy", "offscreen")
    ]
    print(f"  GPU renderer path works on: {', '.join(gpu_ok) or 'none'}")

    bu.write_json(args.json, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared helpers for the benchmark and probe scripts (stats, system info, reporting).

Scripts are run directly (``python scripts/xxx.py``), so this module also makes
``src/`` importable when the package has not been pip-installed (e.g. on a Pi).
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import platform
import sys
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

NS_PER_MS = 1_000_000


# --------------------------------------------------------------------------- stats


def percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile of an already sorted sequence (0 if empty)."""
    if not sorted_values:
        return 0.0
    rank = math.ceil(pct / 100 * len(sorted_values))
    return float(sorted_values[max(0, min(len(sorted_values), rank) - 1)])


def summarize_ms(values_ns: Sequence[int]) -> dict[str, float]:
    """p50/p99/max/mean in milliseconds for a list of nanosecond samples."""
    s = sorted(values_ns)
    n = len(s)
    return {
        "n": n,
        "p50_ms": percentile(s, 50) / NS_PER_MS,
        "p99_ms": percentile(s, 99) / NS_PER_MS,
        "max_ms": (s[-1] / NS_PER_MS) if n else 0.0,
        "mean_ms": (sum(s) / n / NS_PER_MS) if n else 0.0,
    }


class CpuMeter:
    """Process CPU usage over an interval, as % of one core (can exceed 100)."""

    def __init__(self) -> None:
        self._wall0 = time.perf_counter()
        self._cpu0 = time.process_time()

    def percent(self) -> float:
        wall = time.perf_counter() - self._wall0
        cpu = time.process_time() - self._cpu0
        return 100.0 * cpu / wall if wall > 0 else 0.0


# --------------------------------------------------------------------------- system info


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return None


def os_release() -> str:
    text = _read_text("/etc/os-release")
    if text:
        for line in text.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    return f"{platform.system()} {platform.release()} ({platform.version()})"


def board_model() -> str | None:
    return _read_text("/proc/device-tree/model")


def system_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": os_release(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "board": board_model(),
    }
    try:
        import pygame

        info["pygame"] = pygame.version.ver
        info["pygame_ce"] = bool(getattr(pygame, "IS_CE", False))
        info["sdl"] = ".".join(str(x) for x in pygame.get_sdl_version())
    except Exception as exc:  # pragma: no cover - depends on platform
        info["pygame"] = f"unavailable ({exc})"
    return info


def print_header(title: str, extra: dict[str, Any] | None = None) -> None:
    info = system_info()
    if extra:
        info.update(extra)
    print("=" * 78)
    print(title)
    print("=" * 78)
    for key, value in info.items():
        if value is not None:
            print(f"  {key:<16} {value}")
    print()


def print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    cells = [[fmt(v) for v in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for r in cells:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    print()


def write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Results written to {out}")


# --------------------------------------------------------------------------- OS timing knobs


@contextlib.contextmanager
def windows_timer_resolution(enabled: bool, period_ms: int = 1) -> Iterator[bool]:
    """Request a finer Windows system timer (timeBeginPeriod). No-op elsewhere.

    Yields True if the request was actually made.
    """
    if not enabled or sys.platform != "win32":
        yield False
        return
    import ctypes

    winmm = ctypes.WinDLL("winmm")
    ok = winmm.timeBeginPeriod(period_ms) == 0
    try:
        yield ok
    finally:
        if ok:
            winmm.timeEndPeriod(period_ms)


def apply_linux_tuning(nice: int | None, cpu: int | None) -> dict[str, str]:
    """Best-effort niceness and CPU pinning for the current process."""
    result: dict[str, str] = {}
    if nice is not None and hasattr(os, "nice"):
        try:
            os.nice(nice)
            result["nice"] = str(nice)
        except OSError as exc:
            result["nice"] = f"failed ({exc.strerror})"
    if cpu is not None and hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, {cpu})
            result["affinity"] = str(cpu)
        except OSError as exc:
            result["affinity"] = f"failed ({exc.strerror})"
    return result

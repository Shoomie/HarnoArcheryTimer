"""Smoke tests: each benchmark script runs headless for ~1 s and prints a summary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=SCRIPTS.parent,
    )


def test_env_probe() -> None:
    r = _run(str(SCRIPTS / "env_probe.py"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


@pytest.mark.parametrize("backend", ["software", "gpu"])
def test_render_benchmark(backend: str) -> None:
    r = _run(
        str(SCRIPTS / "render_benchmark.py"),
        "--headless",
        "--duration",
        "1",
        "--backend",
        backend,
        "--mode",
        "B",
    )
    assert r.returncode == 0, r.stderr
    assert "fps" in r.stdout.lower()


def test_jitter_benchmark() -> None:
    r = _run(
        str(SCRIPTS / "jitter_benchmark.py"),
        "--headless",
        "--duration",
        "1",
        "--topology",
        "threaded",
        "--load",
        "idle",
        "--timer-res",
        "off",
        "--wait",
        "event",
    )
    assert r.returncode == 0, r.stderr
    assert "p99" in r.stdout.lower()

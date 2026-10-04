"""Running external programs. Everything goes through a Runner so tests can inject a fake."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Mapping, Optional, Protocol, Sequence


class Runner(Protocol):
    def run(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        """Run with output shown on the terminal; return the exit code."""
        ...

    def capture(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> tuple[int, str]:
        """Run quietly; return (exit code, stdout+stderr)."""
        ...


class SubprocessRunner:
    def run(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        try:
            return subprocess.call(list(cmd), cwd=cwd, env=dict(env) if env else None)
        except (OSError, KeyboardInterrupt):
            return 1

    def capture(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> tuple[int, str]:
        try:
            p = subprocess.run(
                list(cmd),
                cwd=cwd,
                env=dict(env) if env else None,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

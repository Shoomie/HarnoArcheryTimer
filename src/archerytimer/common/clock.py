"""Injectable monotonic time source.

All timing in the system goes through a ``Clock``. Production code uses
``MonotonicClock`` (``time.monotonic_ns``, which is system-wide, so core and UI
processes share one timeline). Tests use ``FakeClock``, which only moves when
told to, so no test ever sleeps.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

NS_PER_MS = 1_000_000
NS_PER_S = 1_000_000_000


class Clock(Protocol):
    def now_ns(self) -> int:
        """Current monotonic time in nanoseconds."""
        ...

    def wait(self, event: threading.Event, timeout_ns: int) -> bool:
        """Block until ``event`` is set or ``timeout_ns`` elapses.

        Returns True if the event was set. A non-positive timeout returns
        immediately with the event's current state.
        """
        ...


class MonotonicClock:
    """Real clock backed by ``time.monotonic_ns``."""

    def now_ns(self) -> int:
        return time.monotonic_ns()

    def wait(self, event: threading.Event, timeout_ns: int) -> bool:
        if timeout_ns <= 0:
            return event.is_set()
        return event.wait(timeout_ns / NS_PER_S)


class FakeClock:
    """Manually advanced clock for tests.

    ``wait`` never blocks: if the event is not set, it advances time by the
    full timeout, as if the caller had slept until its deadline.
    """

    def __init__(self, start_ns: int = 0) -> None:
        self._now_ns = start_ns

    def now_ns(self) -> int:
        return self._now_ns

    def advance(self, delta_ns: int) -> None:
        if delta_ns < 0:
            raise ValueError("FakeClock cannot go backwards")
        self._now_ns += delta_ns

    def advance_s(self, seconds: float) -> None:
        self.advance(round(seconds * NS_PER_S))

    def set(self, now_ns: int) -> None:
        if now_ns < self._now_ns:
            raise ValueError("FakeClock cannot go backwards")
        self._now_ns = now_ns

    def wait(self, event: threading.Event, timeout_ns: int) -> bool:
        if event.is_set():
            return True
        if timeout_ns > 0:
            self._now_ns += timeout_ns
        return False

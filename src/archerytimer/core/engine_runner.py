"""Thread wrapper around ``Engine``: sleeps until the next deadline or a command."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from archerytimer.common.clock import NS_PER_MS, Clock
from archerytimer.core.engine import Engine
from archerytimer.core.models import Command

MAX_SLEEP_NS = 50 * NS_PER_MS


log = logging.getLogger("archerytimer.engine")


class EngineRunner:
    def __init__(self, engine: Engine, clock: Clock) -> None:
        self._engine = engine
        self._clock = clock
        self._commands: queue.SimpleQueue[Command] = queue.SimpleQueue()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def send(self, cmd: Command) -> None:
        """Thread-safe; wakes the engine immediately."""
        self._commands.put(cmd)
        self._wake.set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="engine", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        """Stop the thread, then force RED and silence."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
        self._engine.shutdown()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            while True:
                try:
                    cmd = self._commands.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._engine.handle(cmd)
                except Exception:  # a bad command must never kill the timer
                    log.exception("command %r failed", cmd.name)
            self._engine.poll()
            due = self._engine.next_due_ns()
            timeout = MAX_SLEEP_NS
            if due is not None:
                timeout = min(timeout, due - self._clock.now_ns())
            self._clock.wait(self._wake, timeout)

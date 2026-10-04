"""Audio worker: local sound (speakers on the Pi or PC) driven by the engine's events.

Runs in the core process, never in the UI, so a UI crash can never silence a stop signal.
It has its own thread and queue: ``submit`` is a queue put and never blocks the engine.

Timing: a ``Whistle(n, blast_ms, gap_ms)`` event is expanded into blast start times measured
from the moment the engine emitted it (``enq + i * (blast + gap)``), so blasts never drift
or accumulate error, whatever the thread's wake-up latency. ``Whistle(0)`` and
``Buzzer(False)`` silence immediately. A ``Buzzer(True)`` starts a steady tone (host-timed
mode, where the engine itself schedules each blast as on/off events).

Pi onboard audio adds roughly 20-50 ms of device latency; MCU sound is the precise output.
The backend sits behind a small interface so tests (and machines without audio) use fakes.
"""

from __future__ import annotations

import contextlib
import heapq
import logging
import queue
import threading
from typing import Any, Callable, Optional, Protocol

from archerytimer.audio import synth
from archerytimer.common.clock import NS_PER_S, Clock, MonotonicClock
from archerytimer.core import models as m

log = logging.getLogger("archerytimer.audio")
_NS_PER_MS = 1_000_000
_STOP = object()


class AudioBackend(Protocol):
    name: str

    def play(self, duration_ms: int) -> None:
        """Start one blast of ``duration_ms`` now (non-blocking)."""
        ...

    def start_tone(self) -> None: ...

    def stop(self) -> None:
        """Silence everything now."""
        ...

    def set_volume(self, volume: float) -> None: ...

    def close(self) -> None: ...


class NullBackend:
    """No audio hardware: every call is a no-op."""

    name = "none"

    def play(self, duration_ms: int) -> None:
        pass

    def start_tone(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def set_volume(self, volume: float) -> None:
        pass

    def close(self) -> None:
        pass


class PygameBackend:
    """pygame.mixer with a small buffer. Samples are pre-decoded and cached per length."""

    name = "pygame"

    def __init__(self, device: str = "", buffer: int = 512) -> None:
        import pygame

        self._pg = pygame
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        kwargs: dict[str, Any] = dict(frequency=synth.RATE, size=-16, channels=1, buffer=buffer)
        try:
            if device:
                pygame.mixer.init(devicename=device, **kwargs)
            else:
                pygame.mixer.init(**kwargs)
        except (pygame.error, TypeError) as exc:
            if not device:
                raise
            log.warning("audio device %r unavailable (%s); using the default", device, exc)
            pygame.mixer.init(**kwargs)
        self._blasts: dict[int, object] = {}
        self._tone = pygame.mixer.Sound(buffer=synth.sustained())
        self._channel = pygame.mixer.Channel(0)
        self._volume = 1.0
        self.warm(500)

    def warm(self, duration_ms: int) -> None:
        """Pre-decode a blast length so the first play has no synthesis delay."""
        if duration_ms not in self._blasts:
            sound = self._pg.mixer.Sound(buffer=synth.blast(duration_ms))
            sound.set_volume(self._volume)
            self._blasts[duration_ms] = sound

    def play(self, duration_ms: int) -> None:
        self.warm(duration_ms)
        self._channel.play(self._blasts[duration_ms])  # type: ignore[arg-type]

    def start_tone(self) -> None:
        self._channel.play(self._tone, loops=-1)

    def stop(self) -> None:
        self._channel.stop()

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        self._tone.set_volume(self._volume)
        for sound in self._blasts.values():
            sound.set_volume(self._volume)  # type: ignore[attr-defined]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pg.mixer.quit()


def list_devices() -> list[str]:
    """Names of the audio output devices SDL can see (empty when unknown)."""
    try:
        import pygame
        from pygame._sdl2 import audio as sdl_audio

        if not pygame.mixer.get_init():
            pygame.mixer.init()
            names = list(sdl_audio.get_audio_device_names(False))
            pygame.mixer.quit()
            return names
        return list(sdl_audio.get_audio_device_names(False))
    except Exception:
        return []


class AudioWorker:
    def __init__(self, backend: AudioBackend, clock: Optional[Clock] = None) -> None:
        self._backend = backend
        self._clock: Clock = clock or MonotonicClock()
        self._queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._thread: Optional[threading.Thread] = None
        self._enabled = True
        # (start_ns, serial, blast_ms) heap, writer thread only
        self._due: list[tuple[int, int, int]] = []
        self._serial = 0

    # ---------------------------------------------------------------- public

    @property
    def backend(self) -> AudioBackend:
        return self._backend

    def submit(self, event: m.Event) -> None:
        """Thread-safe, never blocks. Only whistle and buzzer events matter."""
        if isinstance(event, (m.Whistle, m.Buzzer)):
            self._queue.put((self._clock.now_ns(), event))

    def set_enabled(self, enabled: bool) -> None:
        self._queue.put((self._clock.now_ns(), _Config(enabled=enabled)))

    def set_volume(self, volume: float) -> None:
        self._queue.put((self._clock.now_ns(), _Config(volume=volume)))

    def set_device(self, factory: Callable[[str], AudioBackend], device: str) -> None:
        """Switch output device. The new backend is built on the worker thread, in order with
        the other requests, so nothing plays on a half-closed device."""
        self._queue.put((self._clock.now_ns(), _Swap(factory, device)))

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="audio", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        """Silence, stop the thread, release the device."""
        self._queue.put(_STOP)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        with contextlib.suppress(Exception):
            self._backend.stop()
        self._backend.close()

    # ---------------------------------------------------------------- thread

    def _run(self) -> None:
        while True:
            timeout: Optional[float] = None
            if self._due:
                timeout = max(0.0, (self._due[0][0] - self._clock.now_ns()) / NS_PER_S)
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                item = None
            if item is _STOP:
                return
            if item is not None:
                try:
                    self._apply(*item)  # type: ignore[misc]
                except Exception:
                    log.exception("audio event failed")
            self._fire_due()

    def _apply(self, enq_ns: int, event: object) -> None:
        if isinstance(event, _Swap):
            self._silence()
            self._backend.close()
            self._backend = event.factory(event.device)
            return
        if isinstance(event, _Config):
            if event.volume is not None:
                self._backend.set_volume(event.volume)
            if event.enabled is not None:
                self._enabled = event.enabled
                if not event.enabled:
                    self._silence()
            return
        if isinstance(event, m.Whistle):
            self._due.clear()
            self._backend.stop()  # a new command replaces whatever was playing
            if not self._enabled or event.count <= 0:
                return
            for i in range(event.count):
                self._serial += 1
                start = enq_ns + i * (event.blast_ms + event.gap_ms) * _NS_PER_MS
                heapq.heappush(self._due, (start, self._serial, event.blast_ms))
        elif isinstance(event, m.Buzzer):
            self._due.clear()
            if event.on and self._enabled:
                self._backend.start_tone()
            else:
                self._backend.stop()

    def _fire_due(self) -> None:
        now = self._clock.now_ns()
        while self._due and self._due[0][0] <= now:
            _, _, blast_ms = heapq.heappop(self._due)
            try:
                self._backend.play(blast_ms)
            except Exception:
                log.exception("playing a blast failed")

    def _silence(self) -> None:
        self._due.clear()
        self._backend.stop()


class _Swap:
    def __init__(self, factory: Callable[[str], AudioBackend], device: str) -> None:
        self.factory = factory
        self.device = device


class _Config:
    def __init__(self, enabled: Optional[bool] = None, volume: Optional[float] = None) -> None:
        self.enabled = enabled
        self.volume = volume


def make_backend(device: str = "") -> AudioBackend:
    """pygame.mixer if it initializes, otherwise a silent backend (never fatal)."""
    try:
        return PygameBackend(device)
    except Exception as exc:
        log.warning("no local audio (%s); local sound is off", exc)
        return NullBackend()

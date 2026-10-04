"""Sound control of one core: the two outputs, their settings, and the sound test.

Used by the leader and by followers alike (each node has its own speakers and MCU). It sits
between the services and the two sound outputs:

- local sound: ``AudioWorker`` (this machine's speakers), fed every whistle/buzzer event;
- MCU sound: the serial worker, which is told to drop or send ``$S`` / ``$B`` frames.

The sound test plays 1, 2, 3 and 5 blasts on every enabled output. It refuses while an end is
running or an emergency is active, so it can never be mistaken for a real signal.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from archerytimer.audio.audio_worker import AudioBackend, AudioWorker
from archerytimer.audio.settings import SETTING_KEYS, AudioSettings, AudioSettingsStore
from archerytimer.core import models as m
from archerytimer.hardware.serial_worker import SerialWorker
from archerytimer.ipc.messages import Message, audio_msg

log = logging.getLogger("archerytimer.core.audio")

TEST_COUNTS = (1, 2, 3, 5)
TEST_PAUSE_S = 0.8  # silence between the test signals


class AudioControl:
    def __init__(
        self,
        audio: Optional[AudioWorker] = None,
        *,
        store: Optional[AudioSettingsStore] = None,
        settings: Optional[AudioSettings] = None,
        devices: Optional[Callable[[], list[str]]] = None,
        backend_factory: Optional[Callable[[str], AudioBackend]] = None,
    ) -> None:
        self._publish: Callable[[Message], None] = lambda _m: None
        self._audio = audio
        self._backend_factory = backend_factory
        self._serial: Optional[SerialWorker] = None
        self._store = store or AudioSettingsStore(None)
        self.settings = settings or AudioSettings()
        self._devices = devices or (lambda: [])
        self._device_names: Optional[list[str]] = None
        self._blast_ms = m.EngineSettings().blast_ms
        self._gap_ms = m.EngineSettings().gap_ms
        self._busy = False  # an end is running or an emergency is active
        self._testing = threading.Event()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- lifecycle

    def bind(self, publish: Callable[[Message], None], serial: Optional[SerialWorker]) -> None:
        """Called by the owning service once its IPC server and serial worker exist."""
        self._publish = publish
        self._serial = serial

    def start(self) -> None:
        if self._audio is not None:
            self._audio.start()
        self._apply()
        self._publish(self.status_msg())

    def stop(self) -> None:
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        if self._audio is not None:
            self._audio.stop()

    def handle_message(self, msg: Message) -> bool:
        """Take the sound-related parts of a UI message. True if the whole message was ours."""
        if msg.get("type") == "settings":
            values = dict(msg.get("values") or {})
            self.on_settings({k: values[k] for k in SETTING_KEYS if k in values})
            return not (set(values) - SETTING_KEYS)
        if msg.get("type") == "cmd" and msg.get("name") == "sound_test":
            self.sound_test()
            return True
        return False

    # ---------------------------------------------------------------- events

    def submit(self, event: m.Event) -> None:
        """Every engine (or mirrored) event: feeds local audio, tracks what the test needs."""
        if isinstance(event, m.Snapshot):
            busy = event.emergency or event.mode is m.Mode.RUNNING
            if busy != self._busy:
                self._busy = busy
                self._publish(self.status_msg())
            return
        if isinstance(event, m.Whistle) and event.count > 0:
            self._blast_ms, self._gap_ms = event.blast_ms, event.gap_ms
        if isinstance(event, (m.Whistle, m.Buzzer)) and self._testing.is_set():
            return  # the test owns the outputs; real signals are blocked while it runs anyway
        if self._audio is not None:
            self._audio.submit(event)

    # ---------------------------------------------------------------- settings

    def on_settings(self, values: dict[str, object]) -> None:
        new = self.settings.updated(values)
        if new == self.settings:
            return
        old, self.settings = self.settings, new
        if (
            new.device != old.device
            and self._audio is not None
            and self._backend_factory is not None
        ):
            self._audio.set_device(self._backend_factory, new.device)
        self._store.save(new)
        self._apply()
        self._publish(self.status_msg())

    def _apply(self) -> None:
        s = self.settings
        if self._audio is not None:
            self._audio.set_volume(s.volume)
            self._audio.set_enabled(s.local)
        if self._serial is not None:
            self._serial.set_mcu_sound(s.mcu)

    def status_msg(self) -> Message:
        if self._device_names is None:
            self._device_names = self._devices()
        s = self.settings
        return audio_msg(
            local=s.local,
            mcu=s.mcu,
            volume=s.volume,
            device=s.device,
            devices=self._device_names,
            local_available=self._audio is not None and self._audio.backend.name != "none",
            busy=self._busy,
            testing=self._testing.is_set(),
        )

    # ---------------------------------------------------------------- sound test

    def sound_test(self) -> bool:
        """Start the test; False if it cannot run now (busy, already running, no output)."""
        s = self.settings
        if self._busy or self._testing.is_set() or not (s.local or s.mcu):
            return False
        self._cancel.clear()
        self._testing.set()
        self._publish(self.status_msg())
        self._thread = threading.Thread(target=self._run_test, name="sound-test")
        self._thread.start()
        return True

    def _run_test(self) -> None:
        try:
            for n in TEST_COUNTS:
                if self._cancel.is_set() or self._busy:
                    break
                ev = m.Whistle(n, self._blast_ms, self._gap_ms)
                if self.settings.local and self._audio is not None:
                    self._audio.submit(ev)
                if self.settings.mcu and self._serial is not None:
                    self._serial.submit(ev)
                length = n * (self._blast_ms + self._gap_ms) / 1000
                if self._cancel.wait(length + TEST_PAUSE_S):
                    break
        finally:
            silence = m.Whistle(0, 0, 0)
            if self._audio is not None:
                self._audio.submit(silence)
            if self._serial is not None and self.settings.mcu:
                self._serial.submit(silence)
            self._testing.clear()
            self._publish(self.status_msg())

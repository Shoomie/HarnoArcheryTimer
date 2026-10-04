"""M7: synthesized horn, local audio worker, sound control and test, whistle id healing."""

from __future__ import annotations

import array
import time
from pathlib import Path
from typing import Any, Callable

from archerytimer.audio import synth
from archerytimer.audio.audio_worker import AudioWorker, NullBackend, PygameBackend
from archerytimer.audio.settings import AudioSettings, AudioSettingsStore, from_table
from archerytimer.common.clock import MonotonicClock
from archerytimer.core import models as m
from archerytimer.core_service import audio_control
from archerytimer.core_service.audio_control import AudioControl
from archerytimer.hardware.serial_worker import LINK_UP, SerialWorker
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair


def wait_for(cond: Callable[[], bool], timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


class FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.calls: list[tuple[str, float, Any]] = []
        self.volume = 1.0
        self.closed = False

    def _log(self, what: str, arg: Any = None) -> None:
        self.calls.append((what, (time.monotonic() - self.t0) * 1000, arg))

    def play(self, duration_ms: int) -> None:
        self._log("play", duration_ms)

    def start_tone(self) -> None:
        self._log("tone")

    def stop(self) -> None:
        self._log("stop")

    def set_volume(self, volume: float) -> None:
        self.volume = volume

    def close(self) -> None:
        self.closed = True

    def plays(self) -> list[tuple[str, float, Any]]:
        return [c for c in self.calls if c[0] == "play"]


# ---------------------------------------------------------------- synth


def test_blast_has_the_right_length_and_no_click_at_the_edges():
    for ms in (100, 500, 1000):
        raw = synth.blast(ms)
        samples = array.array("h")
        samples.frombytes(raw)
        assert len(samples) == synth.RATE * ms // 1000
        assert abs(samples[0]) < 2000 and abs(samples[-1]) < 2000  # faded in and out
        assert max(abs(s) for s in samples) <= 32767 * synth.PEAK + 1
        assert max(abs(s) for s in samples) > 10000  # and actually audible


def test_sustained_tone_is_whole_cycles_so_it_loops_cleanly():
    samples = array.array("h")
    samples.frombytes(synth.sustained(1000))
    cycle = round(synth.RATE / synth.FUNDAMENTAL_HZ)
    assert len(samples) % cycle == 0
    assert samples[0] == samples[cycle]  # periodic: the loop point is seamless


# ---------------------------------------------------------------- worker


def test_whistle_blasts_are_scheduled_from_the_event_time_without_drift():
    be = FakeBackend()
    w = AudioWorker(be, MonotonicClock())
    w.start()
    try:
        w.submit(m.Whistle(3, 40, 60))
        assert wait_for(lambda: len(be.plays()) == 3)
        times = [c[1] for c in be.plays()]
        first = times[0]
        assert all(c[2] == 40 for c in be.plays())
        # 100 ms period: later blasts must not accumulate error
        assert abs((times[1] - first) - 100) < 30
        assert abs((times[2] - first) - 200) < 40
    finally:
        w.stop()
    assert be.closed


def test_silence_cancels_pending_blasts_and_disable_mutes():
    be = FakeBackend()
    w = AudioWorker(be, MonotonicClock())
    w.start()
    try:
        w.submit(m.Whistle(5, 30, 200))
        assert wait_for(lambda: len(be.plays()) >= 1)
        w.submit(m.Whistle(0, 0, 0))
        time.sleep(0.5)
        assert len(be.plays()) <= 2  # the rest were cancelled
        assert be.calls[-1][0] == "stop"
        n = len(be.calls)
        w.set_enabled(False)
        w.submit(m.Whistle(2, 20, 20))
        w.submit(m.Buzzer(True))
        time.sleep(0.2)
        assert {c[0] for c in be.calls[n:]} == {"stop"}  # muted: nothing was started
    finally:
        w.stop()


def test_buzzer_events_drive_a_steady_tone_and_volume_reaches_the_backend():
    be = FakeBackend()
    w = AudioWorker(be, MonotonicClock())
    w.start()
    try:
        w.set_volume(0.3)
        w.submit(m.Buzzer(True))
        assert wait_for(lambda: any(c[0] == "tone" for c in be.calls))
        w.submit(m.Buzzer(False))
        assert wait_for(lambda: be.calls[-1][0] == "stop")
        assert be.volume == 0.3
    finally:
        w.stop()


def test_device_swap_builds_the_new_backend_on_the_worker_thread():
    first, built = FakeBackend(), []

    def factory(device: str) -> FakeBackend:
        built.append(device)
        return FakeBackend()

    w = AudioWorker(first, MonotonicClock())
    w.start()
    try:
        w.set_device(factory, "HDMI")
        assert wait_for(lambda: built == ["HDMI"] and first.closed)
    finally:
        w.stop()


def test_pygame_backend_smoke_with_the_dummy_driver():
    be = PygameBackend()
    try:
        be.set_volume(0.5)
        be.play(50)
        be.start_tone()
        be.stop()
    finally:
        be.close()
    NullBackend().play(10)  # the silent fallback accepts everything


# ---------------------------------------------------------------- settings


def test_settings_validation_and_persistence(tmp_path: Path):
    s = AudioSettings()
    s2 = s.updated({"sound_local": False, "volume": 7, "audio_device": "x", "sound_mcu": "yes"})
    assert (s2.local, s2.volume, s2.device, s2.mcu) == (
        False,
        1.0,
        "x",
        True,
    )  # clamped, bad ignored
    store = AudioSettingsStore(tmp_path / "a.json")
    store.save(s2)
    assert store.load(AudioSettings()) == s2
    (tmp_path / "a.json").write_text("{broken", encoding="utf-8")
    assert store.load(AudioSettings()) == AudioSettings()
    assert from_table({"volume": 0.25, "local": False}).volume == 0.25


# ---------------------------------------------------------------- control + sound test


class FakeSerial:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.mcu = True

    def submit(self, ev: Any) -> None:
        self.events.append(ev)

    def set_mcu_sound(self, on: bool) -> None:
        self.mcu = on


def snap(**kw: Any) -> m.Snapshot:
    base: dict[str, Any] = dict(
        seq=1, mode=m.Mode.WAITING, sequence_id="t", phase_id="", phase_start_ns=0, deadline_ns=0,
        paused=False, remaining_at_pause_ns=0, light=m.Light.RED, group="AB", end_no=1,
        total_ends=1, practice=False, round_index=0, total_rounds=1, emergency=False, link="up",
    )  # fmt: skip
    base.update(kw)
    return m.Snapshot(**base)


def make_control(tmp_path: Path):
    be, serial, msgs = FakeBackend(), FakeSerial(), []
    worker = AudioWorker(be, MonotonicClock())
    ctl = AudioControl(worker, store=AudioSettingsStore(tmp_path / "s.json"))
    ctl.bind(msgs.append, serial)  # type: ignore[arg-type]
    ctl.start()
    return ctl, be, serial, msgs


def test_settings_update_applies_persists_and_publishes(tmp_path: Path):
    ctl, be, serial, msgs = make_control(tmp_path)
    try:
        assert msgs[-1]["type"] == "audio" and msgs[-1]["local"] and msgs[-1]["mcu"]
        assert ctl.handle_message(
            {"type": "settings", "values": {"sound_mcu": False, "volume": 0.4}}
        )
        assert serial.mcu is False
        assert msgs[-1]["mcu"] is False and msgs[-1]["volume"] == 0.4
        assert wait_for(lambda: be.volume == 0.4)
        assert AudioSettingsStore(tmp_path / "s.json").load(AudioSettings()).mcu is False
        # mixed settings messages: the sound part is taken, the rest is left for the engine
        assert not ctl.handle_message(
            {"type": "settings", "values": {"volume": 0.5, "blast_ms": 300}}
        )
    finally:
        ctl.stop()


def test_local_audio_gets_events_but_not_while_disabled(tmp_path: Path):
    ctl, be, serial, msgs = make_control(tmp_path)
    try:
        ctl.submit(m.Whistle(1, 20, 20))
        assert wait_for(lambda: len(be.plays()) == 1)
        ctl.on_settings({"sound_local": False})
        ctl.submit(m.Whistle(1, 20, 20))
        time.sleep(0.15)
        assert len(be.plays()) == 1
    finally:
        ctl.stop()


def test_sound_test_plays_1_2_3_5_on_enabled_outputs_and_then_goes_silent(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(audio_control, "TEST_PAUSE_S", 0.02)
    ctl, be, serial, msgs = make_control(tmp_path)
    try:
        ctl.submit(m.Whistle(1, 10, 10))  # teaches the test the current blast timing
        ctl.submit(snap())
        assert wait_for(lambda: len(be.plays()) == 1)
        be.calls.clear()
        assert ctl.sound_test() is True
        assert wait_for(lambda: msgs[-1]["testing"] is False and len(serial.events) >= 5, 6.0)
        counts = [e.count for e in serial.events if isinstance(e, m.Whistle)]
        assert counts == [1, 2, 3, 5, 0]  # every pattern, then explicit silence
        assert len(be.plays()) == 1 + 2 + 3 + 5
        assert any(msg["testing"] for msg in msgs)  # the UI was told it was running
    finally:
        ctl.stop()


def test_sound_test_is_refused_while_an_end_runs_or_nothing_is_enabled(tmp_path: Path):
    ctl, be, serial, msgs = make_control(tmp_path)
    try:
        ctl.submit(snap(mode=m.Mode.RUNNING))
        assert msgs[-1]["busy"] is True
        assert ctl.sound_test() is False
        ctl.submit(snap(mode=m.Mode.WAITING))
        ctl.on_settings({"sound_local": False, "sound_mcu": False})
        assert ctl.sound_test() is False  # no output to test
        ctl.submit(snap(emergency=True))
        assert msgs[-1]["busy"] is True
        assert serial.events == []
    finally:
        ctl.stop()


# ---------------------------------------------------------------- whistle ids over serial


def _rig(caps: str):
    device = SimDevice(caps=caps)
    host, dev = memory_port_pair()
    runner = SimDeviceRunner(device, dev).start()
    worker = SerialWorker(lambda: host, heartbeat_s=0.03, ack_timeout_s=0.5, backoff_s=(0.02,))
    worker.start()
    assert wait_for(lambda: worker.link == LINK_UP)
    return device, worker, runner


def test_whistle_with_id_is_repeated_but_acted_on_once():
    device, worker, runner = _rig("LSBGTW")
    try:
        worker.submit(m.Whistle(3, 500, 500))
        assert wait_for(lambda: device.sound_dupes >= 2)  # repeats at +40 ms and +120 ms
        assert device.sound_events == [3]  # but the device played the pattern once
        worker.submit(m.Whistle(1, 500, 500))  # a new command has a new id and is acted on
        assert wait_for(lambda: device.sound_events == [3, 1])
    finally:
        worker.stop()
        runner.stop()


def test_device_without_the_w_capability_gets_plain_frames_and_no_repeats():
    device, worker, runner = _rig("LSBGT")
    try:
        worker.submit(m.Whistle(2, 500, 500))
        assert wait_for(lambda: device.sound_events == [2])
        time.sleep(0.3)
        assert device.sound_events == [2] and device.sound_dupes == 0
    finally:
        worker.stop()
        runner.stop()


def test_mcu_sound_off_sends_silence_once_and_no_further_sound_frames():
    device, worker, runner = _rig("LSBGTW")
    try:
        worker.submit(m.Whistle(1, 500, 500))
        assert wait_for(lambda: device.sound_events == [1])
        worker.set_mcu_sound(False)
        assert wait_for(lambda: device.sound_events[-1] == 0)  # silenced
        n = len(device.sound_events)
        worker.submit(m.Whistle(5, 500, 500))
        worker.submit(m.Buzzer(True))
        time.sleep(0.2)
        assert len(device.sound_events) == n and device.buzzer is False
        worker.set_mcu_sound(True)
        worker.submit(m.Whistle(2, 500, 500))
        assert wait_for(lambda: device.sound_events[-1] == 2)
    finally:
        worker.stop()
        runner.stop()

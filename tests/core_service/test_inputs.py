from __future__ import annotations

import time

from archerytimer.common.clock import NS_PER_S, FakeClock, MonotonicClock
from archerytimer.core.models import Command, Light, Mode, PhaseSpec, Sequence
from archerytimer.core_service.inputs import ButtonMap, GpioInput, GpioUnavailable, parse_bindings
from archerytimer.core_service.service import CoreService
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair
from archerytimer.ipc.transport_inproc import InprocListener


def test_press_fires_immediately_and_hold_fires_on_release():
    clock = FakeClock(0)
    sent: list[Command] = []
    bindings = parse_bindings(
        {
            "mcu:1": {"press": "primary"},
            "mcu:4": {"press": "next", "hold": "reset", "hold_s": 2.0},
            "gpio:17": {"press": "clear_emergency_restart"},
        }
    )
    bm = ButtonMap(bindings, sent.append, clock)
    bm.on_event("mcu", 1, True)
    bm.on_event("mcu", 1, False)  # release does nothing for a plain binding
    assert [c.name for c in sent] == ["primary"]
    bm.on_event("mcu", 4, True)
    clock.advance(NS_PER_S // 2)
    bm.on_event("mcu", 4, False)
    bm.on_event("mcu", 4, True)
    clock.advance(3 * NS_PER_S)
    bm.on_event("mcu", 4, False)
    assert [c.name for c in sent[1:]] == ["next", "reset"]
    bm.on_event("gpio", 17, True)
    assert sent[-1] == Command("clear_emergency", {"mode": "restart"})
    bm.on_event("mcu", 99, True)  # unbound: ignored
    assert len(sent) == 4


def test_bad_bindings_are_skipped():
    b = parse_bindings(
        {
            "mcu:1": {"press": "bogus"},
            "nonsense": {"press": "primary"},
            "mcu:2": {"press": "emergency", "hold": "reset"},  # emergency must not hold
            "mcu:3": {"press": "pause"},
        }
    )
    assert list(b) == ["mcu:3"]


def test_gpio_unavailable_is_reported_not_fatal():
    try:
        GpioInput([17], lambda *a: None)
    except GpioUnavailable:
        pass  # expected on a PC without gpiozero / pin factory


def test_mcu_button_reaches_engine_through_service():
    seq = Sequence(
        "t",
        {},
        (PhaseSpec("SHOOT", 60 * NS_PER_S, Light.GREEN, 1), PhaseSpec("END", 0, Light.RED, 3)),
    )
    device = SimDevice()
    host, dev = memory_port_pair()
    runner = SimDeviceRunner(device, dev, poll_s=0.002).start()
    bindings = parse_bindings({"mcu:1": {"press": "primary"}, "mcu:3": {"press": "emergency"}})
    svc = CoreService(
        MonotonicClock(), {"t": seq}, InprocListener(), port_factory=lambda: host, bindings=bindings
    )
    svc.start()
    try:
        from archerytimer.core.models import SessionConfig

        svc.send(Command("configure", {"config": SessionConfig("t")}))
        end = time.monotonic() + 3
        while svc.engine.snapshot().link != "up" and time.monotonic() < end:
            time.sleep(0.005)
        device.press_button(1)
        while svc.engine.snapshot().mode is not Mode.RUNNING and time.monotonic() < end:
            time.sleep(0.005)
        assert svc.engine.snapshot().mode is Mode.RUNNING
        device.press_button(3)
        while not svc.engine.snapshot().emergency and time.monotonic() < end:
            time.sleep(0.005)
        assert svc.engine.snapshot().emergency
    finally:
        svc.stop()
        runner.stop()

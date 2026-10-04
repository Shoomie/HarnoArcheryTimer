from __future__ import annotations

import time
from typing import Callable

from archerytimer.core.models import Buzzer, Light, LightChange, Whistle
from archerytimer.hardware.discovery import PortInfo, select_port
from archerytimer.hardware.serial_worker import LINK_DOWN, LINK_UP, SerialWorker
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair


def wait_for(cond: Callable[[], bool], timeout: float = 2.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


class Rig:
    """Worker plus a simulated device that can be 'unplugged' and replugged."""

    def __init__(self, **worker_kw):
        self.device = SimDevice()
        self.links: list[str] = []
        self.host_ports = []
        self.runners: list[SimDeviceRunner] = []
        self.plugged = True
        kw = dict(heartbeat_s=0.03, ack_timeout_s=0.3, backoff_s=(0.02,))
        kw.update(worker_kw)
        self.worker = SerialWorker(self._factory, on_link=self.links.append, **kw)

    def _factory(self):
        if not self.plugged:
            raise OSError("unplugged")
        host, dev = memory_port_pair()
        self.host_ports.append(host)
        self.runners.append(SimDeviceRunner(self.device, dev).start())
        return host

    def unplug(self):
        self.plugged = False
        self.host_ports[-1].close()

    def __enter__(self):
        self.worker.start()
        assert wait_for(lambda: self.worker.link == LINK_UP)
        return self

    def __exit__(self, *exc):
        self.worker.stop()
        for r in self.runners:
            r.stop()


def test_events_reach_device_and_heartbeat_flows():
    with Rig() as rig:
        rig.worker.submit(LightChange(Light.GREEN))
        assert wait_for(lambda: rig.device.lights == "G")
        rig.worker.submit(Whistle(2, 500, 500))
        assert wait_for(lambda: rig.device.sound_events == [2])
        rig.worker.submit(Buzzer(True))
        assert wait_for(lambda: rig.device.buzzer)
        assert wait_for(lambda: (rig.device.last_heartbeat_seq or 0) >= 3)
        assert rig.worker.info is not None and rig.worker.info.proto == 1
        assert rig.worker.latencies


def test_unplug_reports_down_then_reconnects_and_restores_state():
    with Rig() as rig:
        rig.worker.submit(LightChange(Light.GREEN))
        assert wait_for(lambda: rig.device.lights == "G")
        rig.unplug()
        assert wait_for(lambda: rig.worker.link == LINK_DOWN)
        rig.worker.submit(LightChange(Light.YELLOW))  # arrives while down
        rig.plugged = True
        assert wait_for(lambda: rig.worker.link == LINK_UP)
        assert wait_for(lambda: rig.device.lights == "Y")
        assert rig.links == [LINK_UP, LINK_DOWN, LINK_UP]


def test_silent_device_is_declared_down():
    with Rig() as rig:
        rig.device.mute = True
        assert wait_for(lambda: rig.worker.link == LINK_DOWN)


def test_stop_sends_red_and_silence():
    rig = Rig()
    with rig:
        rig.worker.submit(LightChange(Light.GREEN))
        assert wait_for(lambda: rig.device.lights == "G")
        rig.worker.stop()
        assert wait_for(lambda: rig.device.lights == "R" and rig.device.whistle == 0)
        assert not rig.device.buzzer


def test_never_connects_without_device():
    rig = Rig()
    rig.plugged = False
    rig.worker.start()
    time.sleep(0.1)
    assert rig.worker.link == LINK_DOWN
    rig.worker.stop()


def test_select_port():
    ports = [
        PortInfo("COM1", None, None, "Communications Port"),
        PortInfo("COM7", 0x303A, 0x1001, "USB JTAG"),
    ]
    assert select_port(ports).device == "COM7"
    assert select_port(ports, "COM1").device == "COM1"
    assert select_port(ports, "COM9").device == "COM9"
    assert select_port(ports[:1]) is None


def test_factory_rotates_through_candidates(monkeypatch):
    from archerytimer.hardware import discovery

    opened = []
    monkeypatch.setattr(discovery, "open_serial", lambda dev, baud=115200: opened.append(dev))
    ports = [PortInfo("COM3", 0x2341, 0x0043), PortInfo("COM7", 0x303A, 0x1001)]
    factory = discovery.make_port_factory(lister=lambda: ports)
    for _ in range(3):
        factory()
    assert opened == ["COM3", "COM7", "COM3"]


def test_lights_toggle_keeps_this_device_dark_and_restores():
    with Rig() as rig:
        rig.worker.submit(LightChange(Light.GREEN))
        assert wait_for(lambda: rig.device.lights == "G")
        rig.worker.set_lights(False)
        assert wait_for(lambda: rig.device.lights == "O")
        rig.worker.submit(LightChange(Light.YELLOW))  # engine moves on; this device stays dark
        time.sleep(0.1)
        assert rig.device.lights == "O"
        rig.worker.set_lights(True)
        assert wait_for(lambda: rig.device.lights == "Y")

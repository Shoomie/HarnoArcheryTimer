"""Port discovery for native USB and USB-UART bridge boards, and the no-reset open helper."""

from __future__ import annotations

import sys
import types
from typing import Any, ClassVar

import pytest

from archerytimer.hardware import discovery
from archerytimer.hardware.discovery import (
    PortInfo,
    candidate_ports,
    chip_note,
    is_uart_bridge,
    open_serial,
)

BRIDGES = [
    (0x10C4, 0xEA60, "CP210x"),
    (0x1A86, 0x7523, "CH340"),
    (0x1A86, 0x55D4, "CH9102"),
    (0x0403, 0x6001, "FTDI"),
]


@pytest.mark.parametrize(("vid", "pid", "word"), BRIDGES)
def test_bridge_ids_are_known(vid, pid, word):
    info = PortInfo("COM5", vid, pid)
    assert word in chip_note(info)
    assert is_uart_bridge(info)
    assert candidate_ports([info]) == [info]


def test_native_usb_is_not_a_bridge():
    assert not is_uart_bridge(PortInfo("COM7", 0x303A, 0x1001))
    assert not is_uart_bridge(PortInfo("COM1"))


def test_exact_project_device_is_tried_before_bridges():
    ports = [
        PortInfo("COM3", 0x10C4, 0xEA60),
        PortInfo("COM9", 0x303A, 0x1001),
        PortInfo("COM1", None, None, "Communications Port"),
        PortInfo("COM4", 0x1A86, 0x7523),
    ]
    assert [i.device for i in candidate_ports(ports)] == ["COM9", "COM3", "COM4"]


class FakeSerial:
    instances: ClassVar[list[FakeSerial]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.log: list[tuple[str, Any]] = [("init", args or kwargs)]
        self.is_open = False
        self._port = None
        self._dtr = True  # pyserial's defaults
        self._rts = True
        FakeSerial.instances.append(self)
        if args:
            self.port = args[0]
            self.open()

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, v: bool) -> None:
        self._dtr = v
        self.log.append(("dtr", v))

    @property
    def rts(self) -> bool:
        return self._rts

    @rts.setter
    def rts(self, v: bool) -> None:
        self._rts = v
        self.log.append(("rts", v))

    def open(self) -> None:
        self.log.append(("open", (self._dtr, self._rts)))
        self.is_open = True


@pytest.fixture
def fake_serial(monkeypatch):
    FakeSerial.instances = []
    mod = types.ModuleType("serial")
    mod.Serial = FakeSerial  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "serial", mod)
    return FakeSerial


def test_bridge_open_keeps_dtr_rts_low_at_open(fake_serial):
    port = open_serial("COM5", 115200, bridge=True)
    ser = fake_serial.instances[0]
    assert port is ser and ser.is_open
    assert ("open", (False, False)) in ser.log  # lines low BEFORE the port is opened
    assert ser.dtr is False and ser.rts is False
    assert ser.baudrate == 115200 and ser.port == "COM5"


def test_native_open_is_the_plain_pyserial_open(fake_serial):
    open_serial("COM7")
    ser = fake_serial.instances[0]
    assert ser.is_open
    assert ser.dtr is True  # untouched


def test_factory_opens_bridges_without_reset(monkeypatch):
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        discovery,
        "open_serial",
        lambda dev, baud=115200, bridge=False: calls.append((dev, bridge)),
    )
    ports = [PortInfo("COM4", 0x1A86, 0x55D4), PortInfo("COM9", 0x303A, 0x1001)]
    factory = discovery.make_port_factory(lister=lambda: ports)
    factory()
    factory()
    assert calls == [("COM9", False), ("COM4", True)]

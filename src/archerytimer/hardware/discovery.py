"""Find the microcontroller's serial port by USB VID/PID, with a manual override."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from archerytimer.hardware.sim_device import Port

# (vid, pid or None for any) -> chip note shown on the hardware status screen
KNOWN_DEVICES: dict[tuple[int, Optional[int]], str] = {
    (0x303A, None): "ESP32-S3/C3 native USB",
    (0x2E8A, None): "RP2040 native USB",
    (0x16C0, None): "Teensy native USB",
    (0x2341, None): "Arduino",
    (0x0403, None): "FTDI bridge (set latency_timer to 1 ms)",
    (0x1A86, 0x7523): "CH340 bridge",
    (0x10C4, 0xEA60): "CP210x bridge",
}


@dataclass(frozen=True)
class PortInfo:
    device: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    description: str = ""


def chip_note(info: PortInfo) -> str:
    if info.vid is None:
        return ""
    return KNOWN_DEVICES.get((info.vid, info.pid)) or KNOWN_DEVICES.get((info.vid, None), "")


def candidate_ports(ports: Iterable[PortInfo], override: str = "") -> list[PortInfo]:
    """Ports worth a handshake, in a stable order. The override alone when one is given."""
    ports = list(ports)
    if override:
        for info in ports:
            if info.device == override:
                return [info]
        return [PortInfo(override)]
    return [i for i in sorted(ports, key=lambda i: i.device) if chip_note(i)]


def select_port(ports: Iterable[PortInfo], override: str = "") -> Optional[PortInfo]:
    """The first candidate port, or None."""
    found = candidate_ports(ports, override)
    return found[0] if found else None


def list_ports() -> list[PortInfo]:
    from serial.tools import list_ports as lp

    return [PortInfo(p.device, p.vid, p.pid, p.description or "") for p in lp.comports()]


def open_serial(device: str, baud: int = 115200) -> Port:
    import serial

    port: Port = serial.Serial(device, baud, timeout=0.02, write_timeout=0.1)
    return port


def make_port_factory(
    override: str = "", lister: Callable[[], Iterable[PortInfo]] = list_ports
) -> Callable[[], Port]:
    """A factory for ``SerialWorker``: re-runs discovery on every (re)connect attempt.

    Each call opens the next candidate port, so when the first match is not our firmware
    (the worker's hello handshake fails and it calls again) every candidate gets its turn.
    """
    cursor = 0

    def factory() -> Port:
        nonlocal cursor
        found = candidate_ports(lister(), override)
        if not found:
            raise OSError("no matching serial port found")
        info = found[cursor % len(found)]
        cursor += 1
        return open_serial(info.device)

    return factory

"""Listing serial ports (through pyserial inside the tool environment) and guessing the board."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from .strings import t
from .toolenv import Ctx


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    vid: Optional[int]
    pid: Optional[int]

    @property
    def usb_id(self) -> str:
        if self.vid is None or self.pid is None:
            return "no USB id"
        return f"{self.vid:04X}:{self.pid:04X}"


def guess_board(p: PortInfo) -> str:
    vid = p.vid
    if vid == 0x303A:
        return t("guess.espressif")
    if vid == 0x10C4:
        return t("guess.cp210x")
    if vid == 0x1A86:
        return t("guess.ch340")
    if vid == 0x0403:
        return t("guess.ftdi")
    return t("guess.unknown")


def parse_ports(text: str) -> list[PortInfo]:
    try:
        raw = json.loads(text.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        out.append(
            PortInfo(
                device=str(item.get("device", "")),
                description=str(item.get("description", "")),
                vid=item.get("vid"),
                pid=item.get("pid"),
            )
        )
    return [p for p in out if p.device]


def list_ports(ctx: Ctx) -> list[PortInfo]:
    script = ctx.tools_dir / "listports.py"
    rc, out = ctx.runner.capture([str(ctx.venv_python), str(script)])
    return parse_ports(out) if rc == 0 else []


def describe(p: PortInfo) -> str:
    return f"{p.device} [{p.usb_id}] {p.description}"

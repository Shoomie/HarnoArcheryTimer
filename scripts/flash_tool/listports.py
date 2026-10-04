"""Runs INSIDE the tool environment (needs pyserial): prints the serial ports as JSON."""

from __future__ import annotations

import json


def main() -> None:
    from serial.tools import list_ports

    out = [
        {
            "device": p.device,
            "description": p.description or "",
            "vid": p.vid,
            "pid": p.pid,
            "manufacturer": p.manufacturer or "",
        }
        for p in sorted(list_ports.comports(), key=lambda p: p.device)
    ]
    print(json.dumps(out))


if __name__ == "__main__":
    main()

"""Runs INSIDE the tool environment (needs pyserial): simple serial monitor, 115200, Ctrl+C leaves."""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import serial

    port = argv[1]
    try:
        with serial.Serial(port, 115200, timeout=0.2) as ser:
            while True:
                data = ser.read(256)
                if data:
                    sys.stdout.write(data.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
    except KeyboardInterrupt:
        return 0
    except serial.SerialException as exc:
        print(f"Cannot use {port}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

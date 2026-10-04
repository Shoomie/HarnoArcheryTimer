"""Desktop convenience: start the core service and one UI client, stop both together.

    python -m archerytimer.launcher [--no-serial] [-- <ui client args>]

On the Pi these are two systemd units instead. Extra arguments after ``--`` go to the UI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-serial", action="store_true")
    ap.add_argument("--serial-port", default="")
    args, ui_args = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
    ui_args = [a for a in ui_args if a != "--"]

    core_cmd = [sys.executable, "-m", "archerytimer.core_service"]
    if args.no_serial:
        core_cmd.append("--no-serial")
    if args.serial_port:
        core_cmd += ["--serial-port", args.serial_port]
    core = subprocess.Popen(core_cmd)
    try:
        time.sleep(0.5)
        ui = subprocess.Popen([sys.executable, "-m", "archerytimer.ui_client", *ui_args])
        while ui.poll() is None and core.poll() is None:
            time.sleep(0.2)
        # The UI is closing, or the core died: either way the UI side ends first.
        if ui.poll() is None:
            ui.terminate()
        return ui.wait() or 0
    except KeyboardInterrupt:
        return 0
    finally:
        core.terminate()
        try:
            core.wait(5)
        except subprocess.TimeoutExpired:
            core.kill()


if __name__ == "__main__":
    raise SystemExit(main())

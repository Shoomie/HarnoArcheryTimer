#!/usr/bin/env bash
# One-time setup on desktop Linux or macOS: creates .venv in the project folder and installs the app.
# (For a Raspberry Pi kiosk use scripts/install_pi.sh instead.)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v python3 >/dev/null || { echo "python3 not found (Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip)" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "Python 3.9 or newer is required" >&2; exit 1; }
python3 -m venv .venv || { echo "venv failed (Debian/Ubuntu: sudo apt install python3-venv)" >&2; exit 1; }
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
echo
echo "Done. Start the timer with: scripts/start.sh"
if [ "$(uname)" = Linux ] && ! id -nG | tr ' ' '\n' | grep -qx dialout; then
    echo "Note: to use the USB lights hardware, add yourself to the serial group, then log out and in:"
    echo "  sudo usermod -aG dialout \$USER"
fi

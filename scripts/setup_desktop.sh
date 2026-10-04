#!/usr/bin/env bash
# One-time setup on desktop Linux or macOS: creates .venv in the project folder and installs the app.
# On Linux it also gives the program access to the USB serial port of the lights/radio board
# (one sudo prompt; skip with --no-system). For a Raspberry Pi kiosk use scripts/install_pi.sh instead.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
NO_SYSTEM=0
[ "${1:-}" = "--no-system" ] && NO_SYSTEM=1
command -v python3 >/dev/null || { echo "python3 not found (Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip)" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "Python 3.9 or newer is required" >&2; exit 1; }
python3 -m venv .venv || { echo "venv failed (Debian/Ubuntu: sudo apt install python3-venv)" >&2; exit 1; }
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

if [ "$(uname)" = Linux ] && [ "$NO_SYSTEM" = 0 ]; then
    # Serial port access: the board shows up as /dev/ttyACM* (group dialout; uucp on Arch).
    # The udev rule (1) gives the logged-in desktop user access at once (no log out needed) and
    # (2) tells ModemManager to leave our boards alone (it otherwise probes them with AT commands).
    GROUP=dialout
    getent group dialout >/dev/null || { getent group uucp >/dev/null && GROUP=uucp; }
    RULE=/etc/udev/rules.d/99-archerytimer.rules
    if command -v sudo >/dev/null; then
        echo
        echo "Giving this computer access to the timer's USB board (asks for your password once)..."
        sudo usermod -aG "$GROUP" "$USER" || true
        sudo tee "$RULE" >/dev/null <<'RULES'
# Archery timer boards: ESP32 native USB (303a), CP210x (10c4:ea60), CH340/CH9102 (1a86)
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
RULES
        sudo udevadm control --reload-rules || true
        sudo udevadm trigger --subsystem-match=tty || true
    else
        echo "Note: no sudo here. As an administrator run: usermod -aG $GROUP $USER (then log in again)."
    fi
fi
echo
echo "Done. Start the timer with: scripts/start.sh"

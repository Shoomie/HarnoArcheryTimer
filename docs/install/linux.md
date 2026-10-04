# Install on desktop Linux (and macOS)

[Svenska](linux.sv.md) · [Windows](windows.md) · [Raspberry Pi](raspberry-pi.md) · [Back to README](../../README.md)

For a Raspberry Pi that boots straight into the timer, use the [Raspberry Pi guide](raspberry-pi.md) instead.
This page is for a normal Linux PC or laptop with a desktop (tested on the Debian/Ubuntu family; others work
if they have Python 3.9+).

## 1. Install the prerequisites

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`. Arch: `sudo pacman -S git python sdl2`.

macOS: install Python 3 from <https://www.python.org/downloads/> (or `brew install python`).

## 2. Download the project

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

No git? Download the ZIP from the GitHub page (**Code → Download ZIP**) and unpack it.

## 3. Set up (once)

```bash
scripts/setup_desktop.sh
```

This creates a private environment in `.venv` and installs the timer into it. If the script is not executable,
run it as `bash scripts/setup_desktop.sh`.

## 4. Start the timer

```bash
scripts/start.sh
```

- Demo without lights hardware: `scripts/start.sh --no-serial`
- Fullscreen: `scripts/start.sh -- --fullscreen`
- English interface: `scripts/start.sh -- --lang en`
- Audience screen on the second monitor, no controls: `scripts/start.sh -- --profile audience --display 1`

Keys: **Space** = the big button, **P** = pause, **Esc** = emergency stop. See the
[README](../../README.md#controls).

## 5. Connect the lights and horn (optional)

1. Nothing to do by hand: `scripts/setup_desktop.sh` (step 2) already gave this computer access to the board
   (serial group plus a udev rule that also keeps ModemManager away from it; it asks for your password once;
   `--no-system` skips it) and `scripts/start.sh` works without logging out. If you skipped it, run
   `sudo usermod -aG dialout $USER` and log in again.

2. Plug in the ESP32 board. It is found automatically. To choose the port yourself, find it with
   `ls /dev/ttyACM* /dev/ttyUSB*` and start with `scripts/start.sh --serial-port /dev/ttyACM0`.

The board firmware is in [`firmware/`](../../firmware/) and has **not been tested on real hardware yet**.

## Update

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

Settings are kept in `~/.local/share/archerytimer` (macOS: `~/Library/Application Support/archerytimer`).

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` and run the setup again |
| No window / SDL error | Make sure you run it inside a desktop session (not over plain SSH); install `libsdl2-2.0-0` |
| "Permission denied" on the serial port | Step 5: `dialout` group, then log out and in |
| No sound from the PC speakers | Check the output device in the program's sound settings; ALSA/PulseAudio must work for other apps first |
| Logs | `~/.local/share/archerytimer/logs/` |

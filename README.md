# Archery Timer

**English** · [Svenska](README.sv.md)

An open-source archery shooting clock. It runs the timer at competitions and training, shows it on a TV or
monitor, and drives traffic lights and a horn over USB. Built for a small archery club and operated by
volunteers, so the screen has one obvious button for what happens next and an always-visible emergency stop.

- Runs on **Windows 10/11**, **Linux**, **Raspberry Pi** (2B and up, as a TV kiosk) and macOS.
- Swedish and English interface (Swedish is the default).
- Timer, lights and sound keep running even if the display crashes.
- Optional ESP32 board for lights and horn, optional second screens and several devices on one network.

> **Status: early development.** The timer, display, serial protocol and multi-device features are built and
> tested in simulation. It has **not** been tried on real lights/horn hardware yet, and the ESP32 firmware has
> never been flashed. The timings in `config/` are **placeholders**, not confirmed World Archery / SBF rules.
> Do not rely on it for an official competition yet. Details: "Current status" in [CLAUDE.md](CLAUDE.md).

## Install

Pick your system. Each guide goes from nothing to a running timer, step by step.

| System | Guide | Short version |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.md](docs/install/windows.md) | Install Python, download the project, double-click `scripts\setup_windows.bat`, then `scripts\start_windows.bat` |
| **Linux** (and macOS) | [docs/install/linux.md](docs/install/linux.md) | `scripts/setup_desktop.sh`, then `scripts/start.sh` |
| **Raspberry Pi** (TV kiosk) | [docs/install/raspberry-pi.md](docs/install/raspberry-pi.md) | Flash Pi OS Lite, `git clone`, `sudo scripts/install_pi.sh`, reboot |

### Quick start (any desktop, no hardware needed)

1. Install **Python 3.9 or newer** ([python.org](https://www.python.org/downloads/); on Linux usually
   `sudo apt install python3 python3-venv python3-pip`).
2. Download the project: on GitHub press **Code → Download ZIP** and unpack it, or
   `git clone <repository-url>`.
3. In the project folder run the setup script once, then the start script:

   | | Setup (once) | Start |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` means "no lights hardware connected". Leave it out when an ESP32 board is plugged in; the
   program finds it automatically.

### Controls

| Key | Action |
| --- | --- |
| **Space** / Enter | The big button: whatever happens next (open setup, start the end, ...) |
| **P** | Pause / resume |
| **Esc** | **Emergency stop**: red lights and silence, always one press |
| N / Backspace | Next phase / back |

Everything also works with the mouse. Clickers that act as keyboards work too. Full list: [docs/ui.md](docs/ui.md).

### Useful start options

Add them after the start script, display options after `--`:

```text
scripts/start.sh --no-serial                      demo without hardware
scripts/start.sh --serial-port COM7               choose the USB port yourself (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang en        fullscreen, English
scripts/start.sh -- --profile audience --display 1   audience screen on the second monitor, no controls
```

On Windows use `scripts\start_windows.bat` instead of `scripts/start.sh`.

## Documentation

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | Index of all documentation |
| [docs/install/](docs/install/) | Install guides (English and Swedish) |
| [docs/ui.md](docs/ui.md) · [docs/audio.md](docs/audio.md) | Screen, keys, sound |
| [docs/cluster.md](docs/cluster.md) · [docs/espnow.md](docs/espnow.md) | Several devices, wireless sync |
| [docs/protocol.md](docs/protocol.md) · [firmware/](firmware/) | USB serial protocol and ESP32 firmware |
| [docs/flashing.md](docs/flashing.md) | Flash the ESP32 modules: `scripts/flash.bat` (Windows) or `scripts/flash.sh` |
| [structure.md](structure.md) | Where everything is in the source tree |

## Repository layout

```text
src/archerytimer/   the program (core service, UI client, hardware, audio, IPC)
config/             timing sequences and setup presets (TOML, placeholders)
locales/            all texts, sv.toml and en.toml
assets/             font (Inter, OFL)
firmware/           ESP32 firmware (PlatformIO) and shared test vectors
scripts/            install/start scripts, Raspberry Pi installer, benchmarks
docs/               documentation
tests/  tools/      test suite, mesh simulator
```

## Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # tests (some skip on Windows)
ruff check . && ruff format --check .
mypy
```

Project rules and architecture: [CLAUDE.md](CLAUDE.md). Benchmarks: [docs/benchmarks.md](docs/benchmarks.md).

## License

Not chosen yet. Until a `LICENSE` file is added, all rights are reserved by the author. The bundled Inter font
is under the SIL Open Font License (`assets/fonts/OFL.txt`).

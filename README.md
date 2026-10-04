# Archery Timer

**English** · [Svenska](README.sv.md)

An open-source archery shooting clock. It runs the timer at competitions and training, shows it on a TV or
monitor, and drives traffic lights and a horn over USB. Built for a small archery club and operated by
volunteers, so the screen has one obvious button for what happens next and an always-visible emergency stop.

- Runs on **Windows 10/11**, **Linux**, **Raspberry Pi** (2B and up, as a TV kiosk) and macOS.
- Swedish and English interface (Swedish is the default).
- Timer, lights and sound keep running even if the display crashes.
- Optional ESP32 board for lights and horn, optional second screens and several devices on one network.

> **Before an official competition:** the timings in `config/` are **placeholders**, not confirmed World Archery / SBF
> rules. Check them against the current rules and edit the TOML files (clubs can add their own presets, no code change).
> The system has been tested end to end on a Windows PC, a Linux PC and a Raspberry Pi 2B with ESP32-C3 and WROOM-32D
> modules. Not yet covered: a 4-hour soak run, ESP32-S3 boards and long-range radio tests.

## Running a session

1. Start the program (see Install below). Press **Space** or the big button: the setup opens.
2. Pick a card (for example *Indoor 18 m*), choose lines and number of ends, then start.
3. The big button always says what happens next: start the end, next end, resume. **P** pauses. **Esc** is the
   emergency stop: red lights and silence, always one press, no confirmation.

The screen shows a big light (with a symbol, not colour alone), the countdown, the end and line, and the state of the
hardware in plain words.

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
| S | Stop the end |
| N / Backspace | Next phase / back (Back reads *Ångra* / Undo for 5 seconds after Stop or Next) |
| M / F1 | Menu: new session, timers, settings, hardware status, network, sound, quit |

Everything also works with the mouse. Presentation clickers and foot pedals that act as keyboards work too, and so do the
buttons of the ESP32 modules. Full list: [docs/ui.md](docs/ui.md).

### Useful start options

Add them after the start script, display options after `--`:

```text
scripts/start.sh --no-serial                      demo without hardware
scripts/start.sh --serial-port COM7               choose the USB port yourself (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang en        fullscreen, English
scripts/start.sh -- --profile audience --display 1   audience screen on the second monitor, no controls
```

On Windows use `scripts\start_windows.bat` instead of `scripts/start.sh`.

## Lights, horn and more devices

| I want to... | Read |
| --- | --- |
| Connect traffic lights and a horn (ESP32 board, wiring, pins) | [docs/firmware.md](docs/firmware.md) |
| Flash an ESP32 module (Windows, Linux, macOS; no compiler needed) | [docs/flashing.md](docs/flashing.md): `scriptslash.bat` or `sh scripts/flash.sh` |
| Set up the horn and speakers, sound test | [docs/audio.md](docs/audio.md) |
| Run several screens, PCs or Pis as one timer (LAN or radio) | [docs/cluster.md](docs/cluster.md) |
| Wireless light boxes and remote buttons | [docs/mesh.md](docs/mesh.md) |

## Documentation

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | Index of all documentation |
| [docs/install/](docs/install/) | Install guides (English and Swedish) |
| [docs/ui.md](docs/ui.md) | Screens, keys, display profiles |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | USB serial protocol; core to display protocol |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Raspberry Pi internals; timing and rendering measurements |
| [structure.md](structure.md) | Where everything is in the source tree |

## Repository layout

```text
src/archerytimer/   the program (core service, UI client, hardware, audio, IPC)
config/             timing sequences and setup presets (TOML, placeholders)
locales/            all texts, sv.toml and en.toml
assets/             font (Inter, OFL)
firmware/           ESP32 firmware (PlatformIO), prebuilt images, shared test vectors
scripts/            install/start scripts, Raspberry Pi installer, flashing menu, benchmarks
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

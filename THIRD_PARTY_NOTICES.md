# Third-party components

The project's own code, documentation, hardware notes, synthesized sounds and firmware sources are
under the MIT licence (`LICENSE`). The parts below belong to other authors and keep their own licences.
All of them allow free use, modification and redistribution.

| Component | Used for | Licence |
| --- | --- | --- |
| [Inter](https://rsms.me/inter/) (`assets/fonts/`) | UI font, bundled | SIL Open Font License 1.1 (`assets/fonts/OFL.txt`) |
| [pygame-ce](https://pyga.me/) | UI, audio output (not bundled; installed from PyPI/apt) | LGPL-2.1 |
| [pyserial](https://github.com/pyserial/pyserial) | USB serial (not bundled) | BSD-3-Clause |
| [platformdirs](https://github.com/tox-dev/platformdirs) | Per-user data dirs (not bundled) | MIT |
| [tomli](https://github.com/hukkin/tomli) | TOML on Python < 3.11 (not bundled) | MIT |
| [Arduino-ESP32](https://github.com/espressif/arduino-esp32) | Firmware framework, compiled into `firmware/release/*.bin` | LGPL-2.1 |
| [ESP-IDF](https://github.com/espressif/esp-idf) | Underneath Arduino-ESP32, compiled into the firmware images | Apache-2.0 |

Notes:

- pygame-ce is used as an unmodified, separately installed library, which the LGPL allows from any
  licence. Replace it with another build at any time.
- The prebuilt firmware images contain Arduino-ESP32 and ESP-IDF code. The complete firmware source and
  build settings are in `firmware/`, so the images can be rebuilt (and Arduino-ESP32 swapped) with
  PlatformIO, as the LGPL requires.
- Development tools (pytest, ruff, mypy, PlatformIO) are not distributed with the project.
- Hardware designs, wiring notes and the serial and mesh protocols described in `docs/` are free to
  implement, including in commercial or closed products.

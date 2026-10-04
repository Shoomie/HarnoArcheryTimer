# Flashing the ESP32 modules

One menu does everything, on Windows, Linux and macOS, from the project folder. It needs only Python 3.9+
(no `.venv`).

| System | Start it with |
| --- | --- |
| Windows | double-click `scripts\flash.bat` (or `scripts\flash.bat --action check`) |
| Linux / macOS / Pi | `sh scripts/flash.sh` |
| Anywhere | `python scripts/flash.py` |

The menu is tested without a board (fake runner in `tests/scripts/test_flash_tool.py`) and has been used to flash the
C3 Super Mini and WROOM-32D modules.

## The menu

1. **Flash a module (normal way)**: shows the connected ports, detects the chip, proposes the matching
   firmware, asks for confirmation, writes the ready-made image and checks it.
2. **Build from source and flash (advanced)**: needs PlatformIO (about 1 GB, installed only if you agree).
3. **Create release images (developer)**: builds all variants and writes `firmware/release/<env>.bin` plus
   `manifest.json` (env, chip, version, size, sha256, build date).
4. **Open serial monitor**: 115200 baud, Ctrl+C leaves.
5. **Erase a module**: asks first; the default answer is No.
6. **Check this computer**: Python, USB driver and port permission hints. Changes nothing.
7. **Show what is installed** / 8. **Remove the tool environment**.

Safety rules the menu follows: nothing is written without a question that names the port and the image; only
the port you picked is touched; a firmware for the wrong chip is refused; an image that does not match
`manifest.json` is refused.

## Which firmware?

| Variant | Chip | Meaning |
| --- | --- | --- |
| `esp32-s3-devkitc-1` | ESP32-S3 | normal box: plugged into the timer computer |
| `esp32-s3-standalone` | ESP32-S3 | stand-alone box: follows the radio, e.g. on a USB charger |
| `esp32c3-supermini` | ESP32-C3 | normal box |
| `esp32c3-standalone` | ESP32-C3 | stand-alone box |
| `esp32-wroom-32d` | ESP32 | normal box |
| `esp32-wroom-32d-standalone` | ESP32 | stand-alone box |

## Three flows for a volunteer

### 1. Flash a new module

1. Plug the module into the computer with a USB **data** cable.
2. Start the menu and type `1` (Flash a module).
3. The first time only: the menu says it will download the flashing tool (a few MB) into the project folder
   `.flash-env`. Type `y`.
4. Pick the port from the list (the menu says what it looks like, for example "ESP32-S3 with built-in USB").
5. The menu finds the chip and lists the matching firmware. Choose **normal box**.
6. Read the confirmation (image, port, chip) and type `y`. Wait about a minute; do not unplug.
7. "Done" means it was written and checked. Test it in the program (Hardware screen).

If the chip cannot be found: hold the BOOT button while plugging in USB, then try again.

### 2. Update a module

Same as flow 1 with the new `firmware/release` folder. Choose the **same kind** (normal or stand-alone) as
before. Flashing a merged release image wipes the settings stored on the module (radio keys, role): pair it again.
If a module acts strangely after an update, use menu `5` (Erase) and flash again.

### 3. A stand-alone box (follows the radio, no computer)

1. Flow 1, but choose **stand-alone box** in step 5.
2. Plug it into a USB charger. A stand-alone box has no mesh key yet: it asks the main timer to pair, and the operator accepts it under Menu > Wireless remotes (see [mesh.md](mesh.md)).

## Non-interactive use

```text
python scripts/flash.py --env esp32c3-supermini --port COM5 --yes      # flash (implied)
python scripts/flash.py --action ports --yes
python scripts/flash.py --action release --yes --install-pio [--env esp32c3-supermini ...]
python scripts/flash.py --action check
```

Actions: `flash build release monitor erase check installed remove ports`. `--yes` answers yes to the
questions (including the small esptool download) but **not** to the 1 GB PlatformIO download, which also needs
`--install-pio`. Environment variables: `FLASH_PIO=<path to pio>` use that PlatformIO instead of installing one,
`PLATFORMIO_CORE_DIR` where PlatformIO keeps its toolchains (see below).

## Building from source and release images (developers)

PlatformIO is installed into `.flash-env/` on demand. Its toolchains (about 1 GB) go to
`.flash-env/pio-core`, or, on Windows when that path is long, to the short folder `C:\pio` (the compiler
fails on paths over 260 characters). `Remove the tool environment` offers to delete that folder too.

Release images: `esptool merge-bin` joins bootloader (0x1000 on ESP32, 0x0 on S3 and C3), partitions (0x8000),
`boot_app0` (0xE000) and the firmware (0x10000) into one image that is written at **0x0** on every chip.
**Rebuild and commit `firmware/release/` whenever the firmware changes**, and bump `firmware/esp32s3/src/version.h`
(the version in the manifest is read from there). Menu 3 builds all six images; existing manifest entries are kept when only some variants are rebuilt.

## Why prebuilt images and an on-demand tool environment

Volunteers should never need a compiler, and the Pi never flashes or compiles (a Pi 2B is slow and short of disk for 1 GB of
toolchains). So:

- Prebuilt merged images in `firmware/release/` pin a tested build; they must be rebuilt and committed when the firmware changes.
- The menu installs only `esptool` (a few MB, pure Python) into the project-local `.flash-env/` on first use, after asking.
- PlatformIO goes into the same folder only when someone chooses "build from source" or "create release images", with the 1 GB
  warning; `--yes` does not approve it.
- Nothing is added to `install_pi.sh`, the deploy script or `pyproject.toml`, so the app's `.venv` stays free of firmware tooling.
  To flash from a Pi: `sh scripts/flash.sh` (esptool runs fine there).

esptool is pinned to the 5.x series (`>=5,<6`, hyphenated command names). Change `ESPTOOL_SPEC` in
`scripts/flash_tool/toolenv.py` if a later major version changes the commands.

## Troubleshooting

* No port appears: use a data cable; Windows may need the CP210x or CH340/CH9102 driver (menu 6 explains).
* Linux "permission denied": `sudo usermod -a -G dialout $USER`, then log out and in again.
* Chip not detected: hold BOOT while plugging in; close any serial monitor that holds the port.
* Strings: all text lives in one dict at the top of `scripts/flash_tool/strings.py`; a Swedish dict can be added
  there.

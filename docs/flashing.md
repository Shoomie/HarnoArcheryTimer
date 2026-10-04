# Flashing the ESP32 modules

One menu does everything, on Windows, Linux and macOS, from the project folder. It needs only Python 3.9+
(no `.venv`).

| System | Start it with |
| --- | --- |
| Windows | double-click `scripts\flash.bat` (or `scripts\flash.bat --action check`) |
| Linux / macOS / Pi | `sh scripts/flash.sh` |
| Anywhere | `python scripts/flash.py` |

Status: **not verified on hardware.** The menu, its command lines and the image creation were tested without
a board (fake runner in `tests/scripts/test_flash_tool.py`; images were built and merged on Windows). Nothing has
been flashed yet. Do the first flash with one module and report what happens.

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
before. Settings stored on the module (radio keys, role) are replaced by the flash: set them again if needed.
If a module acts strangely after an update, use menu `5` (Erase) and flash again.

### 3. A stand-alone box (follows the radio, no computer)

1. Flow 1, but choose **stand-alone box** in step 5.
2. Give it a mesh key over USB the first time (see `docs/mesh.md`), then plug it into a USB charger.

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
(the version in the manifest is read from there). The six images are produced with menu 3 once the
`esp32` firmware folder exists; existing manifest entries are kept when only some variants are rebuilt.

## Dependency evaluation

The question: where do `esptool` and PlatformIO live?

| Option | For | Against |
| --- | --- | --- |
| (i) in `install_pi.sh`, the deploy script or a `pyproject` extra | one install step | The Pi never flashes or compiles. A Pi 2B/Zero is slow and short of disk for 1 GB of toolchains. It would pollute the app `.venv` with firmware tooling, and volunteers would wait for a download they do not need. |
| (ii) on-demand bootstrap in the menu | installs only when used, only after asking; project-local, removable, works the same on all three systems | first use needs internet |
| (iii) prebuilt images + esptool only | volunteers never need a compiler; a prebuilt image pins a tested build; esptool is a few MB and pure Python | images must be rebuilt and committed when the firmware changes |

**Recommendation (implemented): (iii) + (ii).** Ship prebuilt merged images in `firmware/release/`; the menu
installs only `esptool` into `.flash-env/` on first use (after asking); PlatformIO is installed there only when
someone chooses "build from source" or "create release images", with the 1 GB warning, and `--yes` does not
approve it. Nothing is added to `install_pi.sh`, the deploy script or `pyproject.toml`. The app's `.venv` stays
free of firmware tooling. An optional note in the Pi install guide is enough: "To flash an ESP32 from the Pi
run `sh scripts/flash.sh`" (a Pi can run esptool, but it is a poor place to build).

esptool is pinned to the 5.x series (`>=5,<6`, hyphenated command names). Change `ESPTOOL_SPEC` in
`scripts/flash_tool/toolenv.py` if a later major version changes the commands.

## Troubleshooting

* No port appears: use a data cable; Windows may need the CP210x or CH340/CH9102 driver (menu 6 explains).
* Linux "permission denied": `sudo usermod -a -G dialout $USER`, then log out and in again.
* Chip not detected: hold BOOT while plugging in; close any serial monitor that holds the port.
* Strings: all text lives in one dict at the top of `scripts/flash_tool/strings.py`; a Swedish dict can be added
  there.

# Firmware variants, pins and host link

One shared source set (`firmware/esp32s3/src`, logic in `firmware/lib/hostcore` and `firmware/lib/meshcore`) builds for
three chips. The `esp32c3` and `esp32` projects only hold a `platformio.ini` that points `src_dir` at the shared sources.

**Status: verified compiled only.** All variants build with PlatformIO (see sizes below) and the native tests pass
(`firmware/test/native`). Nothing has been flashed or run on a real board: pins, buttons, radio, boot behaviour and the
UART link are not verified on hardware.

> **Hardware note (2026-10-04):** the ESP32-C3 Super Mini builds set `-DRADIO_TX_POWER_QDBM=34` (8.5 dBm). At full power the
> board was heard by a WROOM-32D but could not be heard back. `-DRADIO_DEBUG` adds serial debug lines (rx type, PAIR_REQ sends).

> **Button defaults (2026-10-04):** the remote function is on and the four buttons send 1 start/next, 2 pause, 3 stop end, 4 emergency
> out of the box (`$C,remote` / `$C,btn1..4` override them). What a paired remote may actually do is decided by the master's rights page.

## Variants

| Chip | Board | Env | Folder | When to use |
| --- | --- | --- | --- | --- |
| ESP32-S3 | `esp32-s3-devkitc-1` | `esp32-s3-devkitc-1` | `firmware/esp32s3` | Reference board, native USB, host (Pi/PC) attached |
| ESP32-S3 | `esp32-s3-devkitc-1` | `esp32-s3-standalone` | `firmware/esp32s3` | Light/sound box with no host (default mode follow) |
| ESP32-C3 | Super Mini (`esp32-c3-devkitm-1`) | `esp32c3-supermini` | `firmware/esp32c3` | Small, cheap, native USB, host attached |
| ESP32-C3 | Super Mini | `esp32c3-standalone` | `firmware/esp32c3` | Stand-alone box |
| ESP32 classic (WROOM-32D) | `esp32dev` | `esp32-wroom-32d` | `firmware/esp32` | DevKit with USB-UART bridge (CP2102 / CH340 / CH9102), host attached |
| ESP32 classic (WROOM-32D) | `esp32dev` | `esp32-wroom-32d-standalone` | `firmware/esp32` | Stand-alone box |

Build: `cd firmware/<folder>; pio run -e <env>`. Stand-alone envs add `-DESPNOW_DEFAULT_MODE=2` (follow) and need a mesh
key (`$C,mkey` over serial, or pairing). Common flags (`ESPNOW_CHANNEL`, `MESHCORE_EXTERNAL_HMAC`, `PIN_*`, `PIN_BEEP`,
`BEEP_HZ`, `BOOT_CHIME`) are listed at the top of `firmware/esp32s3/platformio.ini`.

Compiled sizes (PlatformIO, core as installed in this session):

| Env | Flash | RAM (static) |
| --- | --- | --- |
| `esp32-s3-devkitc-1` | 721,941 B (21.6 % of 3.3 MB) | 53,656 B (16.4 %) |
| `esp32c3-supermini` | 753,918 B (57.5 % of 1.25 MB) | 47,972 B (14.6 %) |
| `esp32-wroom-32d` (and `-standalone`) | 774,825 B (59.1 % of 1.25 MB) | 53,952 B (16.5 %) |

## Pin maps

All pins are overridable with `-DPIN_xxx=n` in the env. Lights and horn are active HIGH; buttons go to GND (internal
pull-up); the beeper is PWM.

| Function | S3 (defaults in the code) | C3 Super Mini | WROOM-32D |
| --- | --- | --- | --- |
| Green | GPIO4 | GPIO0 | GPIO25 |
| Yellow | GPIO5 | GPIO1 | GPIO26 |
| Red | GPIO6 | GPIO3 | GPIO27 |
| Horn | GPIO7 | GPIO4 | GPIO32 |
| Fault LED | GPIO8 (active HIGH) | GPIO8 (on-board, active LOW) | GPIO2 (on-board, active HIGH) |
| Buttons 1-4 | GPIO9, 10, 11, 12 | GPIO5, 6, 7, 10 | GPIO13, 14, 16, 17 |
| PWM beeper | none (`-DPIN_BEEP=n`) | GPIO21 | GPIO23 |
| Host link | native USB (GPIO19/20) | native USB (GPIO18/19) | UART0 GPIO1 TX / GPIO3 RX via the bridge |

Avoided on purpose:
- S3: nothing special beyond the USB pins GPIO19/20 and the boot strapping pins (0, 3, 45, 46).
- C3: strapping pins GPIO2/8/9 (GPIO8 only drives the LED), USB pins GPIO18/19.
- WROOM-32D: flash pins GPIO6-11, input-only GPIO34-39 (no outputs, no pull-ups), strapping pins GPIO0/5/12/15
  (GPIO2 is used only for the on-board fault LED, which is harmless at boot), UART0 pins GPIO1/3. GPIO16/17 are free
  on WROOM but taken by PSRAM on WROVER modules: use other pins there.

## Wiring cautions

- **Lamps and horn need a driver stage** (transistor, logic-level MOSFET or relay board with flyback protection). A GPIO
  gives a few mA to about 12 mA at 3.3 V and must never drive lamps, a mains relay coil or a horn directly.
- Put a pull-down (about 10 kOhm) on each light and horn output so the lamps are off (not floating) while the chip
  boots. Lights default to RED once the firmware runs; during the first moments of boot pins float.
- Buttons: switch between the pin and GND, no external resistor needed. Keep wires short or add 100 nF at long runs.
- Fault LED: a small series resistor if you use an external LED.
- Power the board from a stable 5 V supply; a Pi USB port is fine for one board without lamps.

## How the host links

The host core finds the board by USB VID/PID (`hardware/discovery.py`) and speaks serial protocol v1/v2
(`docs/protocol.md`) at 115200 baud.

- **Native USB (S3, C3):** the chip is its own USB device (VID 303A). Built with `ARDUINO_USB_MODE=1` and
  `ARDUINO_USB_CDC_ON_BOOT=1`; transmit never blocks when no host is attached (`setTxTimeoutMs(0)`). Lowest latency.
  These devices are tried first.
- **USB-UART bridge (classic ESP32 DevKit):** the board shows up as a bridge chip: Silicon Labs CP210x `10C4:EA60`,
  WCH CH340 `1A86:7523`, WCH CH9102 `1A86:55D4`, FTDI `0403:6001`. They are tried after native-USB devices. The
  firmware uses UART0 at 115200 (no USB flags); RX and TX buffers are enlarged to 1 KB. For FTDI chips set the
  latency timer to 1 ms. A bridge adds roughly 1-2 ms of latency compared with native USB (not measured here).
- **DTR/RTS reset caveat:** most DevKits wire the bridge's DTR and RTS to EN and GPIO0, so a normal port open can
  reset the board (and a core restart would then drop the lights for about a second). The host therefore opens bridge
  ports with `dtr=False, rts=False` set before the open call (`open_serial(..., bridge=True)`). The raise-then-lower at
  the OS open on Linux is a "both high to both low" transition, which the standard auto-reset circuit ignores. Flashing
  tools (esptool, PlatformIO) still use DTR/RTS deliberately; close the core before flashing.
- **Boot noise on UART0:** the ROM bootloader prints a text banner on UART0 at power-up and at every reset. The host
  frame parser drops anything that is not a valid frame, and the firmware also restarts its line at a `$`, so a banner
  without a final newline cannot swallow the first frame. A board that is still booting when the host connects misses
  the first hello; the worker's reconnect backoff (0.2 to 2 s) plus its 0.5 s hello wait cover the boot of about 1 s.
- **Stand-alone boxes with no host:** UART0 drains into the pins whether or not anything listens, so the firmware
  never blocks for good on a print (a burst may wait for the 1 KB TX buffer to drain, a few ms at most).

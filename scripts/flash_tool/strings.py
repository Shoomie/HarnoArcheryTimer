"""All user-facing text of the flashing menu, in one place (a Swedish dict can be added next to EN)."""

from __future__ import annotations

EN: dict[str, str] = {
    "title": "Archery timer - module flashing",
    "menu.header": "What do you want to do?",
    "menu.flash": "Flash a module (normal way)",
    "menu.build": "Build from source and flash (advanced)",
    "menu.release": "Create release images (developer)",
    "menu.monitor": "Open serial monitor",
    "menu.erase": "Erase a module",
    "menu.check": "Check this computer",
    "menu.installed": "Show what is installed",
    "menu.remove": "Remove the tool environment",
    "menu.quit": "Quit",
    "menu.prompt": "Type a number and press Enter: ",
    "menu.invalid": "That is not one of the choices.",
    "choose.prompt": "Your choice (number, empty = cancel): ",
    "cancelled": "Cancelled. Nothing was changed.",
    "yesno.no_default": "[y/N]",
    "yesno.yes_default": "[Y/n]",
    # tool environment
    "boot.esptool": (
        "The flashing tool (esptool, a few MB, from the Python package index) is not installed yet.\n"
        "It will be installed ONLY inside this folder: {dir}\n"
        "Nothing else on this computer is changed."
    ),
    "boot.esptool.ask": "Download and install it now?",
    "boot.creating": "Creating the tool environment...",
    "boot.installing": "Installing {what}...",
    "boot.failed": "The installation failed (see the messages above). Check the internet connection.",
    "boot.declined": "Without the tool this cannot continue.",
    "boot.pio": (
        "PlatformIO (the firmware compiler) is not installed. It is only needed to BUILD firmware.\n"
        "It downloads about 1 GB of toolchains and needs a few GB of free disk.\n"
        "The program is installed inside: {dir}\n"
        "Volunteers normally do not need this: use 'Flash a module' with the ready-made images."
    ),
    "boot.pio.need_flag": "--yes does not approve the 1 GB PlatformIO download. Add --install-pio to allow it.",
    "boot.pio.ask": "Download and install PlatformIO now?",
    "boot.pio.coredir": "PlatformIO files (the 1 GB) will be kept in {core}",
    "boot.pio.short": (
        "(A short folder is used because the project path is long and the compiler\n"
        " fails on Windows paths over 260 characters.)"
    ),
    "boot.pio.override": "Using the PlatformIO program given by FLASH_PIO: {path}",
    # ports
    "ports.none": (
        "No serial ports found. Plug in the module with a USB DATA cable (not a charge-only cable)\n"
        "and try again. Choose 'Check this computer' for driver hints."
    ),
    "ports.header": "Connected serial ports:",
    "ports.line": "  {n}. {device}  [{usb}]  {desc}  -> looks like: {guess}",
    "ports.choose": "Which port is the module on? ",
    "ports.unknown": "The port {port} was not found among the connected ports.",
    "ports.need": "No port given: use --port in non-interactive mode.",
    "guess.espressif": "ESP32-S3 or ESP32-C3 with built-in USB",
    "guess.cp210x": "ESP32 board with a CP210x USB chip",
    "guess.ch340": "ESP32 board with a CH340/CH9102 USB chip",
    "guess.ftdi": "board with an FTDI USB chip",
    "guess.unknown": "unknown device",
    # detect / variants
    "detect.running": "Asking {port} what chip it is (do not unplug)...",
    "detect.failed": (
        "Could not talk to the chip on {port}.\n"
        "Try: hold the BOOT button on the module while plugging in USB (or press BOOT, tap RESET,\n"
        "release BOOT), then run this again. Also check the cable and that no other program\n"
        "(for example a serial monitor) is using the port."
    ),
    "detect.found": "Found chip: {chip}",
    "variants.header": "Firmware versions that fit this chip:",
    "variants.line": "  {n}. {env}\n       {title}: {desc}",
    "variants.choose": "Which one? ",
    "variants.none": "No firmware variant is known for chip {chip}.",
    "variants.unknown_env": "Unknown firmware variant '{env}'. Known: {known}",
    "variants.mismatch": (
        "Firmware '{env}' is for a {want}, but the module on {port} is a {chip}. Not writing."
    ),
    "v.esp32-s3-devkitc-1.title": "Normal box (ESP32-S3)",
    "v.esp32-s3-standalone.title": "Stand-alone box (ESP32-S3)",
    "v.esp32c3-supermini.title": "Normal box (ESP32-C3 Super Mini)",
    "v.esp32c3-standalone.title": "Stand-alone box (ESP32-C3 Super Mini)",
    "v.esp32-wroom-32d.title": "Normal box (ESP32-WROOM-32D)",
    "v.esp32-wroom-32d-standalone.title": "Stand-alone box (ESP32-WROOM-32D)",
    "desc.normal": "normal box: plugged into the timer computer",
    "desc.standalone": "stand-alone box: follows the radio, e.g. on a USB charger",
    # flashing
    "image.missing": (
        "The ready-made image {image} does not exist.\n"
        "Get the 'firmware/release' folder from the project download, or (developer) create the\n"
        "images with the menu entry 'Create release images'."
    ),
    "image.offer_build": "PlatformIO is installed. Build this firmware from source and flash it instead?",
    "image.bad_sha": (
        "The image {image} does not match firmware/release/manifest.json "
        "(damaged or changed). Not writing."
    ),
    "flash.confirm": (
        "About to write\n"
        "   image : {image} ({size} bytes, version {version})\n"
        "   to    : {port}  (chip {chip})\n"
        "ALL firmware and settings stored on that module will be replaced."
    ),
    "flash.ask": "Write it to {port} now?",
    "flash.writing": "Writing... (about a minute, do not unplug)",
    "flash.verifying": "Checking what was written...",
    "flash.ok": "Done. The module was written and checked. It restarts by itself (replug USB if not).",
    "flash.verify_note": "The extra check differs, which is normal once the module has started and saved its own settings. The write itself was verified.",
    "flash.failed": "Writing failed (see the messages above). Try again or use another cable.",
    "build.writing": "Building from source and uploading to {port}... (the first build takes minutes)",
    "build.confirm": "About to BUILD '{env}' from source and write it to {port} (chip {chip}).",
    "build.nofolder": "The firmware folder {folder} does not exist in this project.",
    # release
    "release.nopio": "PlatformIO is needed to create release images.",
    "release.building": "Building {env}...",
    "release.merging": "Merging {env} into one image...",
    "release.skip": "Skipping {env}: {why}",
    "release.missing_art": "build output missing: {path}",
    "release.done": "Created {n} image(s) in {dir}",
    "release.failed": "Failed: {env}",
    "release.commit": "Remember to commit firmware/release/ whenever the firmware changes.",
    # monitor / erase
    "monitor.start": "Serial monitor on {port} at 115200. Press Ctrl+C to leave.",
    "erase.confirm": (
        "About to ERASE everything on the module at {port}. "
        "It does nothing until it is flashed again."
    ),
    "erase.ask": "Erase {port}?",
    "erase.ok": "Erased. Flash the module again before using it.",
    "erase.failed": "Erasing failed (see the messages above).",
    # check
    "check.header": "Check of this computer",
    "check.python": "Python: {version} ({exe})",
    "check.python.old": "  Python 3.9 or newer is needed. Please install a newer Python.",
    "check.venv.ok": "Python can create the tool environment.",
    "check.venv.bad": (
        "Python cannot create virtual environments. "
        "On Debian/Ubuntu/Pi OS run: sudo apt install python3-venv"
    ),
    "check.os": "System: {system}",
    "check.hint.windows": (
        "Windows: if the module does not appear as a COM port, install the USB driver for the chip on\n"
        "  the board: CP210x (Silicon Labs) or CH340/CH9102 (WCH). ESP32-S3/C3 with built-in USB need none.\n"
        "  Use a USB DATA cable. Look under 'Ports (COM & LPT)' in Device Manager."
    ),
    "check.hint.linux": (
        "Linux: your user needs permission for serial ports: sudo usermod -a -G dialout $USER\n"
        "  then log out and in again (on some systems the group is 'uucp')."
    ),
    "check.hint.macos": (
        "macOS: CP210x/CH340 boards may need the vendor driver; ESP32-S3/C3 with built-in USB need none.\n"
        "  Ports are called /dev/cu.usbmodem* or /dev/cu.usbserial*."
    ),
    "check.group.ok": "You are in a group that may use serial ports ({groups}).",
    "check.group.bad": (
        "You are NOT in the dialout/uucp group: serial ports will probably say 'permission denied'."
    ),
    "check.ports.noenv": "Serial ports: not listed yet (the tool environment is installed on first use).",
    "check.ports.n": "Serial ports found: {n}",
    "check.tools": "Tool environment: {state}",
    "check.images": "Ready-made images: {n} in firmware/release",
    "state.absent": "not installed",
    "state.present": "installed",
    # installed / remove
    "inst.header": "What is installed",
    "inst.dir": "Tool environment folder: {dir}",
    "inst.esptool": "esptool: {version}",
    "inst.pio": "PlatformIO: {version}",
    "inst.pio.none": "PlatformIO: not installed",
    "inst.core": "PlatformIO files: {core}",
    "inst.none": "Nothing is installed yet (it is created the first time you flash).",
    "inst.images": "Images in firmware/release:",
    "inst.image": "  {env}  {chip}  version {version}  {size} bytes  built {built}",
    "inst.noimages": "No ready-made images yet.",
    "remove.ask": "Delete the tool environment {dir}? It is downloaded again when needed.",
    "remove.ok": "Removed.",
    "remove.none": "There is nothing to remove.",
    "remove.core.ask": "Also delete the PlatformIO files in {core} (about 1 GB)?",
    # misc
    "err.python": "Python 3.9 or newer is required.",
    "err.need_env": "Give --env (firmware variant) in non-interactive mode.",
}

S = EN


def t(key: str, **kw: object) -> str:
    """Look up a text and fill in the placeholders."""
    text = S[key]
    return text.format(**kw) if kw else text

# Install on Windows 10/11

[Svenska](windows.sv.md) · [Linux](linux.md) · [Raspberry Pi](raspberry-pi.md) · [Back to README](../../README.md)

Time needed: about 10 minutes. You need an internet connection for the first setup only.

## 1. Install Python

1. Go to <https://www.python.org/downloads/> and download the latest Python 3 (3.9 or newer).
2. Run the installer. **Tick "Add python.exe to PATH"** on the first screen, then press *Install Now*.

## 2. Download the project

Choose one:

- **ZIP (easiest):** on the GitHub page press **Code → Download ZIP**, then right-click the file and
  *Extract All*. Put the folder somewhere simple, for example `C:\ArcheryTimer`.
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. Set up (once)

Open the project folder and **double-click `scripts\setup_windows.bat`**. It creates a private Python
environment in `.venv` and installs what the timer needs. Wait for "Done".

If Windows SmartScreen warns about the file, choose *More info → Run anyway* (it is a plain text script you can
read in Notepad).

## 4. Start the timer

Double-click **`scripts\start_windows.bat`**. A window with the timer opens.

- No lights hardware yet? Start it from a terminal as `scripts\start_windows.bat --no-serial` for a demo.
- Fullscreen on a TV: `scripts\start_windows.bat -- --fullscreen`
- English interface: `scripts\start_windows.bat -- --lang en`
- Second monitor for the audience, no controls: `scripts\start_windows.bat -- --profile audience --display 1`

(To make a desktop shortcut: right-click `start_windows.bat` → *Send to → Desktop (create shortcut)*.)

Keys: **Space** = the big button, **P** = pause, **Esc** = emergency stop. See the
[README](../../README.md#controls).

## 5. Connect the lights and horn (optional)

Plug the ESP32 board into a USB port. The program finds it automatically. If it does not:

1. Open *Device Manager → Ports (COM & LPT)* and note the port, for example `COM7`.
2. Start with `scripts\start_windows.bat --serial-port COM7`.

Some cheap boards need a USB-serial driver (CH340 or CP210x); if no COM port appears, install the driver from
the chip maker. The board firmware is in [`firmware/`](../../firmware/); flash a new board with the [flashing guide](../flashing.md).

## Update

Download the new ZIP (or `git pull`) and run `scripts\setup_windows.bat` again. Your settings are kept in your
user profile (`%LOCALAPPDATA%\archerytimer`), not in the project folder.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| "Python was not found" | Reinstall Python and tick *Add python.exe to PATH*, or run the setup again after restarting the PC |
| Window opens, then closes | Run `scripts\start_windows.bat` from a terminal (`cmd`) to see the error message |
| Hardware status says "no lights" | Check the USB cable (it must carry data), port, driver; see step 5 |
| Logs | `%LOCALAPPDATA%\archerytimer\logs` (open it by pasting the path in File Explorer) |

# Install on a Raspberry Pi (TV kiosk)

[Svenska](raspberry-pi.sv.md) · [Windows](windows.md) · [Linux](linux.md) · [Back to README](../../README.md)

Result: the Pi boots straight into the timer on the TV, with no keyboard login. The timer core runs as a
background service and keeps lights and sound going even if the display program restarts.

**Tested target:** Raspberry Pi 2 Model B, Raspberry Pi OS Lite 32-bit (Trixie), HDMI TV. Other Pi models should
work but are untested. Time needed: about 30 minutes.

> The installer has been run on a real Pi 2B once (the display works). Audio, GPIO buttons and the USB hardware
> have not been tested on a Pi yet. See [deployment.md](../deployment.md) for what is verified.

## What you need

- Raspberry Pi with power supply, microSD card (8 GB or more), HDMI cable and a TV or monitor
- A computer to prepare the card, and a network connection for the Pi (cable is easiest) during installation
- Optional: the ESP32 lights/horn board on a USB port, a USB keyboard or clicker

## 1. Write the operating system to the card

1. On your computer install **Raspberry Pi Imager** from <https://www.raspberrypi.com/software/>.
2. Choose your Pi model, then *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***.
3. Choose the SD card, press *Next*, then *Edit settings* (OS customisation) and set:
   - a **hostname** (for example `archerytimer`) and a **username and password** (remember them; this user
     becomes the kiosk user),
   - your **Wi-Fi** if you do not use a cable, and your time zone,
   - *Services → Enable SSH*.
4. Write the card, put it in the Pi, connect HDMI and network, and power it on. Wait a couple of minutes for the
   first boot.

## 2. Log in

From your computer (Windows 10/11 and Linux both have `ssh`):

```bash
ssh <username>@archerytimer.local
```

(If the name is not found, use the Pi's IP address from your router.) Alternatively connect a keyboard to the
Pi and log in on the TV.

## 3. Download the project

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. Run the installer

```bash
sudo bash scripts/install_pi.sh
```

This takes several minutes. It installs the needed packages, copies the program to `/opt/archerytimer`, sets up
the background service, enables the GPU display overlay, and makes the Pi log in automatically on the first
console and start the timer there. When it finishes, reboot:

```bash
sudo reboot
```

After the reboot the timer appears on the TV by itself. Use the mouse or keyboard (Space = big button,
Esc = emergency stop).

Options: `--no-ui` for a lights/sound-only box without a display, `--user NAME` to pick the kiosk user. Run
`scripts/install_pi.sh --help` for the list.

## 5. Connect the lights and horn (optional)

Plug the ESP32 board into a USB port on the Pi. It is found automatically (the kiosk user is already in the
`dialout` group). The status is shown in the program's hardware menu. The firmware in
[`firmware/`](../../firmware/) has **not been tested on real hardware yet**.

## Settings

Extra start options live in two small files. Edit them with `sudo nano`:

| File | Used for | Example |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | the background core | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | the display | `UI_ARGS="--lang en --profile audience"` |

Apply after editing: `sudo systemctl restart archerytimer-core` and reboot (or log out of the console) for the
display. Running several Pis together (one leader, followers): see [cluster.md](../cluster.md).

## Update

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

Your settings and the files in `/etc/archerytimer` are kept.

**From a Windows computer**, without git on the Pi: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(copies the project, runs the installer; add `-Reboot` to restart afterwards).

## Getting a normal shell on the TV

The kiosk takes over the Pi's first console. To work on the Pi itself, log in over **SSH** from another computer,
or create the file `~/.no-kiosk` (`touch ~/.no-kiosk`) and reboot to get an ordinary prompt. Delete the file and
reboot to get the timer back.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Black screen after reboot | Wait 1-2 minutes after power-on. Check HDMI. If it persists, log in by SSH and run `journalctl -u archerytimer-core -n 50` and look at `~/.local/share/archerytimer/logs/ui.log` |
| Screen stays black only if the TV is switched on after the Pi | Add `hdmi_force_hotplug=1` to `/boot/firmware/config.txt`, reboot |
| Display works but "no connection to core" | `systemctl status archerytimer-core`; restart it with `sudo systemctl restart archerytimer-core` |
| No lights/horn | Check the USB cable carries data; `ls /dev/ttyACM* /dev/ttyUSB*` should show a device |
| Check the environment | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| Remove everything | `sudo bash scripts/uninstall_pi.sh` (keeps your settings) |

Live logs: `journalctl -u archerytimer-core -f`. More internals: [deployment.md](../deployment.md).

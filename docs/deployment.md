# Raspberry Pi deployment (M8)

Target: Pi 2 Model B, Raspberry Pi OS Lite 32-bit, no X11. Two services run as the kiosk user (the one who ran `sudo`; the unit files name `archery` as a template). Step-by-step guide: [install/raspberry-pi.md](install/raspberry-pi.md).



| Unit | Runs | Notes |
| --- | --- | --- |
| `archerytimer-core.service` | `python -m archerytimer.core_service $CORE_ARGS` | Headless. `SDL_VIDEODRIVER=dummy`, ALSA audio, `CAP_SYS_NICE` for the priority boost. SIGTERM goes RED and silent first. `Restart=always`. |
| `archerytimer-ui.service` | `python -m archerytimer.ui_client --fullscreen $UI_ARGS` | KMSDRM kiosk on tty1 (logind session via `PAMName=login`). Wants, not requires, the core: a UI crash or core restart never stops the other. |

## Install

Copy the repository to the Pi, then:

```bash
sudo scripts/install_pi.sh            # --no-ui for a lights/sound-only node, --pygame apt|pip to force a source
```

It installs apt packages, creates the `archery` user (groups dialout, audio, video, render, input, gpio), syncs
the code to `/opt/archerytimer`, builds `/opt/archerytimer/.venv` (editable install: the app finds `config/`,
`locales/` and `assets/` relative to the source tree), installs the units and a journald size limit, and starts
both services. pygame: tries the pip wheel, falls back to apt `python3-pygame` (answers the open question once
you run `scripts/env_probe.py` on the Pi and record the result). Re-running updates code and units and keeps
`/etc/archerytimer/*.env` and user data.

## Configuration

- `/etc/archerytimer/core.env`: `CORE_ARGS`, e.g. `--leader 192.168.1.10` (follower), `--host 0.0.0.0`, `--no-audio`.
- `/etc/archerytimer/ui.env`: `UI_ARGS`, e.g. `--profile audience`, `--host <core ip>`, `--display 1`.
- Apply with `sudo systemctl restart archerytimer-core archerytimer-ui`.

## Boot settings (manual, once)

In `/boot/firmware/config.txt`: `dtoverlay=vc4-kms-v3d` (KMSDRM needs it), set `hdmi_force_hotplug=1` if the TV
is switched on after the Pi. In `/boot/firmware/cmdline.txt` add `consoleblank=0 vt.global_cursor_default=0 quiet`.
Disable unused services (`bluetooth`, `triggerhappy`) if boot time or jitter matters.

## Logs and checks

- App logs: `~archery/.local/share/archerytimer/logs/{core,ui}.log` (rotating, 5 x 1 MB each).
- Journal: `journalctl -u archerytimer-core -u archerytimer-ui -f` (capped at 100 MB, 2 weeks).
- Probe: `sudo -u archery /opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py`.
- Remove: `sudo scripts/uninstall_pi.sh` (keeps `/etc/archerytimer`, the user and its data).

## Not verified

None of this has run on a real Pi: KMSDRM start under `PAMName=login`, the pip-vs-apt pygame choice, ALSA device
names, GPIO group access and boot settings are untested. `tests/deploy/` only checks the files statically.

## Kiosk user and UI start (console mode, default)

`install_pi.sh` uses the user who ran `sudo` (or `--user NAME`) as the permanent kiosk user: the core service runs as
that user, tty1 autologins as that user (`getty@tty1` drop-in) and its `~/.profile` (or `.bash_profile`) execs
`scripts/run_ui_tty1.sh`, which restarts the UI if it exits. This gives KMSDRM a real login session (DRM master) on
tty1 and avoids the systemd/getty fight. It also installs libgbm/libegl/libgles/mesa, uses apt `python3-pygame`, adds the
user to video/render/input/tty/audio/dialout/gpio and enables `dtoverlay=vc4-kms-v3d` if missing (reboot afterwards).
Escape hatch: `touch ~/.no-kiosk` (or use SSH) for a normal shell on tty1. `--ui-mode service` installs the old
`archerytimer-ui.service` instead.

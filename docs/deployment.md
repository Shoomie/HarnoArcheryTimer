# Raspberry Pi deployment

Target: Pi 2 Model B, Raspberry Pi OS Lite 32-bit, no X11. Step-by-step guide: [install/raspberry-pi.md](install/raspberry-pi.md). This page is the reference for what the installer sets up.

## What the installer does

`sudo bash scripts/install_pi.sh` (options: `--no-ui` for a lights/sound-only node, `--user NAME`, `--pygame apt|pip`, `--ui-mode service`):

- installs apt packages (including libgbm/libegl/libgles/mesa for KMSDRM and apt `python3-pygame`; in `auto` mode it checks that
  SDL has KMSDRM and swaps the pip pygame for apt's if not),
- syncs the code to `/opt/archerytimer` and builds `/opt/archerytimer/.venv` (editable install: the app finds `config/`,
  `locales/` and `assets/` next to the source),
- makes the user who ran `sudo` (or `--user`) the **kiosk user**: adds them to video/render/input/tty/audio/dialout/gpio, runs the
  core service as them, autologins them on tty1 (`getty@tty1` drop-in) and has their `~/.profile` exec `scripts/run_ui_tty1.sh`,
  which restarts the UI if it exits. This gives KMSDRM a real login session (DRM master) on tty1,
- installs the core unit and a journald size limit, enables `dtoverlay=vc4-kms-v3d` if missing, and starts the core.

Re-running updates code and units and keeps `/etc/archerytimer/*.env` and user data. Reboot after the first run.
`touch ~/.no-kiosk` (or use SSH) gives a normal shell on tty1; `--ui-mode service` installs `archerytimer-ui.service` instead of the console start.

From Windows: `scripts/deploy_to_pi.ps1 -Pi user@host [-Reboot]` copies the project and runs the installer.

## Units

| Unit | Runs | Notes |
| --- | --- | --- |
| `archerytimer-core.service` | `python -m archerytimer.core_service $CORE_ARGS` | Headless. `SDL_VIDEODRIVER=dummy`, ALSA audio, `CAP_SYS_NICE` for the priority boost. SIGTERM goes RED and silent first. `Restart=always`. |
| `archerytimer-ui.service` | `python -m archerytimer.ui_client --fullscreen $UI_ARGS` | Only with `--ui-mode service`. Wants, not requires, the core: a UI crash or core restart never stops the other. |

The UI forces `SDL_RENDER_DRIVER=opengles2` (the Pi's GLES context; SDL's default desktop-GL choice gives a black screen).

## Configuration

- `/etc/archerytimer/core.env`: `CORE_ARGS`, e.g. `--leader 192.168.1.10` (follower), `--host 0.0.0.0`, `--no-audio`.
- `/etc/archerytimer/ui.env`: `UI_ARGS`, e.g. `--profile audience`, `--host <core ip>`, `--display 1`.
- Apply with `sudo systemctl restart archerytimer-core` (and restart the UI or reboot).

## Boot settings

`/boot/firmware/config.txt`: `dtoverlay=vc4-kms-v3d` (the installer adds it); add `hdmi_force_hotplug=1` if the TV is switched on
after the Pi. `/boot/firmware/cmdline.txt`: `consoleblank=0 vt.global_cursor_default=0 quiet` keeps the screen on and quiet.
Disable unused services (`bluetooth`, `triggerhappy`) if boot time or jitter matters.

## Logs and checks

- App logs: `~/.local/share/archerytimer/logs/{core,ui}.log` of the kiosk user (rotating, 5 x 1 MB each).
- Journal: `journalctl -u archerytimer-core -f` (capped at 100 MB and 2 weeks).
- Probe: `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py`.
- Tune painting: `scripts/profile_paint.py`.
- Remove: `sudo bash scripts/uninstall_pi.sh` (keeps `/etc/archerytimer`, the user and its data).

## Rendering on the Pi

CPU painting per pixel is slow on a Pi 2B, so everything that ticks is a GPU **overlay** (`set_overlay`: glyph textures and
rectangles for the countdown, clock, progress bar, light field, icons, frames, hover images, menu banner). Section pictures
repaint only on real changes.

## Checked by tests

`tests/deploy/` checks the units, env files and scripts statically (bash syntax tests skip on Windows).

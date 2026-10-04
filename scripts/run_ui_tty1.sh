#!/usr/bin/env bash
# Kiosk UI launcher, started from the login profile on tty1 (see install_pi.sh).
# Restarts the UI if it exits. To get a normal shell on tty1: touch ~/.no-kiosk (or log in over SSH).
APP_DIR=/opt/archerytimer
[ -f "$HOME/.no-kiosk" ] && exit 0
UI_ARGS=""
[ -f /etc/archerytimer/ui.env ] && . /etc/archerytimer/ui.env
export SDL_VIDEODRIVER=kmsdrm SDL_RENDER_DRIVER=opengles2 SDL_AUDIODRIVER=dummy PYTHONUNBUFFERED=1 PYGAME_HIDE_SUPPORT_PROMPT=1
cd "$APP_DIR" || exit 1
while [ ! -f "$HOME/.no-kiosk" ]; do
    # shellcheck disable=SC2086
    "$APP_DIR/.venv/bin/python" -m archerytimer.ui_client --fullscreen $UI_ARGS
    sleep 1
done

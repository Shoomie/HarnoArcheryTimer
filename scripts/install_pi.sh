#!/usr/bin/env bash
# Install the archery timer on Raspberry Pi OS Lite (needs sudo). Run from the repo root:
#   sudo scripts/install_pi.sh [--no-ui] [--user NAME] [--ui-mode console|service] [--pygame pip|apt] [--no-enable]
# The user who runs sudo (or --user) becomes the permanent kiosk user: the core runs as that user, tty1
# autologins as that user and starts the UI (console mode, default; best for KMSDRM).
# Re-running updates the code and units; /etc/archerytimer/*.env and user data are kept.
set -euo pipefail

APP_DIR=/opt/archerytimer
CONF_DIR=/etc/archerytimer
USER_NAME="${SUDO_USER:-}"
UI_MODE=console
UI=1
ENABLE=1
PYGAME=apt  # Debian's python3-pygame has KMSDRM+EGL; pip wheels lack it on armv7

while [ $# -gt 0 ]; do
    case "$1" in
        --no-ui) UI=0 ;;
        --user) USER_NAME="${2:?user name}"; shift ;;
        --ui-mode) UI_MODE="${2:?console or service}"; shift ;;
        --no-enable) ENABLE=0 ;;
        --pygame) PYGAME="${2:?pip or apt}"; shift ;;
        -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
[ -n "$USER_NAME" ] && [ "$USER_NAME" != root ] || { echo "run with sudo from a normal user, or pass --user NAME" >&2; exit 1; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "user $USER_NAME does not exist" >&2; exit 1; }
case "$UI_MODE" in console|service) ;; *) echo "--ui-mode must be console or service" >&2; exit 2 ;; esac
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
echo "kiosk user: $USER_NAME ($USER_HOME)"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$SRC/pyproject.toml" ] || { echo "run from the repository" >&2; exit 1; }

echo "== packages"
apt-get update
apt-get install -y python3 python3-venv python3-pip rsync alsa-utils libsdl2-2.0-0 libsdl2-mixer-2.0-0 libdrm2 \
    libgbm1 libegl1 libgles2 libgl1-mesa-dri python3-pygame

echo "== user and groups"
for g in dialout audio video render input tty plugdev gpio spi i2c; do
    getent group "$g" >/dev/null && usermod -aG "$g" "$USER_NAME"
done

echo "== graphics (KMS overlay, GPU memory)"
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
if [ -f "$CFG" ] && [ "$UI" -eq 1 ]; then
    if ! grep -Eq '^[[:space:]]*dtoverlay=vc4-(f)?kms-v3d' "$CFG"; then
        cp -n "$CFG" "$CFG.archerytimer.bak"
        printf '
# added by archerytimer install
dtoverlay=vc4-kms-v3d
' >> "$CFG"
        echo "enabled dtoverlay=vc4-kms-v3d in $CFG (reboot needed)"
        REBOOT=1
    fi
    if grep -Eq '^[[:space:]]*dtoverlay=vc4-fkms-v3d' "$CFG"; then
        echo "WARNING: $CFG uses vc4-fkms-v3d; KMSDRM needs vc4-kms-v3d. Change it and reboot." >&2
    fi
fi
REBOOT="${REBOOT:-0}"

echo "== code to $APP_DIR"
mkdir -p "$APP_DIR"
if [ "$SRC" != "$APP_DIR" ]; then
    rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
        --exclude '*.egg-info' --exclude 'firmware' --exclude 'docs/results' "$SRC/" "$APP_DIR/"
fi

echo "== python environment"
install_pygame_apt() {
    apt-get install -y python3-pygame
    "$APP_DIR/.venv/bin/pip" install --no-deps -e "$APP_DIR"
    "$APP_DIR/.venv/bin/pip" install pyserial platformdirs
}
# System site packages so the apt pygame (fallback) is visible; pip packages win otherwise.
python3 -m venv --system-site-packages "$APP_DIR/.venv"
case "$PYGAME" in
    apt) install_pygame_apt ;;
    pip) "$APP_DIR/.venv/bin/pip" install -e "$APP_DIR" ;;
    auto)
        if ! "$APP_DIR/.venv/bin/pip" install -e "$APP_DIR"; then
            echo "pip install failed, falling back to apt python3-pygame"
            install_pygame_apt
        fi ;;
    *) echo "--pygame must be pip or apt" >&2; exit 2 ;;
esac
"$APP_DIR/.venv/bin/python" -c "import pygame, serial, platformdirs; print('pygame', pygame.version.ver)"

# The pip wheel's bundled SDL often lacks KMSDRM (black screen on a Lite kiosk). Verify it, and
# switch to the Debian build if it fails.
kmsdrm_ok() {
    # SDL says "kmsdrm not available" when the driver is not compiled in. Any other failure
    # (no display, DRM busy over SSH) says nothing about the build, so it counts as fine here.
    local out
    out=$(SDL_VIDEODRIVER=kmsdrm SDL_AUDIODRIVER=dummy "$APP_DIR/.venv/bin/python" -c         "import pygame; pygame.display.init()" 2>&1 || true)
    ! printf '%s' "$out" | grep -qi "not available"
}
if [ "$UI" -eq 1 ]; then
    if kmsdrm_ok; then
        echo "KMSDRM video driver available"
    elif [ "$PYGAME" = "auto" ]; then
        echo "KMSDRM not usable with the pip pygame; switching to apt python3-pygame"
        "$APP_DIR/.venv/bin/pip" uninstall -y pygame-ce pygame >/dev/null 2>&1 || true
        install_pygame_apt
        kmsdrm_ok || echo "WARNING: KMSDRM still not usable from this shell (it may need the tty1 session; run env_probe.py)" >&2
    else
        echo "WARNING: KMSDRM not usable from this shell (it may need the tty1 session; run env_probe.py)" >&2
    fi
fi
chown -R "$USER_NAME:" "$APP_DIR"

echo "== configuration and services"
mkdir -p "$CONF_DIR"
for f in core ui; do
    [ -f "$CONF_DIR/$f.env" ] || install -m 644 "$APP_DIR/scripts/systemd/$f.env.example" "$CONF_DIR/$f.env"
done
install -m 644 "$APP_DIR/scripts/systemd/archerytimer-core.service" /etc/systemd/system/
mkdir -p /etc/systemd/journald.conf.d
install -m 644 "$APP_DIR/scripts/systemd/journald-archerytimer.conf" /etc/systemd/journald.conf.d/archerytimer.conf
# Units are written for user "archery"; run them as the kiosk user instead.
sed -i "s/^User=archery\$/User=$USER_NAME/; s/^Group=archery\$/Group=$USER_NAME/" /etc/systemd/system/archerytimer-core.service
SERVICE_UI=0
if [ "$UI" -eq 1 ] && [ "$UI_MODE" = service ]; then
    install -m 644 "$APP_DIR/scripts/systemd/archerytimer-ui.service" /etc/systemd/system/
    sed -i "s/^User=archery\$/User=$USER_NAME/; s/^Group=archery\$/Group=$USER_NAME/" /etc/systemd/system/archerytimer-ui.service
    SERVICE_UI=1
else
    systemctl disable --now archerytimer-ui.service 2>/dev/null || true
    rm -f /etc/systemd/system/archerytimer-ui.service
fi

if [ "$UI" -eq 1 ] && [ "$UI_MODE" = console ]; then
    echo "== tty1 autologin and UI launcher for $USER_NAME"
    chmod 755 "$APP_DIR/scripts/run_ui_tty1.sh"
    mkdir -p /etc/systemd/system/getty@tty1.service.d
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<UNIT
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER_NAME --noclear %I \$TERM
UNIT
    # The login shell must be a real one (a user made with nologin cannot autologin).
    case "$(getent passwd "$USER_NAME" | cut -d: -f7)" in
        */nologin|*/false) chsh -s /bin/bash "$USER_NAME" ;;
    esac
    PROFILE="$USER_HOME/.profile"
    [ -f "$USER_HOME/.bash_profile" ] && PROFILE="$USER_HOME/.bash_profile"
    # A hand-made UI start in another login file would fight over the display; do not edit it, tell the user.
    for f in "$USER_HOME/.bashrc" "$USER_HOME/.bash_profile" "$USER_HOME/.profile"; do
        [ -f "$f" ] || continue
        if grep -v '^[[:space:]]*#' "$f" | grep -q "archerytimer.ui_client"; then
            echo "WARNING: $f starts the UI by hand; remove that block or the display will be contested." >&2
        fi
    done
    touch "$PROFILE"
    sed -i '/# >>> archerytimer kiosk/,/# <<< archerytimer kiosk/d' "$PROFILE"
    cat >> "$PROFILE" <<'PROF'
# >>> archerytimer kiosk (managed by install_pi.sh; touch ~/.no-kiosk to disable)
if [ "$(tty)" = "/dev/tty1" ] && [ -z "${SSH_CONNECTION:-}" ]; then
    exec /opt/archerytimer/scripts/run_ui_tty1.sh
fi
# <<< archerytimer kiosk
PROF
    chown "$USER_NAME:" "$PROFILE"
fi

systemctl daemon-reload
systemctl restart systemd-journald
if [ "$ENABLE" -eq 1 ]; then
    systemctl enable archerytimer-core.service
    [ "$SERVICE_UI" -eq 1 ] && systemctl enable archerytimer-ui.service
    systemctl restart archerytimer-core.service
    [ "$SERVICE_UI" -eq 1 ] && systemctl restart archerytimer-ui.service
fi
echo "done. Status: systemctl status archerytimer-core"
if [ "$UI" -eq 1 ] && [ "$UI_MODE" = console ]; then
    echo "The UI starts on tty1 after login; reboot now (sudo reboot) to start the kiosk."
elif [ "$REBOOT" -eq 1 ]; then
    echo "Reboot needed for the graphics overlay: sudo reboot"
fi
echo "Probe the display stack on this Pi: sudo -u $USER_NAME $APP_DIR/.venv/bin/python $APP_DIR/scripts/env_probe.py"

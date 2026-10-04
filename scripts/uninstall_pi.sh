#!/usr/bin/env bash
# Remove the archery timer services (keeps /etc/archerytimer, the archery user and its data).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
for s in archerytimer-ui archerytimer-core; do
    systemctl disable --now "$s.service" 2>/dev/null || true
    rm -f "/etc/systemd/system/$s.service"
done
rm -f /etc/systemd/journald.conf.d/archerytimer.conf
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
for home in /home/*; do
    for f in "$home/.profile" "$home/.bash_profile"; do
        [ -f "$f" ] && sed -i '/# >>> archerytimer kiosk/,/# <<< archerytimer kiosk/d' "$f"
    done
done
systemctl daemon-reload
rm -rf /opt/archerytimer
echo "removed"

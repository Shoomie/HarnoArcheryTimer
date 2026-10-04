#!/usr/bin/env bash
# Starts the timer (core + display) on desktop Linux or macOS. Extra options are passed on, for example:
#   scripts/start.sh --no-serial              (no lights hardware, demo)
#   scripts/start.sh -- --fullscreen --lang en
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
[ -x .venv/bin/python ] || { echo "Run scripts/setup_desktop.sh first." >&2; exit 1; }
if [ "$(uname)" = Linux ] && [ -z "${ARCHERY_SG:-}" ]; then
    # The serial group was added by setup but this login session does not have it yet: restart
    # under that group so no log out is needed.
    for g in dialout uucp; do
        if getent group "$g" | grep -qE "[:,]${USER}(,|$)" && ! id -nG | tr ' ' '\n' | grep -qx "$g"; then
            cmd=$(printf '%q ' "$0" "$@")
            ARCHERY_SG=1 exec sg "$g" -c "ARCHERY_SG=1 $cmd"
        fi
    done
fi
exec .venv/bin/python -m archerytimer.launcher "$@"

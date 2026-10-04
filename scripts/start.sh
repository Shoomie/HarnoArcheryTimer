#!/usr/bin/env bash
# Starts the timer (core + display) on desktop Linux or macOS. Extra options are passed on, for example:
#   scripts/start.sh --no-serial              (no lights hardware, demo)
#   scripts/start.sh -- --fullscreen --lang en
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
[ -x .venv/bin/python ] || { echo "Run scripts/setup_desktop.sh first." >&2; exit 1; }
exec .venv/bin/python -m archerytimer.launcher "$@"

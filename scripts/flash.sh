#!/usr/bin/env sh
# Flashing menu: finds a Python 3 and runs scripts/flash.py (arguments are passed on).
here=$(cd "$(dirname "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$here/flash.py" "$@"
fi
exec python "$here/flash.py" "$@"

#!/bin/sh
# Builds and runs the native hostcore tests with g++ or clang++ (CXX overrides). Run from anywhere.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/../.."
LIB="$FW/lib/hostcore/src"
CXX="${CXX:-$(command -v g++ || command -v clang++)}"
OUT="${TMPDIR:-/tmp}/hostcore_native"
mkdir -p "$OUT"
"$CXX" -std=c++17 -Wall -Wextra -O1 -I"$LIB" "$HERE/test_hostcore.cpp" "$LIB/hostcore.cpp" -o "$OUT/test_hostcore"
"$OUT/test_hostcore" "$FW"

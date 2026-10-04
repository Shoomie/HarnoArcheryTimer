#!/bin/sh
# Builds and runs the native meshcore tests with g++ or clang++ (CXX overrides). Run from anywhere.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/../.."
LIB="$FW/lib/meshcore/src"
CXX="${CXX:-$(command -v g++ || command -v clang++)}"
OUT="${TMPDIR:-/tmp}/meshcore_native"
mkdir -p "$OUT"
"$CXX" -std=c++17 -Wall -Wextra -O1 -I"$LIB" "$HERE/test_mesh.cpp" "$LIB"/mesh_crypto.cpp "$LIB"/mesh_frame.cpp \
  "$LIB"/mesh_peers.cpp "$LIB"/mesh_arbiter.cpp "$LIB"/mesh_cmd.cpp "$LIB"/mesh_pair.cpp "$LIB"/mesh_x25519.cpp -o "$OUT/test_mesh"
"$OUT/test_mesh" "$FW"

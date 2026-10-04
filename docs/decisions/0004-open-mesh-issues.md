# 0004 – Mesh status and what is still open (updated 2026-10-04)

Companion to `0002` (design) and `0003` (workflow). Everything below is **not verified on hardware**: it is
unit-tested, simulated, or compiled only.

## Decided 2026-10-04 and built

| Decision | Where |
| --- | --- |
| Replay protection: persisted **session counter** (core data dir, +1 at every core start and serial connect; nodes keep the highest accepted per master in NVS and drop lower) | `docs/mesh.md` section 4, `radio_keys.py`, `meshcore` arbiter, `tools/mesh_sim`, three scenarios |
| **Emergency repeats:** after any change toward the safe state, resend TIMER every 50 ms for 500 ms | `SafetyRepeater` (C++), simulator; worst delivery 351 ms over 2000 seeded runs (5 followers, 30 % loss + bursts), none above 500 ms |
| **Remote default permissions** unchanged: primary, pause, resume, stop end (+ emergency always) | `ui_client/screens/remotes.py` |
| Single hop, manual takeover, radio-fed software follower (`--leader radio`, "Radio only" button), HMAC mesh key + per-remote keys | built |

## State of the pieces

| Piece | State |
| --- | --- |
| Contracts, vectors (`test_vectors_v2.txt`, `mesh_vectors.txt`), 13 arbiter scenarios | frozen; the two implementations agree |
| C++ `firmware/lib/meshcore` | MSVC native tests: 412 checks pass (real X25519 against RFC 7748 vectors) |
| C++ `firmware/lib/hostcore` (serial frames) | MSVC native tests: 2179 checks pass (replays all v1 and v2 vectors) |
| Firmware (`esp-0.4.0`, S3 and C3) | **compiles** for all four envs (S3 721 kB flash / 53 kB RAM, C3 754 kB / 48 kB); never flashed |
| Python (codec, simulator, serial v2, core, UI) | full suite 675 passed, 3 skipped on Windows; ruff and mypy clean |

## Behaviour of the firmware to know (from WP-J)

- The radio only starts when a mesh key exists or the node is in pairing. A keyless box needs `$C,mkey` over USB (the core
  pushes it on every connect) or pairing (hold buttons 1+2 for 3 s at boot, then press).
- Legacy `$M`: 0 host-driven master with radio off; 1 and 3 master (a mesh key is generated on the first bridge); 2 role E
  without feeding the host. A proto 1 host gets `$N`, not `$O`.
- A node is listed as remote (kind R) when it only has capability K. RSSI is 0 on Arduino core 2.x.
- A keyless remote cannot verify PAIR_OPEN (see `mesh.md` section 5): accepted on structure while pairing; PAIR_ACC is authenticated.

## Still open

1. **Hardware:** flash two boards, compile on the real cores, USB/serial bring-up, then loss, range and latency; 4 h soak.
   Check that opening the serial port does not reset the board (DTR/RTS) on the S3 and C3.
2. **Late sound starts:** a pattern started from a TIMER (missed SOUND frame) starts from its beginning, up to 400 ms
   later than on the master; an offset parameter in `outputs.cpp` would fix it. (Silence propagation and the 400 ms
   age guard are done: `sound_stop_propagates`, 420 native checks.) `sound_active` in the scenarios assumes blast and
   gap of 500 ms and a pattern length of count x blast + (count - 1) x gap.
3. **UI:** no "radio feed active" status (the node message has no `active_leader` field); the roster could show
   "unknown remote tried to press X".
4. **Pairing UX on the remote:** blink patterns and button timing are defaults to be tried on a real board.
5. **Leader failover** (unchanged): manual takeover exists, automatic does not.
6. Docs: replace `docs/espnow.md` by `docs/mesh.md` after hardware bring-up; update `docs/cluster.md`.

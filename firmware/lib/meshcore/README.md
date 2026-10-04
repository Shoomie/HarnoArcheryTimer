# meshcore: portable C++17 mesh v2 core

Pure logic for `docs/mesh.md` (frozen contract). No Arduino/ESP includes, no heap, no threads, no I/O. Time is always an
argument (`uint32_t now_ms`, wrap-safe), never read inside. **Not verified on hardware** (native tests only).
Native tests: `firmware/test/native/run_tests.bat` (MSVC) or `run_tests.sh` (g++/clang++); 412 checks at last run.

## Public API (headers in `src/`)

| Header | What it gives | Notes for the device build |
| --- | --- | --- |
| `mesh_frame.h` | `Frame` + payload structs, `decode(buf,len,src_mac,KeyRing,Frame&)`, `encode(frame,key,key_len,src_mac,out,cap)`, `compute_tag` | `KeyRing` holds the keys the receiver has: `mesh_key` (16), `remote_lookup` (CMD), `pairing_open` (PAIR_REQ, zero key), `pair_key` (32, PAIR_ACC). Identity is the `src_mac` of the ESP-NOW receive callback. Wrong magic, version, hop, length, tag or payload returns a non-`Ok` code: drop silently. `TimerPayload` is 29 bytes on the wire, `SoundPayload` 12 (both carry `session u32` after `master_id`). |
| `mesh_peers.h` | `PeerTable::accept(mac, epoch, seq, now)` dedupe `(mac, epoch, seq)`, `expire(now)`, `count()` | Call `accept` for every frame that decoded `Ok`; false = repeat, drop. Epoch is a random non-zero u16 picked at boot. |
| `mesh_arbiter.h` | `Arbiter(cfg, SessionStore*)`: `onTimer`, `onSound`, `setHostAlive`, `setHostLights`, `tick(now)`, `output(now)` | `HostRole` M/F/E/N. Call `tick` every few ms, then read `output()` (failsafe, lights, emergency, paused, buzzer, conflict, tx_rank, tx_master_id, follow, latest timer). `soundStartCount()`/`lastSound()` tell when to start a pattern; `soundStopCount()` counts stops (count 0 with a new `sound_seq`, no replay guard: silence the outputs when it changes); `soundActive(now)` is true while the started pattern runs. Pass the receive time. Frames with a lower `session` than stored are dropped inside (no effect at all). |
| `mesh_session.h` | `SessionStore` interface, `MemorySessionStore` (tests) | See "Device must implement". |
| `mesh_cmd.h` | `CmdGate` (master: remote table, counter, permission, ACK cache), `CmdSender` (remote: counter, 15 ms retransmit, 250 ms limit) | Persist `RemoteEntry::last_counter` and the `CmdSender` counter in NVS (the sender BEFORE sending). Retransmits use a new frame `seq`, same counter. |
| `mesh_config.h` | Timing constants, `RepeatSender` (0/3/15/40 ms), `SafetyRepeater` (50 ms steps for 500 ms) | See "Repeats" below. |
| `mesh_pair.h` | `derive_pair_key`, `make_blob`, `open_blob`, `X25519` interface, `PortableX25519` (real), `InsecureTestStubX25519` (tests only), `x25519()`, `x25519_is_zero()` | Never link the stub into firmware. |
| `mesh_crypto.h` | `hmac_sha256`, `ct_equal`, `Sha256` | `MESHCORE_EXTERNAL_HMAC` hook below. |

Repeats (transmit side, all "same frame, same seq", driven from the device loop):

- `RepeatSender`: `begin(now)` at each new TIMER/SOUND/CMD, then `while (poll(now)) radioSendCopy();`.
- `SafetyRepeater`: feed it the outgoing state with `observe(now, lights, emergency, sound_active)` whenever the TIMER content
  is computed (or call `trigger(now)`). After lights go RED, the emergency latch is set, or sound stops it reports a
  resend every 50 ms for 500 ms (`while (poll(now)) resendCurrentTimer();`); a new trigger restarts the window.
  Both repeaters may be due at once: send one copy per `poll()` true.

## Device must implement (Arduino/ESP32 side)

1. **Clock**: a monotonic `uint32_t` milliseconds value (`millis()`); pass the same value to receive and tick calls.
2. **Radio glue**: ESP-NOW broadcast send/receive on the fixed channel; own `epoch` (random non-zero, per boot) and `seq`
   (u16, +1 per new frame, repeats reuse it); the receive callback passes `src_mac`, buffer, length.
3. **HMAC override (optional)**: to use mbedtls, compile with `-DMESHCORE_EXTERNAL_HMAC` (this removes `Sha256`, the
   built-in `hmac_sha256` and `InsecureTestStubX25519`) and provide `mesh::hmac_sha256(key, key_len, const Part*, n_parts,
   out32)` with HMAC-SHA256 semantics (a key longer than 64 bytes is hashed first). `ct_equal` stays here. `PortableX25519`
   does not use HMAC and stays available.
4. **X25519 random source**: use `PortableX25519` and fill a 32-byte private key from the hardware RNG
   (`esp_fill_random`, radio on or `bootloader_random_enable()`); clamping is done inside. Master: generate a keypair when
   a pairing window opens, publish `publicKey` in PAIR_OPEN. Remote: generate per PAIR_REQ. Reject an all-zero shared
   secret (`x25519_is_zero`). Create the 16-byte remote key with the same RNG.
5. **SessionStore (NVS)**: `load(master_id, &session)` and `save(master_id, session)`. The arbiter calls `save` only when
   the highest accepted session for that master rises (first sighting counts as a rise), so flash wear is bounded by
   master restarts. Keep at least a handful of masters (the arbiter holds 8 in RAM and re-reads from the store on a
   cache miss). If the store is `nullptr` replay protection works only until the next reboot.
6. **Key storage**: mesh key (16 B), own remote key (16 B, remote role), master's remote table (`CmdGate::addRemote` with
   `mask` and `last_counter`, up to 8), master X25519 private key only in RAM during a window. Build a `KeyRing` per
   receive: `mesh_key`, `remote_lookup = CmdGate::lookupKey` with `remote_ctx = &gate`, `pairing_open` while the window
   is open, `pair_key` while waiting for PAIR_ACC. Encrypted-at-rest NVS is advised, not required by the contract.
7. **Serial/host glue** (`$R`, `$U`, `$P`, ...): map to `Arbiter::setHostAlive/setHostLights`, `onTimer`/`onSound`
   for frames received from the radio, `CmdGate::onCmd/onHostAck`.

## Limits and notes

8 masters, 16 peers, 8 remotes, 8 groups, sequence id up to 32 characters in this implementation (the mesh.md note says
16 on the wire; the codec accepts up to 32). `onSound` only acts for the followed master. The key agreement is as
unauthenticated against an active attacker as `docs/mesh.md` section 5 states.

# Mesh v2: radio wire format, arbiter, pairing (CONTRACT, frozen in Wave 0)

Replaces the v1 frames of `docs/espnow.md` once implemented. Decisions: `docs/decisions/0002-*`. Work split:
`docs/decisions/0003-*`. Vectors: `firmware/mesh_vectors.txt`. **Not verified on hardware.** Changing this
file after Wave 1 starts is the integrator's job only.

All integers little-endian. All frames are ESP-NOW broadcast on one fixed channel (`$C,chan`, default 1).
Maximum frame 250 bytes (ESP-NOW limit); every frame here is far smaller.

## 1. Frame layout

```text
0 magic 0xA8 | 1 version 0x02 | 2 type | 3 flags (bits 0-1 = hop, rest 0) | 4-5 epoch u16 | 6-7 seq u16
8.. payload | last 8 bytes: tag
```

- **Identity** is the sender's MAC from the receive callback (never inside the frame).
- **epoch**: random non-zero u16, new at every boot of the sender. **seq**: u16, +1 per new frame
  (repeats of one frame reuse its seq). Dedupe key `(src mac, epoch, seq)`: a new epoch resets the
  peer's state and is accepted at once (fixes the v1 reboot-deafness); same epoch needs
  `int16(seq - last) > 0`.
- **tag** = first 8 bytes of `HMAC-SHA256(key, frame[0 .. len-8] || src_mac(6))`. Keys, 16 bytes each:
  `mesh key` (types 1, 2, 3, 5, 6, 7), `remote key` of the sending remote (type 4),
  all-zero key (type 8, integrity only, accepted only while a pairing window is open),
  `pair key K` (type 9, section 5). A frame whose tag, magic, version or length is wrong is dropped
  silently. Hop is 0 in v2 first release (relay specified, **not built**); receivers accept hop 0 only.

## 2. Frame types and payloads

| Type | Name | Payload | Key |
| --- | --- | --- | --- |
| 1 | HELLO | `caps u8` (bit0 L lights, 1 S sound, 2 B buzzer, 3 K buttons, 4 R host-feed capable), `role u8` (0 node, 1 mirror, 2 master, 3 radio-fed host), `rank u8` (0/1/2), `conflict u8`, `master_id u32` (followed or own, 0 none), `fw u8 u8 u8` (major, minor, patch), `name_len u8` (0-12), `name` ASCII | mesh |
| 2 | TIMER | `master_id u32`, `session u32`, `rank u8`, `lights u8` (G=1 Y=2 R=4), `flags u8` (bit0 paused, bit1 emergency latch, bit2 buzzer), `mode u8` (0 idle, 1 running, 2 waiting, 3 finished), `phase u8` (index in the session sequence), `remaining_ms u32` (at transmit time; at pause time while paused), `end_no u8`, `total_ends u8`, `group u8` (index into SESSION groups), `round u8`, `total_rounds u8`, `session_rev u8`, `sound_seq u8`, `sound_count u8`, `sound_blast u8` (x10 ms), `sound_gap u8` (x10 ms), `sound_age u16` (ms since the sound started, `0xFFFF` = none) | mesh |
| 3 | SOUND | `master_id u32`, `session u32`, `sound_seq u8`, `count u8`, `blast u8` (x10 ms), `gap u8` (x10 ms) | mesh |
| 4 | CMD | `counter u32` (per remote, strictly increasing, persisted), `action u8` | remote |
| 5 | CMD_ACK | `target_mac 6`, `counter u32`, `result u8` (0 done, 1 denied, 2 unknown remote) | mesh |
| 6 | SESSION | `master_id u32`, `rev u8`, `flags u8` (bit0 alternate order, bit1 auto-advance), `total_ends u8`, `practice_ends u8`, `prep_ms u32`, `shoot_ms u32`, `warn_ms u32` (each `0xFFFFFFFF` = keep the sequence's value; warn 0 = off), `auto_delay_ms u32`, `seq_len u8`, `sequence_id` ASCII, `groups_n u8`, then per group `len u8`, ASCII | mesh |
| 7 | PAIR_OPEN | `master_id u32`, `seconds_left u8`, `master_pub 32` (X25519) | mesh |
| 8 | PAIR_REQ | `caps u8`, `name_len u8`, `name`, `remote_pub 32` | zero |
| 9 | PAIR_ACC | `target_mac 6`, `blob 32` | pair K |
| 10 | REVOKE | `target_mac 6` | mesh |

REVOKE (added 2026-10-04): after `$P,del,<mac>` the master repeats REVOKE for that MAC every 2 s for 10 minutes. A node that holds a remote key and
sees its own MAC forgets mesh and remote key (NVS) and searches for a master again (section 5), so "Remove" in the UI really un-pairs a
connected device and it shows up as a new request when the operator searches. A box that was off the whole time must be reset by hand
(`$C,mkey,<32 zeros>`, "Pair with the main timer again", or the boot hold). The Python codec does not know type 10 (only firmware sends it).

Action codes (CMD): 1 primary, 2 pause, 3 resume, 4 stop_end, 5 next, 6 back, 7 emergency. Nothing else
may ever be sent by a remote (no reset, quit, clear_emergency, settings). Permission mask bit `n-1`
allows action `n`; emergency (bit 6) is always allowed for every paired remote.

## 3. Timing (constants every implementation shares)

| Constant | Value |
| --- | --- |
| TIMER heartbeat | 200 ms and at once on any change |
| TIMER / SOUND / CMD first send, then repeats | at 0, 3, 15, 40 ms (same frame, same seq) |
| CMD retransmit until CMD_ACK | every 15 ms, at most 250 ms (same counter) |
| HELLO | every 2000 ms plus random 0-250 ms |
| SESSION | on change and every 2000 ms |
| PAIR_OPEN | every 1000 ms while the window is open; window 60 s default, 1-120 s |
| Peer expiry (roster) | 6000 ms without any valid frame |
| Master live | a TIMER heard within 1000 ms |
| Follow switch | the followed master is silent for 600 ms and another is live; or a live master with higher rank has been heard for 400 ms |
| Fail-safe | no live followed master (or host) for 1000 ms: RED, silent, fault LED blinking |
| Sound replay guard | a sound seen in TIMER starts only if `sound_age` < 400 ms |
| Safety-direction repeats | after any change toward the safe state (lights to RED, emergency latch set, sound stopped): resend the TIMER (same seq) every 50 ms for 500 ms, on top of the 0/3/15/40 ms repeats |

## 4. Arbiter (pure logic, no I/O: `firmware/lib/meshcore`, mirrored by the Python simulator)

Inputs: valid frames with receive time, host role (`M`, `F`, `E`, `N`), host alive, local clock.
Outputs: the lights/flags/sound to apply, whether to transmit TIMER and with what rank, conflict flag,
peer table.

- **Master table** by `master_id`: rank, last heard, source mac. A node's own master id (role `M`) is
  never in competition: a role-`M` node never follows.
- **Following** (roles `E`, `N`, or no host): keep the followed master while it is live. Switch only per
  the Follow switch row (section 3); among several candidates pick the highest rank, then the lowest
  `master_id`. Never switch because of a lower node id or MAC.
- **Conflict**: two different `master_id` with rank 2 are both *active* (the second most recent frame of
  each is no older than 600 ms; a role-`M` node with a live host counts as one): `conflict = 1`
  (in HELLO and `$O`) while that holds. No node flips because of a conflict.
  `firmware/arbiter_scenarios.txt` is the executable definition of this section.
- **Transmit**: role `M` and host alive: TIMER rank 2 with its own master id. Role `F` and host alive:
  TIMER rank 1 carrying the leader's `master_id` given by `$R`. Other roles never transmit TIMER.
- **Sound**: SOUND frame (or a TIMER whose `sound_seq` differs from the last one acted on for that
  master, within the replay guard) starts the blast pattern locally; the first TIMER from a newly
  followed master only records `sound_seq`. **Silence propagates:** a SOUND, or a TIMER whose `sound_seq` differs
  from the last one acted on, with `count == 0` stops any running pattern at once on every follower (a `$S,0`
  on the master); the replay guard does not apply to a stop (it is the safe direction). **Emergency latch** (`flags` bit1): outputs RED and stay
  RED while it is set, whatever `lights` says.
- **Session counter (replay protection, decided 2026-10-04):** `session` is a u32 owned by the master's *core*,
  persisted in its data dir and incremented at every core start and at every serial (re)connect to its MCU; the host
  passes it in `$R` and the mirror's host passes the leader's value. Every node keeps, per `master_id`, the highest
  `session` it has accepted **in NVS** (written only when it rises) and **drops a TIMER or SOUND whose `session` is
  lower**. Equal is accepted (same session; `(epoch, seq)` dedupe still applies), higher is accepted and recorded
  at once. Replays from earlier sessions, including across a node reboot, are therefore rejected. A master whose
  counter was lost (data dir erased) must be given a fresh `master_id` by its core (the core does this when it
  detects a missing counter file).
- **Remaining time for a radio-fed host**: deadline = receive time + `remaining_ms` (unless paused).
- **Commands**: only the node with role `M` and a live host accepts CMD; it checks the sender's remote
  key, counter (strictly greater than the last accepted), and permission mask, forwards `$P,cmd` to
  the host and later sends CMD_ACK with the host's `$P,ack` result. Duplicates (same counter) are
  re-ACKed from a small cache, never forwarded twice.

## 5. Pairing

1. Host `$P,open,<s>`: node broadcasts PAIR_OPEN every second (carries its X25519 public key).
2. A node with no key (any freshly flashed box, no button needed) or after holding buttons 1+2 for 3 s at boot
   (that one blinks) replies PAIR_REQ every second while it hears PAIR_OPEN. **No physical press** (changed
   2026-10-04): the operator sees name and hardware ID (MAC) in the UI and accepts or rejects. A node that is
   given a mesh key by its host (`$C,mkey`) leaves the keyless search at once.
3. Master node forwards `$P,req,<mac>,<name>,<caps>` to the host. The operator accepts or rejects in
   the UI (default Cancel/Reject). Accept: host sends `$P,accept,<mac>,<mask hex>`.
4. Master node: `shared = X25519(master_priv, remote_pub)`;
   `K = HMAC-SHA256(shared, "harno-pair" || remote_mac(6) || master_mac(6))` (32 bytes);
   `blob = (mesh_key || remote_key) XOR HMAC-SHA256(K, "enc")` (32 bytes, the remote key is random,
   created by the master node); PAIR_ACC carries it, tag key = K. The remote derives the same K,
   decrypts, stores both keys in NVS and from then on sends HELLO frames signed with the mesh key.
5. Host `$P,del,<mac>` removes a remote key; `$C,mkey,<32 hex>` replaces the mesh key (reset radio network).
6. A remote with no key cannot verify PAIR_OPEN (signed with the mesh key): it accepts PAIR_OPEN on structure only
   while pairing. A forged PAIR_OPEN can at most make the remote pair with the attacker's key exchange (the remote
   then never reaches the real network); PAIR_ACC itself is authenticated by K. The remote keeps the keypairs of
   its last four PAIR_REQs (the operator's accept takes seconds) and the master answers the newest pubkey it saw.
7. Closing the window (`$P,close`, timeout, emergency) stops PAIR_OPEN and ignores PAIR_REQ.

The key agreement is not authenticated against an active attacker inside the 60 s window; the operator
accept (identified by name and MAC) is the countermeasure; the physical press was dropped on purpose. The mesh key never travels in the clear.

## 6. Radio-fed host (role `E`)

The node drives its own outputs from the followed master and forwards verbatim to the host:
TIMER payload as `$F,<hex>`, SOUND payload as `$W,<hex>`, SESSION payload as `$J,<hex>`. The host
rebuilds a Snapshot (`mesh_follower`) and sends its commands as `$P,tx,<action>`; the node sends them
as CMD with its remote key, so a radio-fed software follower must itself be a paired remote.

## 7. Serial v2 (host side, see `docs/protocol.md`)

Frames added: `$R` role, `$C` config, `$Q` config query, `$U` timer state for the radio, `$J` session,
`$P` pairing and remote commands, `$O` status v2, `$D` roster, `$F`/`$W` radio feed, and `$S` with
blast/gap. Proto number in `$I` becomes 2; capability letter `R` = mesh v2.

## 8. Clarifications from Wave 1 (binding, found while two implementations were built)

- **Field meanings:** TIMER `phase` = index into the session sequence's phases; `group` = index into the SESSION
  groups; `round` = the engine's 0-based `round_index`; `remaining_ms` is 0 unless the mode is running (paused or
  emergency: the frozen time). A follower derives the waiting length from the sequence.
- **Sizes:** TIMER payload 29 bytes, SOUND 12. `$F` carries exactly 29 and `$W` exactly 12 bytes (hex). `$P,accept` mask
  is at most `7F`. `$P,state` seconds 0-120. Names (`$P,req`, `$D`, `$C,name`) match `[A-Za-z0-9_-]{1,12}`.
- **CMD retransmits** use a **new `seq`** with the same `counter`; only the 0/3/15/40 ms copies of one frame reuse the
  `seq`. Otherwise the master's dedupe drops the retransmit and a lost ACK stalls the remote.
- **Result 2 (unknown remote) is never sent:** a CMD from an unpaired MAC fails its tag, so the master has no key to
  answer with. Such frames are dropped silently. Hosts only send results 0 and 1.
- **Scenario files:** the expects in `arbiter_scenarios.txt` see only the events above them in the file (file order),
  not all events at the same millisecond.
- **Implementation limits** (C++ core): 8 masters, 16 peers, 8 remotes, 8 groups; sequence id up to 16 characters on
  the wire.
- **Known weaknesses, open:** (1) replayed old TIMER frames: **closed** by the session counter (section 4, decided). (2) emergency
  delivery tail under 30 ms burst loss: **closed** by the safety-direction repeats (section 3, decided);
  re-measure in the simulator.

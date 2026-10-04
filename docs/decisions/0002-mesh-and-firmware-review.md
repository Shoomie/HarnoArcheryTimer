# 0002 – ESP32 firmware review and the timer mesh (proposal, not yet decided)

Status: **draft for discussion** (2026-10-04). Nothing here is built. Reviewed: `firmware/esp32s3/src/*`,
`docs/espnow.md`, `docs/cluster.md`, `docs/protocol.md`, `core_service/netdisco.py`, `node.py`, `inputs.py`.

## 1. Review of the current firmware

The firmware has never been compiled, so the first finding is that **nothing below is tested**.
Severity: **S** safety/correctness, **R** reliability, **D** design gap against the new goals.

| # | Sev | Finding |
| --- | --- | --- |
| 1 | S | **Reboot deafness.** Receivers keep `lastSeq` per sender id forever (`peerFor` returns the old entry). A transmitter that power-cycles restarts `txSeq` at 1, and every receiver drops its frames until the new seq passes the old one, so a bridge that ran 10 min is ignored for ~10 min. `lastMs` is refreshed before the dedupe check, so the peer still looks alive while followers time out to RED. Also: opening the serial port may reset ESP32 boards (DTR/RTS), so every core reconnect could trigger it. Verify on hardware. |
| 2 | S | **Node id collisions.** `id = hash(mac) % 250 + 1`: ~10 % collision chance with 8 devices, ~23 % with 12. Equal ids ignore each other (`src == nodeId`), the lowest-id arbitration is arbitrary, and `ESPNOW_SLOT` defaults to 1 on every build, so two remotes are indistinguishable. The receive callback already gives the sender MAC for free: use it as identity. |
| 3 | S | **Master is whoever has the lowest hash.** Not the device the operator chose. Two cores both acting as leaders are silently accepted, each drives its own MCU, and the mesh follows one of them for an arbitrary reason. A takeover (`src <= followSrc`) is immediate, so a late-joining lower id flips every follower mid-end. |
| 4 | S | **Sound is a one-shot event.** `SOUND` is sent once plus two repeats within 6 ms; one interference burst loses all three, and the heartbeat does not carry it. Emergency blasts depend on that. Same for `BTN`: a lost "down" edge of an emergency button is a failed emergency stop. |
| 5 | S | **No authentication, shared default net key (`0x4152`).** Two clubs in range merge into one network by default; anyone can send GREEN. The doc says so, but the default should not be shared, and the remote-control goal needs real authorization. |
| 6 | R | **Not a mesh.** Single hop, no relay, so range is one radio hop. Fine for a field, but "mesh" implies more. |
| 7 | R | Fail-over glitch: an AUTO device whose host dies goes RED after 1 s, and only then can it learn that another AUTO device (silent while a lower id transmitted) starts transmitting after a 1.5 s hold, so a gap of 0.5-1.5 s of RED on followers. Safe, but visible mid-end. |
| 8 | R | Repeats are 3 ms and 6 ms after the original: no protection against bursts longer than that. |
| 9 | R | `esp_wifi_set_ps(WIFI_PS_NONE)` not set; channel fixed to 1, which is the most common venue WiFi channel; no channel setting, no scan. |
| 10 | D | State frames carry only lights and buzzer. A **software** instance cannot be synchronized from them (no phase, remaining time, end number, group, paused, emergency). |
| 11 | D | The four modes (`off/bridge/follow/auto`) mix "who drives my outputs" with "do I transmit". The host cannot tell the MCU where its timer comes from, so the MCU cannot feed the host. No device roster, no names. |
| 12 | D | Remote buttons are raw edges with a slot; the core has no way to know which remote is allowed to do what. |
| 13 | R | `$S` carries only a count: the MCU uses `BLAST_MS/GAP_MS = 500` constants while the engine setting `blast_ms/gap_ms` is not sent. Changing the engine setting would silently desync MCU horn and local speaker. (Only the ESP-NOW `SOUND` frame carries the timings, and it is fed from the same constants.) |
| 14 | minor | `processLine` rejects lowercase hex only if the first digit is `a` (should reject `a-f`). `main.cpp` mixes serial protocol, arbitration, buttons and outputs in one file, so none of it is unit-testable off-device. |

Verdict: the single-hop broadcast design works on paper for lights and sound, but 1-5 must be fixed
before any field use, and the new goals (named master, remotes, software sync over radio) need a
protocol v2 rather than patches.

## 2. Proposed model

**One firmware image, behaviour from stored configuration and from what the host declares.**

### Node configuration (NVS, set over USB by the core, or over the air by an accepted admin command)

`name` (up to 12 chars, e.g. "Line 1"), `lights on/off`, `sound on/off`, `remote buttons on/off`,
`radio on/off`, `channel`, `mesh key`. Capabilities (which pins exist) are build-time; use is config.
So the same binary can be a light box, a horn box, a button remote, or all three.

### Sources, in priority order (derived, no operator-visible "modes")

1. **USB host that declares itself master** (`$R,M`): its outputs follow the host, and the node
   transmits as the master's radio presence.
2. **USB host fed by the network** (`$R,F`: a follower core with LAN link): outputs follow the host,
   the node relays that state into the mesh as a lower-rank "mirror".
3. **Mesh** (no host, or `$R,E`: the host wants its own timer *from* the radio): outputs follow the best
   live master on the radio; with `$R,E` the node also forwards the compact state to the host.
4. **None for 1 s: RED and silent** (unchanged).

`$R,<M|F|E|N>` is sent by the core in every connect sequence (like `$M` today), so it is the
"auto-identify" handshake: the MCU learns whether to feed the host, be fed, or both.
`$M` stays as a v1 compatibility alias (0 off, 1 bridge ≈ `M`/`F`, 2 follow ≈ `E`, 3 auto).

### Who is master (on the air)

Every timer frame carries `master_id` (random 32-bit generated when a leader core starts) and a
`rank` (2 leader engine, 1 mirror, 0 none). Rules:

- A node follows the live master it already follows (**stickiness**); it switches only after 1.5 s of
  silence, or to a strictly higher rank. Never to a lower id just because it is lower.
- A second rank-2 master in range is a **conflict**: nobody flips; every node reports `conflict=1`
  in `$N`, the core shows a loud plain-language banner naming both ("Two main timers: Simon-PC and
  Pi-Line1. Stop one."). Nothing is demoted automatically while a session runs.

### Frames (v2, ESP-NOW payload up to 250 B; sketch, sizes approximate)

All frames: `magic, version, type, hop, seq(16), boot-epoch(16)` + payload + **8-byte truncated
HMAC** (mbedtls, hardware accelerated; mesh key). Sender identity = MAC from the receive callback.
Dedupe by `(mac, boot-epoch, seq)`: a reboot changes the epoch, fixing finding 1.

| Type | Payload | Rate |
| --- | --- | --- |
| `HELLO` | name, caps, fw version, role, rank, master seen, config hash | every ~2 s, jittered |
| `TIMER` | master_id, rank, lights mask, flags (paused, emergency latch, buzzer), phase code, **remaining ms at tx**, end no, total ends, group, `sound_seq`, `sound_count`, blast/gap, `sound_age` | on change and every 200 ms |
| `SOUND` | same sound fields | immediate, repeats at 0, 3, 15, 40 ms |
| `CMD` | remote id, counter, action (`primary`, `pause`, `emergency`, `stop_end`, `next`, `back`...) | repeated every ~15 ms for 250 ms until acknowledged |
| `CMD_ACK` | remote id, counter | inside `TIMER` and as a short frame |
| `PAIR_*`, `ADMIN` | see section 3 | |

- **Sound heals itself:** every heartbeat carries `sound_seq`, so a node that missed the `SOUND` frame
  starts the pattern from the next heartbeat if `sound_age` is still small, and never replays an old one.
- **Emergency is a latched flag** in `TIMER` (RED, blasts, until the master clears it), not an event.
- **Relay:** a node rebroadcasts an unseen `TIMER`/`SOUND`/`CMD` with `hop+1` (max 2), after 0-2 ms
  jitter, subtracting its dwell time from `remaining ms`. Real range extension; a node in range of
  the master never needs it. Off by default if testing shows collisions.
- Followers' software gets deadlines as `local_rx + remaining`, so no clock sync is needed (error is
  the air latency, about 1-2 ms per hop).

### Host feed over the radio (`$R,E`)

New serial frames: `$X,<hex of TIMER payload>` (state), `$Y,<sound>` (event), `$D,<mac>,<name>,<caps>,<rssi>`
(roster, on change). The core gets a `MeshFollower` service next to `FollowerService`: it rebuilds a
Snapshot for its UI from `$X`, mirrors nothing (the MCU already drives its own outputs), and sends
commands back as `CMD` through the same MCU. A software instance on the radio is therefore just "a remote
with a screen". Needs the follower to know the session config (sequence ids, preset): `TIMER` carries
phase code and end numbers only, and a `SESSION` frame (preset id + overrides, on change and every ~2 s)
fills in the rest. **Open: how much of the session must travel (section 5).**

## 3. Remotes, trust and pairing

Two layers, so a stray box can neither show GREEN nor stop the timer:

- **Mesh key** (one per installation, random, generated by the first leader core, stored in the core and
  pushed to each of its MCUs). HMAC on every frame. Provisioning an ESP32: plug it into any core once
  (Hardware screen: "Set up this module": name, outputs, key). Replaces the shared default net key.
- **Per-remote key** for `CMD` only, created by pairing:
  1. Master core UI: Settings > Wireless remotes > **Add remote** opens a 60 s pairing window
     (`$P,1`). The window shows a countdown and closes on emergency.
  2. A remote with no key (or after holding two buttons for 3 s) broadcasts `PAIR_REQ` (MAC, name) and
     blinks its lights; it needs a physical button press on the remote during the window.
  3. The master MCU relays `$P` to the core, which asks the operator: **"Remote 'Finish line' (3A:F2)
     wants to join: Accept / Reject"**. Cancel is the default.
  4. On Accept the keys are exchanged (X25519 key agreement in mbedtls, so nothing secret is sent in
     the clear) and the remote is stored with its **permission**: `emergency only` (default),
     `control` (primary, pause, next, back, stop end), never `reset` or `quit` from a remote.
  5. Remove remote in the same screen deletes its key; "Reset radio network" rotates the mesh key.
- Authorization is checked **twice**: by the master MCU (drops unpaired or unauthorized `CMD`) and by
  the core (permission table, source `remote:<mac>`), with a rate limit. The core stays the only place
  that decides what a command does.
- A remote's emergency press also turns its own lights RED/sound off at once (safe direction only);
  everything else waits for the master's confirmation in `TIMER`.
- Keyboard and mouse on the master are unchanged; `$K` from MCU buttons stays `mcu:n`; a radio remote
  is `remote:<name>`, so `[buttons]` bindings can address it.

## 4. Seeing the master (software side)

- Every core broadcasts the UDP beacon (not only leaders): `role` (leader / follower / alone), `name`,
  `node id`, `follows` (leader name), `session state` (idle/running), radio status, app version.
  Add mDNS (`_archerytimer._tcp`) as a second path for networks that block broadcast.
- Settings > **Timer network** lists everything found with plain words: "Main timer: Simon-PC (this
  device)", "Follower: Pi-Line1, follows Simon-PC", "Radio: Light box 'Line 2' (via radio, good signal)",
  "Remote 'Finish line' (paired, emergency only)". Same data feeds the existing status bar chip:
  *Main timer*, *Follows Simon-PC*, *Works alone*, *Radio only*.
- A leader that hears another leader's beacon raises the conflict banner (section 2). The leader lists
  its followers (closes the open "Roster" point in `docs/cluster.md`).
- Follower software on the network and a bridge on the radio at the same time: LAN wins as source, radio
  is the fallback if the LAN link drops (same rule as `auto` today), stated on the screen.

## 5. Plan (one milestone at a time, firmware first because nothing is compiled)

| | Step | Done when |
| --- | --- | --- |
| F0 | Make it build (PlatformIO S3 and C3), split `main.cpp` into modules with a pure-C++ core (frame codec, arbiter, dedupe, relay) that also builds natively; replay `test_vectors.txt`; fix findings 1, 2, 4, 8, 13, 14 in v1 | `pio run` for both boards, `pio test -e native` passes |
| F1 | **Mesh simulator in Python** (N nodes, lossy/bursty radio, reboots, partitions, two masters) driving the same C++ arbiter through a thin wrapper or a port with shared vectors | simulated runs show: no flip-flop, reboot recovers in < 1 s, emergency delivered despite 30 % loss |
| F2 | Protocol v2 on air and serial (`$R`, `$N` v2, `$D`, `$X`, `$Y`, `$P`, blast/gap on `$S`), HMAC, HELLO/roster, relay | vectors for every frame; two real boards on the bench |
| F3 | Core: roster, beacon v2, conflict banner, Timer network screen, `$R` handshake | tests with `sim_device`; screenshots |
| F4 | Remotes: pairing, permissions, `CMD`/ack, remote bindings, UI | pairing tests; real remote on a bench |
| F5 | Mesh-fed software follower (`MeshFollower`, `SESSION` frame) | one Pi follows a leader over radio only |
| F6 | Hardware: loss, range, latency and 4 h soak with 3+ boards; update `docs/benchmarks.md` | numbers recorded, not assumed |

Each milestone ends with tests, ruff/mypy, docs and a short summary, as agreed. Firmware that I cannot
run stays flagged "not verified on hardware" until step F6.

## 6. Decisions (user, 2026-10-04)

1. **Trust:** mesh key plus per-remote keys, operator-accepted pairing (sections 2-3 as written).
2. **Remote rights:** per-remote setting; emergency only by default; reset and quit never from a remote.
3. **Radio-fed software follower is in the first mesh version** (F5 is no longer "later"; the
   `SESSION` frame and `MeshFollower` ship with the rest). Expect the largest milestone.
4. **Single hop for now** (relay stays specified but not built until range is measured on a field).
   **Manual takeover** ("Make this device the main timer", with a confirm) is built in F3; automatic
   failover stays out.
5. Channel: not asked; default **fixed channel, configurable** over USB (`$C`), no scan in v1.

Still open: exact `SESSION` frame contents (which preset fields a radio follower needs), and whether
the first demo is single-node as the earlier review suggested (recommended: F0-F2 on one S3 + one C3).

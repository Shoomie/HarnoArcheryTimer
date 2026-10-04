# Multi-device timer network (cluster)

Goal: several devices (Pi or PC, each with its own screen, lights, sound and buttons) run as one
timer. Every device can run commands and every device can have light/sound hardware.

## Joining without any network (radio-only follower, 2026-10-04)

A club on a range with no wifi or LAN needs nothing but the two ESP32s. On the follower laptop choose Menu > Network and
sync > "Radio only". The core then does **not** push a mesh key into its ESP32 (`mesh_config` has only the name), so a
fresh ESP32 is keyless and asks the master to pair, exactly like the stand-alone boxes. On the master open Menu > Wireless
remotes, tap the new device (name = the laptop's host name, plus MAC), pick its rights and Accept: the radio hands over the
mesh key and a remote key, the follower then shows the timer from the radio feed and can send the commands it was granted.
A box that already holds an old key: "Pair with the main timer again" (Network screen) sends a one-shot `$C,mkey,<32 zeros>`
(`SerialWorker.forget_radio_keys`, never remembered) and the ESP32 forgets both keys and searches again. Works the same on a
Pi or any other host. **Not yet run between two real C3 boards** (tested: unit tests, compile; keyless pairing C3/WROOM).

## Discovering new radio devices (2026-10-04)

Menu > Remotes starts a search (`pair_open` with `discover`): the core keeps the MCU's pairing window open
and renews it (not while a request waits for the operator, at most 10 minutes after the last press of
"Search"). A keyless ESP32 in range shows up within a second or two as `name (MAC)`; tapping the row opens
its rights (same toggles as a paired remote), Accept sends `$P,accept`. Devices that stop asking for 25 s
leave the list; a rejected device stays hidden until the next search. **Limit:** a core always keeps its own
mesh key, so the ESP32 of a follower core that is not yet approved is on a foreign key and cannot be heard by
the master; approve the follower core under Menu > Followers (that hands over the mesh key and the ESP32
then appears in the timer network).

## Model: one leader, any number of followers

```text
 Device A (leader)                         Device B (follower)
 ┌───────────────────────────┐            ┌────────────────────────────────┐
 │ engine (the only one)     │  events    │ mirrors events to its MCU      │
 │ serial -> MCU A           │ ─────────► │ serial -> MCU B                │
 │ IPC server  ◄─────────────┼────────────┤ forwards commands to leader    │
 │   UI clients, buttons     │  commands  │ IPC server for local UI/buttons│
 └───────────────────────────┘  state     │   (state with local-clock times)│
                                          └────────────────────────────────┘
```

- **One timeline.** Only the leader runs the engine, so there is no merge problem and no two
  devices can disagree about what the timer is doing. Commands from any device are executed in
  the order the leader receives them.
- **Hardware on every device.** The leader sends each hardware event (light, whistle, buzzer)
  as it happens (`event` IPC messages). A follower writes it straight to its own MCU. Every
  `state` message also re-asserts the light, so a missed event heals within one message.
- **Screens on every device.** A follower republishes the leader's `state` to its own UI
  clients. The deadlines are translated into the follower's clock using the measured offset
  (`ipc/clocksync.py`), so a screen attached to any device counts to the same instant.
- **Commands from every device.** A follower accepts commands from its UI clients, MCU buttons
  and GPIO and forwards them to the leader. The follower's light status shown on its own
  screens is *its* hardware link, not the leader's.
- **Fail-safe.** A follower with no leader for 1 s forces its lights RED and silences sound,
  and tells its UIs (`link` message with `upstream = down`), which then show "no contact".
  An emergency command on a follower with no leader still stops that follower's own outputs.
  If the leader dies, followers go RED and silent: start the timer on another device as the
  new leader (restart it without `--leader`) and point the others at it. There is no automatic
  leader election yet (see below).

## Running it

Leader (listen on the network):

```text
python -m archerytimer.core_service --host 0.0.0.0
```

Each follower:

```text
python -m archerytimer.core_service --leader 192.168.1.10:8765 [--espnow auto]
python -m archerytimer.ui_client --fullscreen        # shows this device's view
```

The same settings can live in `config/default_settings.toml` under `[node]` (`leader`,
`espnow`). Without `--leader` a core is a leader (and a perfectly good stand-alone timer).
A display-only machine does not need a core at all: run `ui_client --host <any core's IP>`.

## Choosing how a device syncs (menu: "Network and sync")

Every device can have a screen, lights and sound. The menu screen sets three things on the core
(stored in `core_node.json` in the user data dir):

| Choice | Meaning | Takes effect |
| --- | --- | --- |
| Works alone (default) | own timer, listens on this machine only | |
| Main timer (leader) | runs the session, listens on the network, announces itself by UDP beacon (port 8766) | after **Apply** |
| Follows a main timer | mirrors a leader's lights and sound; the leader is chosen from those found on the LAN (or automatic when exactly one is found) | after **Apply** |
| Lights on this device: on / off | keeps this device's own lamps dark (`$L,O`) whatever the engine says; RED on shutdown or lost link is unchanged. Not locked by start flags. In `bridge` mode the dark state is also what nearby light boxes receive, so switch lights off only on a device that does not feed boxes | immediately |
| Wireless light boxes: off / send / follow / automatic | ESP-NOW role of the attached ESP32 | immediately |

**Apply** restarts the core's service in-process (lights go red for a moment) and is refused while
a session is in progress. Start flags (`--leader`, `--espnow`, `--host`) override the stored choice
and lock the screen. Priority: flags, stored choice, `[node]` in `default_settings.toml`.
Over IPC: `settings` values `node_role`, `node_leader`, `espnow`, `lights`; the `apply_network` command; the
core answers with a `node` message. A screenless ESP32 light box in `follow`/`auto` mode needs no
computer at all.

Alternatives by command line: `--leader HOST` / `[node] leader` (role follower), `--host 0.0.0.0`
(leader), `--espnow off|bridge|follow|auto` / `[node] espnow`.

Network sync and ESP-NOW combine: a follower's MCU can additionally bridge to nearby
stand-alone ESP32 light boxes (mode `bridge` or `auto`), so far-away lights without a computer
still follow the timer.

## Limits and open points

- **No leader election / failover.** Followers fail safe (RED, silent). A manual restart picks
  a new leader. Automatic failover needs a decision on who may become leader; ask before building.
- **Latency.** Events travel over TCP, so on wired LAN expect about a millisecond or less, on
  WiFi a few milliseconds, with occasional spikes. Lights on followers can lag the leader's by
  that much. The measured clock offset only affects what screens display, not light timing.
- **A lost `$S` whistle** on a follower MCU is not healed by the heartbeat (same open point as M7).
- **No authentication** on the IPC port. Use a trusted network only.
- **Roster.** The leader does not yet list connected followers; the status screen (M6) can.
- **Not verified on real hardware or networks.** Tested only with in-process transports and
  simulated MCUs (`tests/core_service/test_cluster.py`).

## Follower access (contract, 2026-10-04; `ipc/access.py`, builders in `ipc/messages.py`)

The leader decides what each follower may do. Decided: operator approval plus a per-follower key; presets and
per-action toggles; an unapproved follower can only watch; emergency always works from everywhere.

- **Permissions:** `primary pause resume stop_end next back reset configure settings clear_emergency`; emergency needs none.
  Presets: `view` (none), `operator` (primary, pause, resume, stop_end, next, back), `full` (all).
- **Join:** a follower core sends `join {id, name}`; an unknown id becomes *pending* (watch only) and shows up on the
  leader's Followers screen. On approval the leader creates a random per-follower `key` and sends `access` with `key`
  and the radio `mesh_key` once (plain over the LAN, which is trusted here); the follower stores both, adopts the mesh
  key for its own ESP32 and from then on proves itself with `challenge`/`auth` (HMAC-SHA256 of the nonce).
- **Enforcement** is on the leader for every non-loopback connection (`required_perm`): missing permission means the
  message is dropped and `denied {name}` goes back. Connections from the leader's own machine are the operator.
  An unauthenticated remote UI is watch-only too.
- **Follower UI:** the follower core tells its UIs its state (`follower` message); buttons without permission are
  greyed, pending shows "waiting for approval". `link` carries `leader_rtt_ms` and `leader_offset_ms` for the clock-sync
  diagnostic.
- **Not covered:** the LAN itself is not encrypted; a key that travels in the approval message could be read by someone
  sniffing that exact moment. Approve followers on a network you trust.

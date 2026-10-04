# Several devices as one timer

Several devices (Pi or PC, each with its own screen, lights, sound and buttons) can run as one timer. Every device can
run commands and every device can have light and sound hardware. They connect over a **LAN**, over the **ESP32 radio**
([mesh.md](mesh.md)), or both.

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

- **One timeline.** Only the leader runs the engine, so no two devices can disagree about what the timer is doing.
  Commands from any device run in the order the leader receives them.
- **Hardware on every device.** The leader sends each hardware event (light, whistle, buzzer) as it happens (`event` IPC
  messages). A follower writes it straight to its own MCU. Every `state` message also re-asserts the light, so a missed
  event heals within one message.
- **Screens on every device.** A follower republishes the leader's `state` to its own UI clients. Deadlines are translated
  into the follower's clock with the measured offset (`ipc/clocksync.py`), so every screen counts to the same instant.
- **Commands from every device.** A follower accepts commands from its UI clients, MCU buttons and GPIO and forwards them
  to the leader, as far as its rights allow (below). The light status on a follower's screens is *its* hardware link.
- **Fail-safe.** A follower with no leader for 1 s forces its lights RED, silences sound and tells its UIs (`link` with
  `upstream = down`), which show "no contact". An emergency on a follower with no leader still stops its own outputs.
- **A display-only machine needs no core:** `ui_client --host <any core's IP>`.

## Choosing how a device syncs (Menu > Network and sync)

The screen sets these on the core (stored in `core_node.json` in the user data dir):

| Choice | Meaning | Takes effect |
| --- | --- | --- |
| Works alone (default) | own timer, listens on this machine only | |
| Main timer (leader) | runs the session, listens on the network, announces itself by UDP beacon (port 8766) | after **Apply** |
| Follows a main timer | mirrors a leader's lights and sound; the leader is picked from those found on the LAN (automatic when exactly one is found) | after **Apply** |
| Radio only | no LAN: the timer arrives over the ESP32 radio; the device pairs with the master like a remote | after **Apply** |
| Lights on this device: on / off | keeps this device's own lamps dark whatever the engine says (RED on shutdown or lost link is unchanged). In `bridge` mode the dark state is also what nearby light boxes receive | immediately |
| Wireless light boxes: off / send / follow / automatic | ESP-NOW role of the attached ESP32 | immediately |

**Apply** restarts the core in-process (lights go red for a moment) and is refused while a session is in progress. Start
flags override the stored choice and lock the screen. Priority: flags, stored choice, `[node]` in
`config/default_settings.toml`.

Without the menu, by command line:

```text
python -m archerytimer.core_service --host 0.0.0.0                           # leader, listens on the network
python -m archerytimer.core_service --leader 192.168.1.10:8765 [--espnow auto]   # follower
python -m archerytimer.core_service --leader radio                           # radio-only follower
python -m archerytimer.ui_client --fullscreen                                # this device's display
```

`--espnow off|bridge|follow|auto` sets the ESP32's role. A follower's MCU can additionally bridge to nearby stand-alone
light boxes (`bridge` or `auto`), so far-away lights without a computer still follow the timer.

The timer network (every core on the LAN, radio modules, remotes, who follows whom, and a banner when two devices claim to
be the main timer) is listed under Network and sync. "Make this device the main timer" (with a confirm) is the manual
takeover.

## Follower access (LAN)

The leader decides what each follower may do. Code: `ipc/access.py`, `core_service/followers.py`.

- **Join and approval.** A follower core sends `join {id, name}`. An unknown id is *pending* (watch only) and appears on
  the leader's Menu > Followers. On approval the leader creates a random per-follower `key` and sends it once, together
  with the radio `mesh_key`; the follower stores both, gives the mesh key to its own ESP32, and from then on proves itself
  with `challenge`/`auth` (HMAC-SHA256 of a nonce). Rights are a preset plus per-action toggles. A rejected or removed
  follower asks to join again by itself.
- **Rights:** `primary pause resume stop_end next back reset configure settings clear_emergency`. Presets: `view` (none),
  `operator` (primary, pause, resume, stop_end, next, back), `full` (all). **Emergency always works from everywhere.**
- **Enforcement** is on the leader for every non-loopback connection: a missing permission drops the message and sends
  `denied`. Connections from the leader's own machine are the operator. A remote UI without approval is watch-only.
- **Follower UI:** buttons without permission are greyed; a pending follower shows "waiting for approval".
- **Sync diagnostic:** a follower core logs and publishes `leader_rtt_ms` and `leader_offset_ms`.

The LAN itself is not encrypted, and the key travels in the approval message: approve followers on a network you trust.

## Radio-only follower (no network at all)

A club on a range with no WiFi or LAN needs only the ESP32 modules.

1. On the follower computer choose Menu > Network and sync > **Radio only** > Apply. The core does not push a mesh key to its
   ESP32, so the module is keyless and asks the master to pair.
2. On the master open Menu > **Wireless remotes**. The new device shows up within a second or two as name (the computer's host
   name) plus MAC. Tap it, pick its rights, **Accept**.
3. The master hands over the mesh key and a remote key. The follower now shows the timer from the radio feed and can send the
   commands it was granted.

To start over, "Pair with the main timer again" on the Network screen makes the ESP32 forget both keys and search again.
Removing a device on the master also un-pairs it over the radio; it then pairs again as a new request.

Measured with two ESP32-C3 boards on one PC and no network (`scripts/hw_e2e_two_boards.py`, 34 checks): join, accept,
mirrored session (lights agree; the countdown deadline is 8-31 ms behind the master, median about 23 ms, which is two USB
hops), commands and rights over the radio, restarts of both cores, remove and re-pair, fail-safe when the master stops.

**Finding new radio devices.** Wireless remotes > Search keeps the master's pairing window open (renewed while searching, at
most 10 minutes after the last press) and lists keyless modules in range. Devices that stop asking for 25 s leave the list; a
rejected device stays hidden until the next search. A follower core that is not yet approved on the LAN keeps its own mesh
key, so the master cannot hear its ESP32 until the follower has been approved under Followers.

## Limits

- **No automatic leader election.** If the leader dies, followers go RED and silent. An operator makes another device the main
  timer (manual takeover) and the others follow it.
- **Latency.** Events travel over TCP: about a millisecond or less on a wired LAN, a few milliseconds on WiFi with occasional
  spikes. Lights on followers can lag the leader by that much. The clock offset only affects what screens show, not light timing.
- **The IPC socket is not encrypted** (see Follower access).
- **Radio:** single hop, range of one ESP-NOW link; see [mesh.md](mesh.md).

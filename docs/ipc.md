# IPC: core service <-> UI client

Newline-delimited JSON, one object per line, each with `type` and `v` (protocol version, currently 1).
Unknown types are ignored and logged. Bad lines are dropped.

- Messages: `src/archerytimer/ipc/messages.py`
- Server and client helper: `src/archerytimer/ipc/server.py`
- Transports behind one interface (`ipc/transport.py`): `transport_socket.py` (localhost TCP,
  default `127.0.0.1:8765`) and `transport_inproc.py` (tests, single-process use).
  Unix sockets are not implemented; TCP works everywhere.

## Core to UI

| `type` | Fields | When |
| --- | --- | --- |
| `hello` | `version`, `caps`, `sequences` (id to localized names), `timings` (id to `prep_s`, `shoot_s`, `warn_s`) | on connect |
| `link` | `status` (`up`/`down`), `fw`, `chip` | on connect (if known) and on change |
| `state` | `state`: full snapshot (see `core/models.py` `Snapshot`) | on connect and on every change |
| `audio` | `local`, `mcu`, `volume`, `device`, `devices`, `local_available`, `busy`, `testing` | on connect and on every change (see Sound) |
| `node` | `role`, `active_role`, `leader`, `leaders`, `espnow`, `lights`, `locked`, `busy`, `restart_needed` | on connect and on change: network role (see `cluster.md`) |
| `roster` | `devices`, `master`, `conflict` | the timer network: LAN cores, radio modules, remotes; `conflict` names two main timers |
| `remotes` | `remotes`, `pairing_open`, `seconds_left`, `pending` | paired radio remotes, pairing window, requests waiting for the operator |
| `followers` | `followers` | leader only: followers with status `approved`/`pending`/`blocked`, rights, connected |
| `follower` | `status`, `perms`, `preset`, `leader` | follower core to its own UIs: its access state |
| `denied` | `name` | a command was refused for lack of permission |

`hello` also carries `master_id` and `master_session` (the leader's radio identity). `link` also carries `espnow`
(mode, peers, source), `upstream` (`down` on a follower that lost its leader), `via` (`radio` for a radio-only
follower) and, on a follower, `leader_rtt_ms` / `leader_offset_ms`.

A new client receives `hello`, then `link`, `audio`, then the latest `state` (and the other replayed messages), so a restarted UI
recovers exactly. `state` never carries "remaining seconds": it carries `phase_start_ns` and
`deadline_ns` from the shared monotonic clock, and the UI computes remaining time per frame.
When `paused` or `emergency` is set, use `remaining_at_pause_ns`.

## UI to core

| `type` | Fields | Effect |
| --- | --- | --- |
| `cmd` | `name`, `args` | see below |
| `ping` | `id`, `t0` (sender's clock) | core answers `pong` (`id`, `t0`, `t1` = core clock), used for clock offset (see `docs/ui.md`) |
| `settings` | `values` | core settings: `emergency_blasts`, `blast_ms`, `gap_ms`, `whistle_timing` (`mcu`/`host`), `pause_light`; sound: `sound_local`, `sound_mcu`, `volume`, `audio_device`; network: `node_role`, `node_leader`, `espnow`, `lights`, `node_name` |

Commands: `configure` (`sequence_id`, `groups`, `total_ends`, `practice_ends`,
`alternate_order`, `auto_advance`, `auto_advance_delay_s`), `start`, `pause`, `resume`,
`stop_end`, `next`, `back`, `reset`, `emergency`, `primary` (start the waiting end or resume a paused one), `clear_emergency` (`mode`: `continue` or
`restart`). Also: `sound_test`; network `apply_network`, `take_over` (this device becomes the main timer); radio remotes
`pair_open`, `pair_close`, `pair_accept`, `pair_reject`, `remote_remove`, `remote_perms`, `radio_reset_key` (new mesh key for the whole radio network), `radio_forget_key` (this device forgets its keys and pairs again); followers
`follower_approve`, `follower_perms`, `follower_block`, `follower_remove`. Invalid or inapplicable commands are ignored and
logged; they never stop the engine.

## Between cores (leader and follower)

A follower core connects to the leader like a UI and also sends `join` (`id`, `name`) and `auth` (`id`, `mac`); the leader
answers with `access` and `challenge`. The leader streams `event` messages (light, whistle, buzzer) so the follower can
drive its own hardware. What a follower may do is checked per message (`ipc/access.py`); see `cluster.md`.

## Network use

`--host 0.0.0.0` makes the core listen on all interfaces so UI clients on other machines can
connect (`ui_client --host <core IP>`). The socket is not encrypted. A remote client is watch-only unless the leader
has approved it (`cluster.md`); use a trusted network. Remote clients measure the clock offset with `ping`/`pong`.

## Behaviour guarantees

- The engine thread only does a queue put per client; a slow, hung or dead UI cannot delay
  the engine or the serial worker. A client more than 1000 messages behind is dropped and can
  reconnect.
- Event order out of the engine is preserved: serial worker first, then IPC.
- The core keeps running with no UI attached. Killing and restarting the UI mid-end loses
  nothing (tested over both transports).

## Running

```text
python -m archerytimer.core_service [--no-serial] [--serial-port COM7] [--tcp-port 8765]
```

Raises priority (Linux `nice`, Windows above-normal) and can pin a CPU (`--cpu`), all best
effort. Ctrl+C or SIGTERM sends RED and silence before exit. Logs rotate under the per-user
data dir (`logs/core.log`).

## Sound

`audio` carries `busy` (an end runs or an emergency is active). UIs change sound with a `settings` message
carrying `sound_local`, `sound_mcu`, `volume` (0-1) or `audio_device`, and start the test with `cmd` `sound_test`. These are handled by the node's own `AudioControl`; a follower does not
forward them to the leader.

# IPC: core service <-> UI client (v1)

Newline-delimited JSON, one object per line, each with `type` and `v` (protocol version).
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

A new client receives `hello`, then `link`, `audio`, then the latest `state`, so a restarted UI
recovers exactly. `state` never carries "remaining seconds": it carries `phase_start_ns` and
`deadline_ns` from the shared monotonic clock, and the UI computes remaining time per frame.
When `paused` or `emergency` is set, use `remaining_at_pause_ns`.

## UI to core

| `type` | Fields | Effect |
| --- | --- | --- |
| `cmd` | `name`, `args` | see below |
| `ping` | `id`, `t0` (sender's clock) | core answers `pong` (`id`, `t0`, `t1` = core clock), used for clock offset (see `docs/ui.md`) |
| `settings` | `values` | core settings: `emergency_blasts`, `blast_ms`, `gap_ms`, `whistle_timing` (`mcu`/`host`), `pause_light` |

Commands: `configure` (`sequence_id`, `groups`, `total_ends`, `practice_ends`,
`alternate_order`, `auto_advance`, `auto_advance_delay_s`), `start`, `pause`, `resume`,
`stop_end`, `next`, `back`, `reset`, `emergency`, `primary` (start the waiting end or resume a paused one), `clear_emergency` (`mode`: `continue` or
`restart`). Invalid or inapplicable commands are ignored and logged; they never stop the engine.

## Network use

`--host 0.0.0.0` makes the core listen on all interfaces so UI clients on other machines can
connect (`ui_client --host <core IP>`). The protocol has no authentication; use a trusted
network only. Remote clients measure the clock offset with `ping`/`pong`.

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

## Sound (M7)

`audio` (core to UI, on connect and on every change): `local`, `mcu`, `volume`, `device`, `devices`,
`local_available`, `busy` (an end runs or an emergency is active), `testing`. UIs change sound with a
`settings` message carrying `sound_local`, `sound_mcu`, `volume` (0-1) or `audio_device`, and start the
test with `cmd` `sound_test`. These are handled by the node's own `AudioControl`; a follower does not
forward them to the leader.

# Project structure: what is where

Reference map for the repository (root `E:\HarnoArcheryTimer`). The spec and rules are in
`CLAUDE.md`; this file only says where things live and how they connect. Keep it current when files
move or a new module appears.

## Processes and data flow

```text
core_service (headless)                          ui_client (one per display)
  EngineRunner thread -> Engine (core/)  --state/event-->  IpcServer ==socket/inproc==> CoreLink
       |   emit(LightChange|Whistle|Buzzer|Snapshot)                                     |
       +--> SerialWorker (hardware/) --$ frames--> MCU        UiApp: sections + screens <-+
       +--> AudioControl -> AudioWorker (audio/) -> speakers      commands/settings go back as
       +--> IpcServer.publish(state / event / link / audio)       `cmd` / `settings` messages
```

Dependency direction: `common` <- `core` <- (`hardware`, `audio`, `ipc`) <- `core_service`;
`ui_client` depends only on `common`, `core.models` and `ipc`. Nothing imports `ui_client`.

## src/archerytimer/

| Path | What it holds |
| --- | --- |
| `common/clock.py` | `Clock`, `MonotonicClock`, `FakeClock` (all timing goes through these) |
| `common/compat.py`, `paths.py`, `i18n.py` | `SLOTS` dataclass helper; per-user data dir + rotating logs; `Translator` (TOML locales, sv first, en fallback) |
| `core/models.py` | Immutable dataclasses: `Light`, `Mode`, `PhaseSpec`, `Sequence`, `SessionConfig`, `EngineSettings`, events (`LightChange`, `Whistle`, `Buzzer`), `Snapshot`, `Command` |
| `core/engine.py` | The deadline FSM: rounds, phases, pause, emergency, back, skip, reset, line rotation, whistle events |
| `core/scheduler.py`, `engine_runner.py`, `cli.py` | Heap scheduler; engine thread; CLI that runs a session and prints events |
| `core/rules.py` | Sequence TOML loader, `apply_overrides` (per-session prep/shoot/warn), `timing_info` |
| `hardware/protocol.py` | Serial protocol v1: frames, checksum, parser (pure functions, mypy strict) |
| `hardware/serial_worker.py` | Writer thread, heartbeat, ACK watchdog, reconnect, MCU sound toggle, `$S` ids and repeats |
| `hardware/discovery.py`, `sim_device.py` | USB VID/PID port discovery; simulated MCU (memory/pty ports, proto 1 and 2) |
| `hardware/mesh_types.py`, `mesh_codec.py` | Mesh v2 contract types (serial frames, radio payloads) and the Python radio frame codec (header, HMAC tag, dedupe, pairing blob) |
| `audio/synth.py` | Synthesized horn (blast and steady tone), no sample files needed |
| `audio/audio_worker.py` | `AudioWorker` thread, `PygameBackend`, `NullBackend`, `make_backend`, `list_devices` |
| `audio/settings.py` | `AudioSettings` (local, mcu, volume, device) and its JSON store |
| `ipc/messages.py` | Message builders/parsers: `hello`, `state`, `link`, `audio`, `event`, `cmd`, `settings`, `ping/pong` |
| `ipc/server.py`, `link.py`, `clocksync.py` | `IpcServer` (replays latest `link`/`audio`/`state` to new clients); `CoreLink` client with reconnect and clock offset; offset estimator |
| `ipc/transport*.py` | Transport interface; socket (TCP) and in-process implementations |
| `core_service/service.py` | `CoreService` (leader): wires engine, serial, audio, IPC; `translate()` of commands |
| `core_service/cluster.py` | `FollowerService`: mirrors a leader's events onto its own MCU/speakers, forwards commands, fails safe |
| `core_service/audio_control.py` | `AudioControl`: sound settings, MCU on/off, sound test; used by leader and follower |
| `core_service/node.py`, `netdisco.py`, `roster.py`, `remotes.py` | Role and takeover; beacon v2 and instance browser; the timer-network roster (LAN + radio, conflict); paired remotes, pairing window, permissions |
| `ipc/access.py`, `core_service/followers.py` | Follower access: permissions and presets, auth MAC, message gate; the leader's registry of followers (approval, per-follower key, rights, persistence) |
| `core_service/meshfeed.py`, `radio_keys.py`, `radio_service.py`, `mesh_follower.py` | `$U`/`$J` encoding for the radio; mesh key and node id; radio-only follower service (`--leader radio`); rebuilds snapshots from the radio feed |
| `core_service/inputs.py` | Physical buttons (MCU `$K`, optional Pi GPIO) mapped to engine commands |
| `core_service/__main__.py` | Core entry point (`--leader`, `--espnow`, `--no-audio`, `--no-serial`...) |
| `launcher.py` | Desktop convenience: starts core and UI together |
| `ui_client/__main__.py`, `app.py` | UI entry point; `UiApp` frame loop, dispatch, screens stack, idle, undo, display prefs |
| `ui_client/context.py` | `ViewContext` plus pure view helpers: countdown text, `light_view`, `buttons_for` |
| `ui_client/sections/` | Cached, dirty-tracked sections: `traffic_light`, `countdown`, `info_panel`, `operator_bar`, `status_bar`, `screen_section` (hosts screens), `idle_section` |
| `ui_client/screens/` | Operator screens: `setup` (wizard + Advanced), `menu` (menu, settings, hardware, help), `timers`, `sound`, `confirm`; `base` has layout helpers |
| `ui_client/widgets/__init__.py` | Declarative `Widget`, drawing and hit-testing |
| `ui_client/renderer/` | `base` interface, `gpu` (SDL renderer), `software` fallback |
| `ui_client/layout.py`, `theme.py`, `fonts.py` | Relative section rects per profile; colours; font cache (Inter from `assets/fonts`, else pygame default) |
| `ui_client/input.py`, `prefs.py`, `presets.py`, `core_link.py` | Key/joystick maps; UI prefs JSON; preset and timing TOML loaders; re-export of `ipc/link.py` |

## Config, assets, locales

| Path | What |
| --- | --- |
| `config/default_settings.toml` | Button bindings, `[node]` (leader/ESP-NOW), `[audio]` first-run defaults, keys/joystick overrides |
| `config/sequences/*.toml` | Phase sequences (PREP, SHOOT, END). Placeholder timings |
| `config/presets/default.toml`, `timings.toml` | Setup cards; quick timer lengths. Clubs add files in `<user data dir>/presets/` |
| `locales/sv.toml`, `en.toml` | Every user-facing string (keys must match in both) |
| `assets/fonts/` | Inter Bold + `OFL.txt`; any `.ttf/.otf` placed here is used |
| `assets/sounds/` | Empty: the horn is synthesized. Reserved for optional samples |
| User data dir (platformdirs) | `logs/`, `ui_prefs.json` (UI), `core_audio.json` (core sound settings), `presets/` |

## Firmware, scripts, docs, tests

| Path | What |
| --- | --- |
| `firmware/esp32s3/`, `esp32c3/` | PlatformIO v1 firmware split into `config/outputs/hostlink/buttons/radio` + `main.cpp` (the C3 shares the S3 sources). Builds; never flashed |
| `firmware/esp32/` | Classic ESP32-WROOM-32D project (envs `esp32-wroom-32d`, `-standalone`; UART bridge, no native USB); shares the S3 sources. Variants and pin maps: `docs/firmware.md` |
| `scripts/flash.py`, `flash.bat`, `flash.sh`, `scripts/flash_tool/` | ESP32 flashing menu (stdlib only; own `.flash-env/` with esptool; PlatformIO only on demand). Guide and dependency evaluation: `docs/flashing.md` |
| `firmware/release/` | Generated merged images (`<env>.bin`) and `manifest.json` for all six variants; rebuild and keep when the firmware changes (menu entry 'Create release images') |
| `firmware/lib/meshcore/`, `firmware/test/native/` | Portable C++ mesh v2 core (codec, HMAC, dedupe, arbiter, CMD gate, pairing HMAC) and its native tests (MSVC run, 352 checks); not yet linked into the firmware |
| `firmware/*_vectors*.txt`, `arbiter_scenarios.txt` | Serial v1/v2 and radio vectors, arbiter scenarios shared by C++ and Python |
| `tools/mesh_sim/`, `tests/mesh_sim/` | Mesh simulator (lossy radio, reboots, two masters, remotes) and Python arbiter |
| `firmware/test_vectors.txt` | Protocol vectors shared by Python tests and firmware |
| `scripts/` | `render_benchmark`, `jitter_benchmark`, `ui_benchmark`, `latency_probe`, `env_probe` (+ `_benchutil`, `_scene`); `install_pi.sh`, `uninstall_pi.sh`, `systemd/` (core and UI units, env examples, journald cap; M8) |
| `docs/` | `protocol.md`, `ipc.md`, `ui.md`, `audio.md`, `cluster.md`, `espnow.md`, `deployment.md`, `benchmarks.md`, `results/`, `decisions/` |
| `tests/` | Mirrors `src/`: `core`, `hardware`, `audio`, `ipc`, `core_service`, `ui_client`, `scripts`, `deploy` (static checks of units/scripts); fixtures in `conftest.py` |

## Where to change what

| Task | Start here |
| --- | --- |
| New engine command | `core/engine.py` (`handle`), `core_service/service.py` (`SIMPLE_COMMANDS`/`translate`), `ui_client/app.py` (`_SIMPLE_ACTIONS`) |
| New serial frame | `hardware/protocol.py`, `firmware/test_vectors.txt`, `sim_device.py`, `firmware/.../main.cpp`, `docs/protocol.md` |
| New IPC message | `ipc/messages.py`, `ipc/link.py` (`drain`), `ipc/server.py` if it must be replayed, `docs/ipc.md` |
| New operator screen | `ui_client/screens/` (subclass `Screen`), register in `menu.py`, strings in both locales |
| New preset / timing / sequence | TOML in `config/presets/` or `config/sequences/`; no code |
| Sound behaviour | `audio/`, `core_service/audio_control.py`, `ui_client/screens/sound.py` |
| Key bindings | `ui_client/input.py` (`DEFAULT_KEYS`), `config/default_settings.toml` |

## Tooling

Venv `.venv` (Python 3.14, pygame-ce); on Windows use `.venv\Scripts\python.exe`. Install with
`pip install -e ".[dev]"`. Lint/format: `ruff check --fix src tests scripts`, `ruff format`; types:
`mypy`; tests: `pytest -q` (headless UI uses `SDL_VIDEODRIVER=dummy`, set in the test conftests).

## Top-level docs and install scripts

`README.md` (English) and `README.sv.md` (Swedish) are the entry points. Install guides: `docs/install/{windows,linux,raspberry-pi}[.sv].md`; index: `docs/README.md`. Desktop scripts: `scripts/setup_windows.bat`, `start_windows.bat`, `setup_desktop.sh`, `start.sh`. `.gitignore` excludes `.venv`, caches and `.claude/settings.local.json`.

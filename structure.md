# Project structure: what is where

Reference map for the repository. The spec and rules are in `CLAUDE.md`; this file says where things live and
how they connect. Keep it current when files move or a new module appears.

## Processes and data flow

```text
core_service (headless)                          ui_client (one per display)
  EngineRunner thread -> Engine (core/)  --state/event-->  IpcServer ==socket/inproc==> CoreLink
       |   emit(LightChange|Whistle|Buzzer|Snapshot)                                     |
       +--> SerialWorker (hardware/) --$ frames--> ESP32      UiApp: sections + screens <-+
       +--> AudioControl -> AudioWorker (audio/) -> speakers      commands/settings go back as
       +--> IpcServer.publish(state / event / link / audio / ...)  `cmd` / `settings` messages
       +--> node, roster, remotes, followers (LAN and radio)
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
| `hardware/protocol.py` | Serial protocol v1 and v2: frames, checksum, parser (pure functions, mypy strict) |
| `hardware/serial_worker.py` | Writer thread, heartbeat, ACK watchdog, reconnect, MCU sound toggle, `$S` ids and repeats, v2 role/config/pairing frames |
| `hardware/discovery.py`, `sim_device.py` | USB VID/PID port discovery (rotates through all candidates); simulated MCU (memory/pty ports, proto 1 and 2) |
| `hardware/mesh_types.py`, `mesh_codec.py` | Mesh contract types (serial frames, radio payloads) and the Python radio frame codec (header, HMAC tag, dedupe, pairing blob) |
| `audio/synth.py` | Synthesized horn (blast and steady tone), no sample files |
| `audio/audio_worker.py` | `AudioWorker` thread, `PygameBackend`, `NullBackend`, `make_backend`, `list_devices` |
| `audio/settings.py` | `AudioSettings` (local, mcu, volume, device) and its JSON store |
| `ipc/messages.py` | Message builders/parsers: `hello`, `state`, `link`, `audio`, `event`, `node`, `roster`, `remotes`, `followers`, `follower`, `join`/`challenge`/`auth`/`access`/`denied`, `cmd`, `settings`, `ping/pong` |
| `ipc/server.py`, `link.py`, `clocksync.py` | `IpcServer` (replays latest `link`/`audio`/`state`/... to new clients, gates remote clients); `CoreLink` client with reconnect and clock offset; offset estimator |
| `ipc/access.py` | Follower rights: permissions, presets, auth MAC, `required_perm` message gate |
| `ipc/transport*.py` | Transport interface; socket (TCP) and in-process implementations |
| `core_service/service.py` | `CoreService` (leader): wires engine, serial, audio, IPC; `translate()` of commands |
| `core_service/cluster.py` | `FollowerService`: mirrors a leader's events onto its own MCU/speakers, forwards commands, fails safe |
| `core_service/audio_control.py` | `AudioControl`: sound settings, MCU on/off, sound test; used by leader and follower |
| `core_service/node.py` | Role (alone / leader / follower / radio only), stored choice, Apply, manual takeover, radio key reset |
| `core_service/netdisco.py`, `roster.py` | UDP beacon and LAN instance browser; the timer-network roster (LAN + radio) and conflict detection |
| `core_service/remotes.py` | Paired radio remotes, pairing window and discovery, per-remote rights |
| `core_service/followers.py` | The leader's registry of LAN followers: approval, per-follower key, rights, persistence |
| `core_service/meshfeed.py`, `radio_keys.py`, `radio_service.py`, `mesh_follower.py` | `$U`/`$J` encoding for the radio; mesh key, node id and session counter; radio-only follower service (`--leader radio`); rebuilds snapshots from the radio feed |
| `core_service/inputs.py` | Physical buttons (MCU `$K`, optional Pi GPIO) mapped to engine commands |
| `core_service/__main__.py` | Core entry point (`--leader`, `--espnow`, `--host`, `--no-audio`, `--no-serial`...) |
| `launcher.py` | Desktop convenience: starts core and UI together |
| `ui_client/__main__.py`, `app.py` | UI entry point; `UiApp` frame loop (logs exceptions, drops open screens, keeps drawing), dispatch, screen stack, idle, undo, display prefs |
| `ui_client/context.py` | `ViewContext` plus pure view helpers: countdown text, `light_view`, `buttons_for` |
| `ui_client/sections/` | Cached, dirty-tracked sections: `traffic_light`, `countdown`, `info_panel`, `operator_bar`, `status_bar`, `screen_section` (hosts screens), `idle_section` |
| `ui_client/screens/` | Operator screens: `setup` (wizard + Advanced), `menu` (menu, settings, hardware, help), `timers`, `sound`, `confirm`, `network` (role, roster), `remotes` (pairing, rights), `followers` (approval, rights); `base` has layout helpers |
| `ui_client/widgets/__init__.py` | Declarative `Widget`, drawing and hit-testing |
| `ui_client/renderer/` | `base` interface, `gpu` (SDL renderer, overlays for everything that ticks), `software` fallback |
| `ui_client/layout.py`, `theme.py`, `fonts.py` | Relative section rects per profile; colours; font cache (Inter from `assets/fonts`, else pygame default) |
| `ui_client/input.py`, `prefs.py`, `presets.py`, `core_link.py` | Key/joystick maps; UI prefs JSON; preset and timing TOML loaders; re-export of `ipc/link.py` |

## Config, assets, locales

| Path | What |
| --- | --- |
| `config/default_settings.toml` | Button bindings, `[node]` (leader/ESP-NOW), `[audio]` first-run defaults, keys/joystick overrides |
| `config/sequences/default.toml` | Phase sequences (PREP, SHOOT, END). Placeholder timings |
| `config/presets/default.toml`, `timings.toml` | Setup cards; quick timer lengths. Clubs add files in `<user data dir>/presets/` |
| `locales/sv.toml`, `en.toml` | Every user-facing string (keys must match in both) |
| `assets/fonts/` | Inter Bold + `OFL.txt`; any `.ttf/.otf` placed here is used |
| `assets/sounds/` | Empty: the horn is synthesized |
| User data dir (platformdirs) | `logs/`, `ui_prefs.json` (UI), `core_audio.json` (sound), `core_node.json` (network role), radio keys and session counter, follower and remote registries, `presets/` |

## Firmware

| Path | What |
| --- | --- |
| `firmware/esp32s3/src/` | The one shared firmware source set: `config`, `outputs`, `hostlink`, `hostmsg`, `buttons`, `beep`, `radio`, `meshglue`, `version.h`, `main.cpp` |
| `firmware/esp32s3/`, `esp32c3/`, `esp32/` | PlatformIO projects (C3 and classic ESP32 only hold a `platformio.ini` pointing at the S3 sources). Six variants, pins and wiring: `docs/firmware.md` |
| `firmware/lib/meshcore/` | Portable C++ mesh core (frame codec, HMAC, dedupe, arbiter, command gate, pairing, X25519); its README lists what a device build must provide |
| `firmware/lib/hostcore/` | Portable C++ serial frame handling |
| `firmware/test/native/` | Native C++ tests (MSVC or g++) replaying the shared vectors |
| `firmware/*_vectors*.txt`, `arbiter_scenarios.txt` | Serial v1/v2 vectors, radio vectors and arbiter scenarios shared by C++ and Python |
| `firmware/release/` | Generated merged images (`<env>.bin`) and `manifest.json` for the six variants; rebuild and commit when the firmware changes (flash menu entry 3) |
| `tools/mesh_sim/`, `tests/mesh_sim/` | Mesh simulator (lossy radio, reboots, two masters, remotes) and the Python arbiter |

## Scripts

| Path | What |
| --- | --- |
| `scripts/setup_windows.bat`, `start_windows.bat`, `setup_desktop.sh`, `start.sh` | Desktop install and start (the Linux setup also grants serial access) |
| `scripts/install_pi.sh`, `uninstall_pi.sh`, `run_ui_tty1.sh`, `deploy_to_pi.ps1`, `systemd/` | Pi kiosk install: core unit, optional UI unit, env examples, journald cap; deploy from Windows |
| `scripts/flash.py`, `flash.bat`, `flash.sh`, `flash_tool/` | ESP32 flashing menu (stdlib only; own `.flash-env/` with esptool; PlatformIO only on demand). Guide: `docs/flashing.md` |
| `scripts/hw_e2e_two_boards.py` | Hardware test with two real boards (not in the unit suite) |
| `scripts/render_benchmark.py`, `jitter_benchmark.py`, `ui_benchmark.py`, `latency_probe.py`, `env_probe.py`, `profile_paint.py` (+ `_benchutil`, `_scene`) | Measurement scripts; results in `docs/benchmarks.md` and `docs/results/` |

## Docs and tests

| Path | What |
| --- | --- |
| `README.md`, `README.sv.md` | Entry points (English, Swedish) |
| `docs/README.md` | Index. `install/` has Windows, Linux and Pi guides in English and Swedish |
| `docs/` | `ui`, `audio`, `cluster`, `mesh`, `firmware`, `flashing`, `protocol`, `ipc`, `deployment`, `benchmarks`, `results/`, `decisions/` (design records) |
| `tests/` | Mirrors `src/`: `core`, `common`, `hardware`, `audio`, `ipc`, `core_service`, `ui_client`, `mesh_sim`, `scripts`, `deploy` (static checks of units/scripts); fixtures in `conftest.py` |

## Where to change what

| Task | Start here |
| --- | --- |
| New engine command | `core/engine.py` (`handle`), `core_service/service.py` (`SIMPLE_COMMANDS`/`translate`), `ui_client/app.py` (`_SIMPLE_ACTIONS`) |
| New serial frame | `hardware/protocol.py`, the vector files in `firmware/`, `sim_device.py`, `firmware/lib/hostcore`, `firmware/esp32s3/src/main.cpp`, `docs/protocol.md` |
| New radio frame or arbiter rule | `docs/mesh.md`, `firmware/lib/meshcore`, `hardware/mesh_codec.py`, `tools/mesh_sim`, the vector and scenario files |
| New IPC message | `ipc/messages.py`, `ipc/link.py` (`drain`), `ipc/server.py` if it must be replayed or gated, `docs/ipc.md` |
| New operator screen | `ui_client/screens/` (subclass `Screen`), register in `menu.py`, strings in both locales |
| New preset / timing / sequence | TOML in `config/presets/` or `config/sequences/`; no code |
| Sound behaviour | `audio/`, `core_service/audio_control.py`, `ui_client/screens/sound.py` |
| Key bindings | `ui_client/input.py` (`DEFAULT_KEYS`), `config/default_settings.toml` |
| Firmware change | Edit, bump `version.h`, rebuild release images (flash menu 3), commit `firmware/release/` |

## Tooling

Venv `.venv` (Python 3.14, pygame-ce); on Windows use `.venv\Scripts\python.exe`. Install with
`pip install -e ".[dev]"`. Lint/format: `ruff check --fix src tests scripts`, `ruff format`; types: `mypy`;
tests: `pytest -q` (headless UI uses `SDL_VIDEODRIVER=dummy`, set in the test conftests). Native firmware tests:
`cd firmware/test/native && cmd /c .\run_tests.bat` (Windows) or `sh run_tests.sh`. `.gitignore` excludes `.venv`,
caches, `.pio/` and `.claude/`; `.flash-env/` is the flashing tool's own environment.

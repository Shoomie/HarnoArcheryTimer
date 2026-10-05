# Archery Timing & Display System – Project Spec

Open-source, cross-platform, low-latency archery timer: runs the shooting clock at competitions and
training, shows it on a TV/monitor, and drives lights and sound over USB serial. Used by a small
Swedish club, operated by non-technical volunteers. Python 3.9+, pygame-ce, pyserial.

Where things are: **`structure.md`**. Detail docs: `docs/` (index in `docs/README.md`: `ui`, `audio`, `cluster`, `mesh`,
`firmware`, `flashing`, `protocol`, `ipc`, `deployment`, `benchmarks`, `install/`, `decisions/`). Entry points for humans:
`README.md` (English, the source) and `README.<code>.md` in 10 more languages (sv zh hi es fr ar bn pt ru ur).

## Working agreement

- Plan briefly, then build one piece at a time; end each in a working, reviewable state.
- **Never invent archery rules or timings.** Everything rule-like is config (TOML) and flagged as a
  placeholder until the user confirms it against World Archery / SBF rules.
- Measure, don't assume: latency and performance claims need the benchmark/probe scripts (ideally on a real Pi 2B).
- Correctness and safety over features: timer, lights and sound must be right every time.
- Keep this file concise and current; propose edits when a decision changes the spec.
- The user wants progress, not exhaustive testing: run the suite once at milestone end, not after every edit.
  No git operations unless asked.

## Targets and priorities

Priority order: (1) timer correctness and hardware output timing, (2) stability and fail-safe behaviour,
(3) ease of use, (4) visual polish.

Primary target: **Raspberry Pi 2 Model B**, Pi OS Lite 32-bit (Trixie), SDL2 KMSDRM kiosk, no X11,
ALSA audio, systemd core service, UI started on tty1. Must also run on Windows 10/11, desktop Linux, and (nice to have) macOS. Any
resolution/aspect ratio; 1080p60 baseline; layout scales, nothing hardcoded in pixels.

| Requirement | Target |
| --- | --- |
| State change to USB write | < 2 ms typical, < 5 ms worst |
| State change to MCU acting | < 5-10 ms end to end |
| Timer drift over 4 h | 0 (deadline-based) |
| Event lateness under UI load (Pi 2B) | < 2 ms p99 |
| UI | 60 fps when animating; renders only on change; low idle CPU |
| UI crash/freeze | Timer, lights, sound continue |
| Lost USB link | MCU goes RED and silent within ~1 s |

Hard rules:
- Hardware commands are emitted by the engine at the logical state change, **never** from the render loop.
- Serial I/O never blocks the UI; UI never delays serial or the engine.
- No timing depends on frame rate, `sleep` accuracy or tick counting. Use `monotonic_ns` through an injectable clock.
- RED and silence is the safe state after any error, shutdown or lost contact.

## Architecture

Two processes: a headless **core service** (engine thread, serial worker, audio worker, IPC server) and a
**UI client** (SDL renderer, input) that holds no timing authority. Core imports nothing from UI.

- Engine: data-driven FSM with absolute deadlines (`deadline_ns`); pause stores remaining time; late wake-ups
  fire overdue events in order. Outputs are states ("lights are GREEN"), not toggles. Overrides in any state:
  emergency (RED, 5+ blasts, explicit exit: continue or restart), pause/resume, stop end, next, back, reset.
- Sessions: line rotation (AB/CD etc., alternating start order), end counter, practice ends, per-session
  prep/shoot/warn overrides, optional auto-advance. Finals/matchplay shot clocks are v2.
- IPC: JSON lines over a socket (TCP, or in-process for tests/single-process). Core sends `hello`, `state`
  (full snapshot incl. phase **deadline**; UI computes remaining time per frame with a measured clock offset),
  `link`, `audio`, `event`; UI sends `cmd` and `settings`. The UI goes RED after 1 s without the core.
- UI rendering: sectioned and cached; redraw only dirty sections on the CPU, recompose cached textures on
  the GPU (SDL renderer; software fallback). Present only when something changed; sleep until the next input,
  IPC message or second boundary. No full-screen CPU blits, no gradients/alpha/animations that cost frames.
- Multi-device: one leader core runs the engine; follower cores mirror hardware events and state onto their
  own MCU/speakers, forward commands, and fail safe without a leader (`docs/cluster.md`). A new LAN follower is
  watch-only until the leader's operator approves it (per-follower key, rights preset plus toggles; emergency always
  passes). ESP32 modules also sync over an ESP-NOW radio mesh with a named master, HMAC-signed frames and
  operator-accepted pairing of remotes and radio-only followers (`docs/mesh.md`, ADR `0002`). All devices
  synchronized, any can run commands (within its rights), any can have lights/sound.
- Inputs resolve to engine commands (`primary` is resolved by the engine): keyboard/clickers and mouse in the
  UI; MCU buttons (`$K`) and optional Pi GPIO in the core.

## Serial protocol (`docs/protocol.md`)

Line-based ASCII, NMEA-style XOR checksum, 115200 baud: `$<CMD>[,args]*<XX>\n`. Host to MCU: `$L` lights,
`$S` whistle (MCU-timed; optional id for de-duplicated repeats, capability `W`), `$B` buzzer, `$G` group, `$T`
time, `$H` heartbeat (every 200 ms, full state), `$V` hello, `$M` ESP-NOW mode (legacy). MCU to host: `$I` hello reply
(caps `LSBGTKNWR`), `$A` ACK, `$E` error, `$K` button, `$N` ESP-NOW status. Commands are idempotent state
assertions; MCU watchdog forces RED and silence after ~1 s without a valid frame. **Serial v2** (proto 2, cap `R`) adds
the mesh frames: `$R` role, `$C`/`$Q` config, `$U`/`$J` timer and session for the radio, `$P` pairing and remote
commands, `$O` status, `$D` roster, `$F`/`$W`/`$Y` radio feed. Shared vectors: `firmware/test_vectors.txt`,
`firmware/test_vectors_v2.txt`, `firmware/mesh_vectors.txt`, `firmware/arbiter_scenarios.txt`.

## Sound (`docs/audio.md`)

Two independent outputs: MCU horn (`$S`/`$B`, most precise, default) and local speakers (audio worker in the
core, synthesized horn, never in the UI). Per-core settings: each on/off, volume, output device; sound test
plays 1, 2, 3, 5 blasts and is blocked during an end or emergency. Whistle convention (placeholders to
confirm): 2 = to the line, 1 = start, 3 = stop, 5+ = emergency.

## Presets and competition features

All numbers are **placeholders to confirm** with WA/SBF rules. Presets are TOML (`config/presets/`), clubs
add their own. Built: Indoor 18 m (3 arrows), Outdoor qualification 6 and 3 arrows, Practice ends, Free
training. Not built: individual finals (alternating per-arrow clock), team/mixed team, shoot-off. Setup toggles:
line rotation, arrows and time per end, prep time, yellow warning threshold, ends and practice ends,
auto-advance, whistle counts, tenths in the last seconds, interface language (English default, Swedish).

## UX requirements

Benchmark: a volunteer who has never seen the program runs a full session after a 2-minute explanation.
- One main screen, one obvious action: the primary button always says what happens next.
- Emergency stop is always visible, one press, no confirmation, fixed place, keyboard Esc. It stays on screen
  under every menu; screens close on emergency.
- Destructive actions (reset, quit, replace session) use a confirm dialog; Cancel is the safe default.
- Readable at distance: huge digits, light colour field plus tick/!/X icons (not colour alone), plain words.
- Setup in three steps; last setup remembered; advanced toggles behind a separate page.
- Visible plain-language hardware status; no error codes. Everything works with mouse, keyboard and (later) touch.
- Operator vs audience view (`--profile audience` has no controls except emergency); idle clock screen when
  nothing runs (options in Settings); no distracting animation on the archers' view.

## Coding standards

- Type hints; mypy strict on `core/`, `ipc/`, `hardware/protocol.py`; ruff lint + format.
- Immutable dataclasses (`frozen=True`, via `SLOTS` helper for 3.9). No global mutable state; inject clock,
  transport, serial port. Cross-thread data only via `SimpleQueue` and immutable messages.
- Every thread has a clean shutdown (RED and silence first); `Ctrl+C`/SIGTERM safe (Windows has no SIGTERM:
  the MCU watchdog covers a hard kill).
- Structured rotating logs in the per-user data dir. No user-facing strings outside `locales/`; keep `sv` and
  `en` keys identical. `pathlib` everywhere; guard OS-specific calls.
- Tests: engine tests use `FakeClock` and never sleep; protocol tests use shared vectors; performance
  scripts and hardware tests (`scripts/hw_e2e_two_boards.py`) stay separate from the unit suite (results in
  `docs/benchmarks.md`).
- Docs: the READMEs and `docs/install/` are for volunteers (plain words). English is the source; keep the translations (`sv zh hi es fr ar bn pt ru ur`, files `*.<code>.md`) in step with it. How: `CONTRIBUTING.md`.
  Describe how things are, not how they came to be: no work-in-progress notes, change dates or milestone talk outside ADRs.
- Tooling: `.venv\Scripts\python.exe` on Windows (Python 3.14, pygame-ce 2.5.8). Multi-line edits are easiest
  as a small Python script in the scratchpad (big shell heredocs with quotes have failed). Headless UI needs
  `SDL_VIDEODRIVER=dummy` (set in test conftests). Firmware: PlatformIO builds, native C++ tests in
  `firmware/test/native`, flashing menu `scripts/flash.*` (`docs/flashing.md`); rebuild and commit `firmware/release/` and bump
  `firmware/esp32s3/src/version.h` when the firmware changes.

## State of the project

Everything below is built, tested and documented. Last full run: 792 Python tests collected (pty and bash-syntax tests skip on
Windows), native C++ tests pass, ruff and mypy clean.

| Area | What exists |
| --- | --- |
| Engine and CLI | Deadline FSM, line rotation, per-session overrides, emergency/pause/back/next/reset, auto-advance |
| Serial | Protocol v1 and v2, simulated MCU, serial worker with heartbeat/watchdog/reconnect, discovery across VID/PID candidates |
| Core service and IPC | Leader, LAN follower, radio-only follower, follower approval and rights, timer-network roster, wireless remotes, manual takeover |
| UI | Sectioned renderer (GPU overlays and software fallback), setup wizard, timers, menu, settings, hardware, sound, network, remotes, followers, confirm, idle screen, undo, audience profile, English (default) and Swedish interface; docs in 11 languages |
| Audio | Synthesized horn, MCU and local outputs, volume, device, sound test, repeat-safe `$S` ids |
| Firmware | `esp-0.4.0` for ESP32-S3, C3 Super Mini and WROOM-32D (host-attached and stand-alone variants), mesh v2, remote buttons, beeper; prebuilt images and a flashing menu |
| Deployment | `install_pi.sh` (console kiosk on tty1 or `--ui-mode service`), systemd core unit, journald cap, deploy script, desktop setup/start scripts for Windows and Linux |

**Verified on real hardware:** the demo set-up (Windows master, Fedora and Raspberry Pi 2B followers, ESP32-C3 Super Mini
modules, WROOM-32D remote), plus `scripts/hw_e2e_two_boards.py` (34 checks, two C3 boards, no network).

**Not verified:** a 4 h soak and unplug / UI-crash tests under load; ESP32-S3 boards; ESP-NOW range and loss in the field;
GPIO buttons on a Pi; touchscreen and gamepad; multi-monitor placement; macOS; the Pi 2B runs of `docs/benchmarks.md`
(the kiosk renders smoothly, but no run is recorded).

**Known gaps / placeholders:** rule timings, preset ends and line options (what ABC/ABCD mean), the "Träning" preset;
whistle blast length lives in engine settings (no UI yet); fullscreen/monitor choice is a start-up flag; no automatic leader
failover (manual takeover only); Windows has no SIGTERM (the MCU watchdog covers a hard kill); a whistle pattern started
from a radio heartbeat after a lost SOUND frame can start up to 400 ms late; the LAN link is unencrypted (trusted network).

## Decisions

- Repo root is `E:\HarnoArcheryTimer`. `common/clock.py` is shared with the benchmarks. The jitter benchmark's two-process
  mode is a throwaway spike.
- `slots=True` needs Python 3.10, so messages use `@dataclass(frozen=True, **SLOTS)`. Protocol has an internal error code `MF`
  (framing garbage, never sent). Only heartbeats are ACKed. `$S` is an event, made safe with optional ids (cap `W`) and host repeats.
- Inputs: mouse + keyboard now, touch later; clickers are HID keyboards; MCU buttons (`$K`) and Pi GPIO live in the core. One UI
  process per display (`--display`, `--profile`); remote UIs measure a clock offset.
- UI: screens keep a banner and the operator bar visible; sound settings belong to the core; the horn is synthesized (no licensed
  sample); UI font is Inter Bold (SIL OFL). Ticking elements are GPU overlays because per-pixel CPU painting is slow on a Pi 2B.
  `SDL_RENDER_DRIVER=opengles2` is forced on the Pi.
- Pi: the sudo user becomes the kiosk user (core as that user, tty1 autologin, `~/.profile` runs `scripts/run_ui_tty1.sh`);
  apt `python3-pygame` (has KMSDRM). `touch ~/.no-kiosk` gives a shell.
- Mesh (`docs/decisions/0002-mesh-and-firmware.md`): one firmware image, behaviour from stored config plus the host's `$R` role; named
  master with rank and stickiness and a conflict banner; HMAC mesh key plus per-remote keys with operator-accepted pairing and
  per-remote rights; fixed remote pinout and actions (1 start/next, 2 pause, 3 stop end, 4 emergency); radio-fed software follower;
  single hop, manual takeover, no automatic failover; persisted session counter against replays; safety-direction repeats.
- ADR `0001`: Python + pygame-ce, two processes.

## Resume here (new instance)

Read this file, `structure.md`, then the doc for the area you touch. Do not re-verify finished work. Candidate next work: long-run
hardening (4 h soak, unplug and UI-crash tests, `docs/benchmarks.md` on a Pi 2B), an operator guide with screenshots, and the
open questions below. Ask the user only about leader failover, exact rule timings and light/horn hardware.

## Licence

MIT (`LICENSE`), chosen so anyone can use, change and redistribute it everywhere, including commercially. Third-party parts
and their licences: `THIRD_PARTY_NOTICES.md`. Only add dependencies, fonts or assets under licences that allow free
redistribution; keep the licence text next to bundled files.

## Open questions

- [ ] **Exact rule timings** (prep, end times, warning, whistle conventions, finals) against current WA/SBF rules.
- [ ] **Light and horn hardware:** driver stage (MOSFET/relay), pull-downs on the outputs, which lamps and horn.
- [ ] **Leader failover:** followers go RED and silent when the leader dies. Automatic takeover (and by whom), or manual only?
- [ ] **Windows timing target:** is < 2 ms p99 also required on Windows, or Pi only?
- [ ] **CI:** GitHub Actions (ruff, mypy, pytest on Ubuntu + Windows, Python 3.9 + latest)?

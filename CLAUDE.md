# Archery Timing & Display System – Project Spec

Open-source, cross-platform, low-latency archery timer: runs the shooting clock at competitions and
training, shows it on a TV/monitor, and drives lights and sound over USB serial. Used by a small
Swedish club, operated by non-technical volunteers. Python 3.9+, pygame-ce, pyserial.

Where things are: **`structure.md`**. Detail docs: `docs/` (`protocol`, `ipc`, `ui`, `audio`, `cluster`,
`espnow`, `benchmarks`, `decisions/`).

## Working agreement

- Plan briefly, then build one milestone at a time; end each in a working, committed-or-reviewable state.
- **Never invent archery rules or timings.** Everything rule-like is config (TOML) and flagged as a
  placeholder until the user confirms it against World Archery / SBF rules.
- Measure, don't assume: latency and performance claims need the benchmark/probe scripts (ideally on a real Pi 2B).
- Correctness and safety over features: timer, lights and sound must be right every time.
- Keep this file concise and current; propose edits when a decision changes the spec.
- The user wants progress, not exhaustive testing: run the suite once at milestone end, not after every edit.
  No git operations unless asked (the folder is not a repo right now).

## Targets and priorities

Priority order: (1) timer correctness and hardware output timing, (2) stability and fail-safe behaviour,
(3) ease of use, (4) visual polish.

Primary target: **Raspberry Pi 2 Model B**, Pi OS Lite 32-bit (2026-09-15 release), SDL2 KMSDRM kiosk, no X11,
ALSA audio, systemd services. Must also run on Windows 10/11, desktop Linux, and (nice to have) macOS. Any
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
  own MCU/speakers, forward commands, and fail safe without a leader (`docs/cluster.md`). ESP32 devices can
  sync over ESP-NOW (`docs/espnow.md`). All devices synchronized, any can run commands, any can have lights/sound.
- Inputs resolve to engine commands (`primary` is resolved by the engine): keyboard/clickers and mouse in the
  UI; MCU buttons (`$K`) and optional Pi GPIO in the core.

## Serial protocol v1 (`docs/protocol.md`)

Line-based ASCII, NMEA-style XOR checksum, 115200 baud: `$<CMD>[,args]*<XX>\n`. Host to MCU: `$L` lights,
`$S` whistle (MCU-timed; optional id for de-duplicated repeats, capability `W`), `$B` buzzer, `$G` group, `$T`
time, `$H` heartbeat (every 200 ms, full state), `$V` hello, `$M` ESP-NOW mode. MCU to host: `$I` hello reply
(caps `LSBGTKNW`), `$A` ACK, `$E` error, `$K` button, `$N` ESP-NOW status. Commands are idempotent state
assertions; MCU watchdog forces RED and silence after ~1 s without a valid frame. Shared vectors:
`firmware/test_vectors.txt`.

## Sound (`docs/audio.md`)

Two independent outputs: MCU horn (`$S`/`$B`, most precise, default) and local speakers (audio worker in the
core, synthesized horn, never in the UI). Per-core settings: each on/off, volume, output device; sound test
plays 1, 2, 3, 5 blasts and is blocked during an end or emergency. Whistle convention (placeholders to
confirm): 2 = to the line, 1 = start, 3 = stop, 5+ = emergency.

## Presets and competition features

All numbers are **placeholders to confirm** with WA/SBF rules. Presets are TOML (`config/presets/`), clubs
add their own. v1: Indoor 18 m (3 arrows), Outdoor qualification 6 and 3 arrows, Practice ends, Free
training. v2: individual finals (alternating per-arrow clock), team/mixed team, shoot-off. Setup toggles:
line rotation, arrows and time per end, prep time, yellow warning threshold, ends and practice ends,
auto-advance, whistle counts, tenths in the last seconds, language (Swedish first, English).

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
  scripts stay separate from the unit suite (results in `docs/benchmarks.md`).
- Tooling: `.venv\Scripts\python.exe` on Windows (Python 3.14, pygame-ce 2.5.8). Multi-line edits are easiest
  as a small Python script in the scratchpad (big shell heredocs with quotes have failed). Headless UI needs
  `SDL_VIDEODRIVER=dummy` (set in test conftests).

## Milestones

| | Milestone | State |
| --- | --- | --- |
| M0 | Foundation, render and jitter benchmarks | done, committed |
| M1 | Serial protocol, vectors, simulated MCU | built |
| M2 | Core engine (headless) and CLI | built |
| M3 | Serial worker, discovery, latency probe, ESP32 firmware | built; firmware never compiled |
| M4 | IPC, core service | built |
| M5 | UI client shell (renderers, sections, loop) | built |
| M6 | Operator UX: setup wizard, timers, menu, settings, hardware, confirm, idle, undo, Inter font | built |
| M7 | Audio: local worker, MCU/local toggles, volume, device, sound test, `$S` ids | built |
| M8 | Pi deployment: install script, systemd units (core, UI; leader/follower), KMSDRM kiosk, log rotation | built; untested on a Pi (`docs/deployment.md`) |
| M9 | Hardening: 4 h soak, unplug/UI-crash tests, README, Swedish operator guide with screenshots | next |
| M10 | Mesh v2 (`docs/decisions/0002`-`0004`): contracts, C++ core, Python sim, serial v2, roster/remotes/takeover, radio follower | software built and wired (Wave 1+2); **firmware v2 integration and hardware pending** |

Also built after M5: leader/follower cluster and ESP-NOW sync. A milestone is done when tests pass, ruff and
mypy are clean, docs are updated, and a short summary is posted.

## Decisions log

- Repo root is `E:\HarnoArcheryTimer`. `common/clock.py` exists from M0 (benchmarks need it). The jitter benchmark's
  two-process mode is a throwaway spike.
- `slots=True` needs Python 3.10, so messages use `@dataclass(frozen=True, **SLOTS)`. Protocol has an internal
  error code `MF` (framing garbage, never sent). Only heartbeats are ACKed. `$S` is an event; made safe with
  optional ids (cap `W`) and host repeats.
- Inputs: mouse + keyboard now, touch later; clickers are HID keyboards; MCU buttons (`$K`) and Pi GPIO live in
  the core. One UI process per display (`--display`, `--profile`); remote UIs measure a clock offset.
- Multi-device: leader + followers, no automatic leader election (open question); ESP-NOW mode chosen by the
  host with `$M` (`off|bridge|follow|auto`).
- UI: screens keep a banner and the operator bar visible; sound settings belong to the core; the horn is
  synthesized (no licensed sample); UI font is Inter Bold (SIL OFL) in `assets/fonts/`.

- Mesh v2 (`docs/decisions/0002-mesh-and-firmware-review.md`, decided 2026-10-04): one firmware image, behaviour from
  stored config plus the host's `$R` role; named master (`master_id`, rank, stickiness, conflict banner); HMAC mesh
  key plus per-remote keys with operator-accepted pairing and per-remote rights; radio-fed software follower in v1;
  single hop, manual takeover, no auto failover. Firmware steps F0-F6 come before any new feature (nothing is compiled).

## Current status (update at every hand-off)

M0 committed; M1-M8 plus cluster/ESP-NOW built and awaiting review, **uncommitted by the user's choice**
(not a git repo). Last full run: all tests pass (pty and bash-syntax tests skip on Windows), ruff and mypy clean.

**Added after the pre-Pi review:** serial discovery rotates through all candidate ports (a non-project USB
serial device no longer blocks the ESP32); firmware `beep.cpp` (LEDC PWM beeper, `PIN_BEEP`, `beepPlay` note
tables); menu "Network and sync" (role alone/leader/follower, LAN leader discovery by UDP beacon, ESP-NOW
mode, per-device lights on/off, Apply restarts the service; `docs/cluster.md`). The lights toggle and its tests were written but not run. Tests, ruff and mypy pass; the firmware change is uncompiled.

**Added after the pre-hardware review:** firmware resets `lastSoundId` on `$V` hello (the first whistle after a
core restart is no longer dropped); `install_pi.sh` checks that SDL has KMSDRM and, in `auto` mode, swaps the pip
pygame for apt `python3-pygame` if not; the UI frame loop (`UiApp._frame`/`_recover`) logs exceptions, drops open
screens and keeps drawing instead of crashing. UI and deploy tests, ruff pass; these three are untested on hardware
and have no dedicated tests. Review follow-ups still open: confirm rule numbers (ends in `indoor_18`/`outdoor_6`),
consider a confirm for `next` while an end runs, add MOSFET/relay stage and pull-downs on light/horn pins, keep the
first demo single-node, back up or `git init` before flashing.

**First run on a real Pi 2B (2026-10-04, Trixie, Mesa 26.2):** KMSDRM works with apt `python3-pygame` plus
libgbm/libegl/libgles/mesa. Root causes found: missing GL libs, SDL picking the desktop-GL `opengl` render driver on a
GLES context (black screen; fixed by forcing `SDL_RENDER_DRIVER=opengles2` in `open_renderer` and the launchers), a
hand-made `~/.bashrc` UI start holding DRM master. `install_pi.sh` now makes the sudo user the kiosk user (core as that
user, tty1 autologin, `~/.profile` runs `scripts/run_ui_tty1.sh`; `touch ~/.no-kiosk` for a shell; `--ui-mode service`
keeps the old unit). CPU per pixel is very slow on the Pi, so ticking things are **overlays** (`set_overlay`: glyph
textures and rectangles drawn by the GPU: countdown, clock, progress bar, light field/icons/frames, hover images, menu
banner); section pictures repaint only on real changes. Measured result: smooth, only layout changes log `slow frame`.
Deploy from Windows with `scripts/deploy_to_pi.ps1 -Pi user@ip [-Reboot]`; tune with `scripts/profile_paint.py`.
Open from that session: one unexplained Pi reboot after ~30 s (not reproduced; journal now persistent), core still runs
as old user `archery` until `install_pi.sh` is rerun, `tests/core_service/test_node.py` lights-toggle test fails.

**Mesh v2 (2026-10-04):** built by seven parallel work packages (`docs/decisions/0003`), integrated; full suite 641 passed +
the new `test_meshfeed`, ruff and mypy clean. Every core beacons and lists the timer network; `--leader radio` runs a
radio-only follower; the MCU gets `$R`, `$C` (mesh key, name), `$U` and `$J` from the core. **Firmware v2 is not
integrated yet** (`firmware/lib/meshcore` is not linked, X25519 is only a test stub, so pairing is unusable) and the
UI has no 'radio only' choice yet. Open decisions and next steps: `docs/decisions/0004-open-mesh-issues.md`.
**Update, same day:** session counter, safety-direction repeats and silence propagation decided and built; firmware
`esp-0.4.0` now links meshcore + hostcore and **compiles** for S3 and C3 (never flashed); native C++ tests 420 + 2179
checks, Python suite 675+ passed; 'Radio only' button exists. Pairing uses a real X25519 (RFC 7748 tested). Next:
hardware bring-up (two boards), see 0004. Native tests: `cd firmware/test/native && cmd /c .\run_tests.bat`.
**Flashing (2026-10-04):** `scripts/flash.bat|sh` is an OS-independent menu (stdlib only, `.flash-env/` with esptool,
prebuilt images in `firmware/release/`, PlatformIO only on demand; nothing added to the install scripts, see
`docs/flashing.md`). Six firmware variants incl. the classic ESP32-WROOM-32D (`docs/firmware.md`), compile-only.
**Follower access (2026-10-04, `docs/cluster.md`):** a new LAN follower is *pending* (watch only) until the operator approves
it on the leader (Menu > Followers); approval creates a per-follower key and hands over the radio mesh key; rights are a
preset (view/operator/full) plus per-action toggles; emergency always passes; the leader's own machine is the operator;
remote UIs without approval are watch-only. Follower cores log and publish `leader_rtt_ms`/`leader_offset_ms` (sync
diagnostic). Built and tested with in-process transports (725 tests); not tried on a real LAN yet.

**Radio discovery (2026-10-04, `docs/cluster.md`):** pairing needs no button press any more; a keyless ESP32 asks to join by
itself and the Remotes screen lists it live (name + MAC) with a rights page before Accept; the core renews the pairing window
during a search. Python 775 tests, ruff, mypy pass; the firmware change (`radio.cpp`, `main.cpp`) is uncompiled and untested.
A follower core's ESP32 is on its own mesh key until the follower is approved, so the master cannot see it before then.
**First hardware test (2026-10-04, C3 Super Mini master on USB + WROOM-32D standalone):** the keyless WROOM asked to join and
the C3 reported `$P,req` with name and MAC, no button. Found on the way: the C3 Super Mini at full TX power was not heard by the
WROOM (one-way link); `-DRADIO_TX_POWER_QDBM=34` (8.5 dBm) in `firmware/esp32c3/platformio.ini` fixes it. `-DRADIO_DEBUG` prints rx/pairing
lines on the serial port (off by default). Still untested on hardware: the full UI flow (accept, rights), S3 boards, a 3rd device.

**Remote buttons (decided 2026-10-04):** rigid pinout and fixed button actions (1 start/next, 2 pause, 3 stop end, 4 emergency; GPIO 13/14/16/17); the
master only decides rights per remote. Master-assigned button mapping (remote sends the button id) was considered and not chosen.

**Network-free joining (2026-10-04, `docs/cluster.md`):** a radio-only follower core no longer pushes its own mesh key; its keyless ESP32
pairs over the radio with the master (Menu > Wireless remotes > Accept); `radio_forget_key` / "Pair with the main timer again" resets it.
Intended demo hardware: C3 Super Mini for the synced network (Windows master + Fedora follower, later a Pi), WROOM-32D only as the
stand-alone breadboard remote (one button, three LEDs). Release images rebuilt and committed. 784 tests pass; the join between two real C3s is untested.

**Remove really unpairs (2026-10-04):** `$P,del` makes the master send REVOKE (mesh frame type 10, `docs/mesh.md`) so a removed remote forgets its keys and pairs
again; flashing a merged release image also wipes the ESP32's stored keys. Native C++ tests 425 checks pass; not yet tried on two real boards.

**Not verified:** any firmware (never compiled or flashed: buttons, ESP-NOW, `$S` ids, reworked `main.cpp`);
real MCU/light/horn hardware; the cluster on a real LAN; ESP-NOW range/latency; anything on the Pi (the M8 install script and systemd units, KMSDRM under `PAMName=login`,
GPU path, audio output, GPIO, performance, benchmarks); multi-monitor placement; touchscreen; gamepad; local
audio on a real device (only the dummy driver).

**Known gaps / placeholders:** rule timings, preset ends and line options (what ABC/ABCD mean), "Träning"
preset; whistle blast length lives in engine settings (no UI yet); fullscreen/monitor choice is a start-up flag;
leader failover not built; Windows has no SIGTERM.

**Resume here (new instance):** read this file, `structure.md`, then the doc for the area you touch. Do not
re-verify finished work. Next: finish M10 (firmware v2 integration per `0004`), then **M9** (propose a short plan, then build). Ask the user only about leader failover,
exact rule timings, and real MCU/light/sound hardware.

## Open questions

- [ ] **Exact rule timings** (prep, end times, warning, whistle conventions, finals) against current WA/SBF rules.
- [ ] **Microcontroller hardware:** board (ESP32-S3 assumed), light hardware, sound hardware.
- [ ] **Leader failover:** followers go RED and silent when the leader dies. Automatic takeover (and by whom), or manual?
- [ ] **pygame-ce on Pi OS Lite armv7:** pip wheel with KMSDRM, or apt `python3-pygame`? Run `scripts/env_probe.py` on the Pi.
- [ ] **Windows timing target:** is < 2 ms p99 also required on Windows, or Pi only?
- [ ] **CI:** GitHub Actions (ruff, mypy, pytest on Ubuntu + Windows, Python 3.9 + latest)?
- [ ] **Licensing:** project licence (MIT or GPL-3.0); sounds are synthesized, the font is OFL. No LICENSE file until decided.

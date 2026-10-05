# UI client

`python -m archerytimer.ui_client` renders the core's state on one display and sends
commands. It holds no timing authority: if it freezes or crashes, the timer, lights and sound
carry on (restart it and it resyncs from the next `state` message).

## How a frame is made

- The screen is split into **sections** (traffic light, countdown, info panel, operator bar,
  status bar). Each section has a `key(ctx)` (everything its pixels depend on) and
  `next_change_ns(ctx)` (when its key will change by itself).
- The loop sleeps until the earliest `next_change_ns` or an event (input, IPC message), redraws
  only sections whose key changed, uploads those textures and presents. Nothing changed: no
  present. A running countdown therefore presents once per second (clock ticks too).
- Countdown text comes from the **deadline**: `remaining = deadline - (local_now + offset)`.
  The core never sends "remaining seconds".
- Layout is fractions of the output (`layout.py`); fonts scale from output height. On the GPU
  path the logical canvas is capped at 1080p high and the GPU scales it, so 4K costs nothing
  extra. Software path renders at output size.
- Light state always has words and a shape (circle, triangle, square), never colour alone.
- **No contact with the core for 1 s turns the display RED** ("no contact with timer"): the
  hardware also goes RED when the core goes silent, and no contact means stop.

Renderers (`renderer/`): `gpu` (SDL renderer API via `pygame._sdl2.video`) and `software`;
`--renderer auto` tries GPU first and falls back.

## Running it

```text
python -m archerytimer.ui_client [--fullscreen] [--display N] [--profile full|audience]
    [--renderer auto|gpu|software] [--fps 60] [--tenths] [--lang en|sv]
    [--host CORE_IP --tcp-port 8765]
    [--sequence indoor_3arrows --groups AB,CD --ends 2]   # dev: configure an idle core
python -m archerytimer.launcher --no-serial      # desktop: core + UI together
```

Keys (all remappable in the `[keys]` table of the settings TOML): Space / Enter / PageDown /
Right = primary action (start end, next end, resume), P / B / . = pause or resume, S = stop
end, N = next, Backspace / PageUp / Left = back, **Esc = emergency stop**, C / R = after an
emergency, resume shooting / restart the end, M / F1 = menu, Y = confirm a confirm dialog, H = hide the operator bar, Ctrl+Q = quit (asks for confirmation). A presentation clicker is just a keyboard to the OS, so its
buttons already work through this map (Esc from a clicker stops the timer, which is the safe
direction).

## Input devices

| Device | Where it is handled | Status |
| --- | --- | --- |
| Mouse | UI: operator bar buttons | works, tested |
| Keyboard, clicker, foot pedal (HID keyboard) | UI: `[keys]` map | works, tested |
| Touchscreen | arrives as mouse clicks | works as mouse (not tried on a real touchscreen) |
| Gamepad / HID buttons | UI: `[joystick]` table, `button<N> = "<action>"` | not tried on hardware |
| MCU buttons (ESP32) | **core**: `$K,<id>,<0\|1>` frames, bound in `[buttons]` as `mcu:<id>` | works with the firmware |
| Raspberry Pi GPIO | **core**: `gpiozero`, bound as `gpio:<pin>` | optional; the core logs a warning and carries on if `gpiozero` is missing |

Core-side inputs reach the engine directly, so they work with no UI running. A binding is
`press = "<action>"`, optionally `hold = "<action>"` and `hold_s` (then it fires on release:
short press runs `press`, long press runs `hold`; useful for hold-to-confirm reset).
Emergency can never have a hold. Actions are the engine's commands plus `primary`, which the
engine resolves itself (start the waiting end, or resume a paused one), so every input device
agrees on what "go" means.

## Operator screens

Menu (`M` / `F1` / the Meny button) opens a stack of screens in a `screen` section that
replaces light, countdown and info. The timer stays visible as a banner (light colour, label,
countdown) and the operator bar with the emergency stop stays on screen, so a menu never hides
the light; an emergency closes every screen. Screens are declarative: each returns immutable
`Widget`s (`widgets/`), which double as the section's dirty key, so an idle screen costs nothing.

| Screen | Purpose |
| --- | --- |
| Setup (3 steps) | 1 preset card (or "last used"), 2 lines and ends, 3 start. Sends `configure`, remembers the setup |
| Advanced | Prep time, shooting time, warning threshold, auto next end, alternate start order (per session) |
| Timers | Quick timer lengths (`config/presets/timings.toml`, clubs can add their own) and a custom timer: prep, shooting time, yellow warning. Becomes the default for new sessions; "Standard" returns to each preset's own timing |
| Menu | New session, timers, reset, settings, hardware status, network and sync, followers, wireless remotes, shortcuts, quit |
| Network and sync | This device's role (alone, main timer, follows, radio only), ESP-NOW role, lights on/off, the timer-network list; see `cluster.md` |
| Followers | Leader only: approve a new follower, set its rights, block or remove it |
| Wireless remotes | Search for new radio devices, accept with rights, change or remove paired remotes |
| Settings | Language, tenths, FPS cap, eco profile, idle screen (UI only, saved in `ui_prefs.json` in the user data dir) |
| Sound | Horn on the MCU / local speakers, volume, output device, sound test (`audio.md`) |
| Hardware | Plain-language status of timer, lights, firmware, ESP-NOW, clock sync |
| Shortcuts | Key bindings, read from the active key map |
| Confirm | Reset, quit, replace a session. Space/Enter/Back cancel; only the red button or `Y` confirms |

Presets are TOML (`config/presets/*.toml`, plus `<user data dir>/presets/*.toml` for clubs);
the UI offers those whose sequence the core reports. Per-session timing overrides travel in the
`configure` command (`prep_s`, `shoot_s`, `warn_s`). Keys on a screen: Back goes a step back,
Primary is the screen's forward action, everything else (pause, stop end, emergency) still
reaches the core. Clicks on the operator bar always go to the core. The audience profile never
shows screens.

## Operator conveniences

- **Icons and frame:** the light has a big icon on both sides (tick = shoot, ! = running out of time,
  X = stop) and a frame in the light colour runs down both screen edges, so the state reads
  without colour and from the shooting line.
- **Next end:** while waiting, the primary button shows what it will start ("Linje CD · Omgång 4 av 10").
- **Undo:** after Stop end or Next, the Back button turns amber and reads Ångra for 5 seconds. It
  sends the engine's `back` (the end can be shot again), it does not rewind a whistle already blown.
- **No session:** the primary button and Space open Setup.
- **Idle screen:** with nothing running, after N minutes (1 / 5 / 10 / 30) the display shows a big clock
  (style: clock, dim clock or black). Any key, click or touch, or any change from the core, ends it; the
  key press that wakes it does nothing else, except Emergency, which always acts. It never starts
  while an end runs or during an emergency. Idle costs one redraw per minute (none in the black style).
  All three options are in Settings and saved in `ui_prefs.json`.
- **Font:** Inter Bold from `assets/fonts/`; any `.ttf`/`.otf` placed there is used instead (see its README).

## Several displays and several machines

One UI process drives one display. For two monitors on a PC, start two UI clients
(`--display 0 --profile full`, `--display 1 --profile audience`). `--profile audience` shows
only the light, countdown, info and status, with no controls except the emergency key. For
displays on other machines, run a UI client there with `--host <core machine's IP>` and start
the core with `--host 0.0.0.0` so it listens on the network.

Clock sync: a UI measures `offset = core_clock - local_clock` with ping/pong round trips every
2 s (fastest of the last 8 exchanges wins; see `ipc/clocksync.py`). Remote screens then count
the same deadline; accuracy is bounded by network asymmetry (a fraction of a millisecond on
wired links, a few ms on WiFi). The status bar shows the sync figure when the offset is non-trivial.

Security note: the IPC socket is not encrypted, and a remote display is watch-only until the leader approves it
(`cluster.md`). Only expose it on a network you trust (the club's own LAN or a direct cable), never the open internet.

Several devices that each have their own lights, sound and buttons run as a cluster (one
leader, followers that mirror it and forward commands): see `docs/cluster.md`.

## Measured

`scripts/ui_benchmark.py` (cost of one presented frame, headless SDL, dev PC, 1080p): software
mean 1.8 ms, GPU path 4.0 ms (dummy driver, so the GPU number is not meaningful). Pi 2B
numbers: run `SDL_VIDEODRIVER=kmsdrm python scripts/ui_benchmark.py --fullscreen` on the Pi. On the Pi the ticking parts are GPU overlays
(`deployment.md`).

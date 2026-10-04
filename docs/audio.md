# Audio (M7)

Two independent sound outputs, each switchable on the Sound screen (Menu > Ljud / Sound):

| Output | Path | Notes |
| --- | --- | --- |
| MCU sound | engine event -> `SerialWorker` -> `$S,<n>[,<id>]` (MCU times the blasts) or `$B` (host-timed) | Most precise; the default |
| Local sound | engine event -> `AudioControl` -> `AudioWorker` -> `pygame.mixer` | Runs in the core, never in the UI; Pi onboard audio adds ~20-50 ms |

Both follow the same events, so they stay aligned. `whistle_timing` (engine setting) picks `mcu`
(one `Whistle(n, blast_ms, gap_ms)` event, each output times it) or `host` (the engine schedules
every `Buzzer` on/off).

## Local audio

- `AudioWorker` has its own thread and queue. Blast start times are `event_time + i * (blast + gap)`,
  so wake-up latency never accumulates. `Whistle(0)` / `Buzzer(False)` silence at once.
- The horn is synthesized (`audio/synth.py`, 441 Hz plus odd harmonics, 8 ms attack, 25 ms release), so
  no licensed sample is needed. Blasts are pre-decoded and cached per length; mixer buffer is 512 samples.
- No working audio device means a silent `NullBackend` (logged, never fatal); the UI shows a warning.
- Output device: chosen on the Sound screen (names from SDL); changing it rebuilds the backend on the
  worker thread. `""` is the system default (on a Pi: pick HDMI or 3.5 mm there).

## Settings (per core)

`AudioSettings`: `local`, `mcu`, `volume` (0-1, local only), `device`. Defaults come from `[audio]` in
`config/default_settings.toml`, then the core's own `core_audio.json` in the user data dir. UIs send
`settings` values `sound_local`, `sound_mcu`, `volume`, `audio_device`; the core replies with an `audio`
message (also replayed to new clients). In a cluster each node keeps its own sound settings.

## Sound test

`sound_test` command: plays 1, 2, 3 and 5 blasts on every enabled output, then explicit silence. It is
refused while an end runs or an emergency is active (`busy` in the `audio` message), and when no output
is enabled. Real engine signals are never delayed by it.

## `$S` healing (resolves the M1 open point)

Devices with capability `W` accept `$S,<n>,<id>` (id 1-255) and ignore a frame whose id equals the last
one they acted on. The host repeats each whistle frame 40 ms and 120 ms later, so a frame lost on the
wire is healed without ever replaying the blasts. Devices without `W` get the plain `$S,<n>` once. A
newer whistle command cancels pending repeats. Switching MCU sound off sends `$S,0` and `$B,0` once and
drops all later sound frames (RED and silence on shutdown are always sent). Firmware change is in
`firmware/esp32s3/src/main.cpp` (`lastSoundId`), not yet compiled.

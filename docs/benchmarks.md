# Benchmarks

Scripts live in `scripts/`. Each case runs in its own subprocess and prints a summary table.
Add `--json PATH` to save raw results. Use `--headless` for CI-style runs without a display.

## How to run

On the Pi 2B (Pi OS Lite, no desktop), from the repo root with the venv active:

```bash
# 1. What does this machine support? (SDL drivers, KMSDRM, audio, pygame build)
python scripts/env_probe.py

# 2. Rendering: modes A (full redraw), B (sectioned, 1 section at 60 fps), C (sectioned, 1 Hz)
SDL_VIDEODRIVER=kmsdrm python scripts/render_benchmark.py --fullscreen --duration 10 --json render_pi.json

# 3. Engine wake-up jitter (target: lateness p99 < 2 ms), full matrix
python scripts/jitter_benchmark.py --duration 20 --json jitter_pi.json
# Heavier: all cores loaded, engine pinned and niced
python scripts/jitter_benchmark.py --duration 60 --hogs 4 --engine-cpu 3 --engine-nice -5
```

Run `top` in a second terminal during step 2 mode C to see idle CPU.

## Windows results (dev PC, 16 cores; indicative only)

Not representative of the Pi. Short runs, 1080p windowed.

| Case | Result |
| --- | --- |
| Render, GPU, all modes | 60 fps reached. B: 1.5 ms work, 12 % CPU. C: 2 % CPU |
| Render, software A / B | 13 % / 9 % CPU, 60 fps |
| Jitter, `Event.wait`, default timer | p99 ~16 ms (timer tick is 15.6 ms) |
| Jitter, `Event.wait`, `timeBeginPeriod(1)` | p99 ~2.1-2.4 ms |
| Jitter, hybrid wait, threaded | passes 2 ms p99 except under overload (~5 ms) |
| Jitter, hybrid wait, two-process | 0.7-1.4 ms p99, including under overload |
| Jitter, threaded + animating | one 229 ms spike seen (GIL/SDL contention suspected) |

The full 20 s Windows matrix was deferred by request; precise timing work moves to the
real target hardware and to M2. A run may have been left going in the background; if so its
output is in `docs/results/`.

## Pi 2B results

_Pending: to be run on hardware._

## Takeaways so far

- Two-process design is supported by the data (see ADR 0001).
- Engine wait must be an injectable strategy (plain on Linux, hybrid + 1 ms timer on Windows).
- Pi: confirm KMSDRM availability and pygame-ce wheel vs apt `python3-pygame` with `env_probe.py`.

# ADR 0001: Python + pygame-ce, two-process architecture

- Status: accepted (provisional until the Pi 2B benchmark numbers are in)
- Date: 2026-10-04

## Context

The timer, lights and sound must be exact on a Raspberry Pi 2B (4x Cortex-A7 at 900 MHz,
1 GB RAM) while a 1080p UI renders on the same machine. The project needs fast
development, support for Pi OS Lite (no desktop), Windows and desktop Linux, and a
modest dependency footprint.

## Decision

1. **Language and libraries:** Python 3.9+, pygame-ce (SDL2, KMSDRM on the Pi), pyserial,
   standard library. A Rust rewrite of the core stays possible because the core is pure
   logic behind interfaces.
2. **Two processes:** a headless core service (engine, serial, audio, IPC server) and a UI
   client (rendering, input) connected by a local socket. The core publishes absolute
   monotonic deadlines, not remaining time.
3. **Engine wait strategy is injectable:** plain `Event.wait(timeout)` where the OS timer is
   fine-grained (Linux, expected), a hybrid wait (coarse `Event.wait`, then 0.5 ms sleeps
   that still poll for commands) with 1 ms timer resolution on Windows.

## Rationale (M0 measurements, Windows, see docs/benchmarks.md)

- A thread-based engine inside the UI process shares the GIL with rendering. Under heavy UI
  load it showed lateness spikes of tens to hundreds of ms and ~5 ms p99 even with the
  hybrid wait.
- The engine in its own process stayed around 1 ms p99 under the same overload.
- On Windows, `Event.wait` granularity is the system timer (15.6 ms by default), so a naive
  wait misses the 2 ms target without mitigation.

## Consequences

- IPC adds a small, bounded delay for UI updates only; hardware output never crosses it.
- A UI crash or freeze does not affect timing, lights or sound.
- Pi 2B numbers must confirm the choice; if the single-process variant also passes there,
  the in-process transport remains available as a fallback.

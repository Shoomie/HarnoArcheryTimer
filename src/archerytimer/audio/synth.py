"""Synthesized signal horn: no licensed sample needed, identical on every platform.

16-bit mono PCM built with the standard library only. A blast has a short attack and release
so it never clicks; the sustained tone is an exact number of cycles so it loops seamlessly.
"""

from __future__ import annotations

import array
import math

RATE = 44100
FUNDAMENTAL_HZ = 441.0  # exactly 100 samples per cycle at 44.1 kHz
# Odd harmonics give a horn-like, penetrating timbre (relative amplitudes).
HARMONICS = ((1, 1.0), (3, 0.45), (5, 0.25), (7, 0.12))
ATTACK_MS = 8
RELEASE_MS = 25
PEAK = 0.8  # of full scale; leaves headroom for the volume control to work above and below


def _cycle() -> list[float]:
    n = round(RATE / FUNDAMENTAL_HZ)
    norm = sum(a for _, a in HARMONICS)
    return [
        sum(a * math.sin(2 * math.pi * h * i / n) for h, a in HARMONICS) / norm for i in range(n)
    ]


def blast(duration_ms: int, rate: int = RATE) -> bytes:
    """One horn blast of ``duration_ms``, as little-endian signed 16-bit mono samples."""
    total = max(1, rate * duration_ms // 1000)
    cyc = _cycle()
    n = len(cyc)
    attack = max(1, rate * ATTACK_MS // 1000)
    release = max(1, min(total, rate * RELEASE_MS // 1000))
    out = array.array("h")
    for i in range(total):
        gain = min(1.0, (i + 1) / attack, (total - i) / release)
        out.append(int(32767 * PEAK * gain * cyc[i % n]))
    return _le_bytes(out)


def sustained(duration_ms: int = 1000) -> bytes:
    """A whole number of cycles of steady tone, for looping while the buzzer is on."""
    cyc = _cycle()
    n = len(cyc)
    cycles = max(1, RATE * duration_ms // 1000 // n)
    out = array.array("h", (int(32767 * PEAK * cyc[i % n]) for i in range(cycles * n)))
    return _le_bytes(out)


def _le_bytes(samples: array.array) -> bytes:  # type: ignore[type-arg]
    import sys

    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    return samples.tobytes()

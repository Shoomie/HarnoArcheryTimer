"""Clock offset between this machine and the core, for UIs on other devices.

``time.monotonic_ns`` is system-wide but unrelated between machines, so a remote UI cannot
compare the snapshot's deadlines with its own clock directly. It measures
``offset = core_clock - local_clock`` with ping/pong round trips and renders
``remaining = deadline - (local_now + offset)``. Same-machine UIs measure ~0.

Estimator: of the last few samples, trust the one with the smallest round trip (queueing
delay only ever adds to the RTT, so the fastest exchange is the least distorted).
Accuracy is bounded by half the round-trip asymmetry: typically well under 1 ms on a LAN
or direct Ethernet cable, a few ms on WiFi.
"""

from __future__ import annotations

from collections import deque


class OffsetEstimator:
    def __init__(self, keep: int = 8) -> None:
        self._samples: deque[tuple[int, int]] = deque(maxlen=keep)  # (rtt_ns, offset_ns)

    def add(self, t0: int, t1: int, t2: int) -> None:
        """``t0`` local send time, ``t1`` core time when it replied, ``t2`` local receive time."""
        rtt = t2 - t0
        if rtt < 0:
            return
        self._samples.append((rtt, t1 - (t0 + rtt // 2)))

    @property
    def synced(self) -> bool:
        return bool(self._samples)

    @property
    def offset_ns(self) -> int:
        return min(self._samples)[1] if self._samples else 0

    @property
    def rtt_ns(self) -> int:
        return min(self._samples)[0] if self._samples else 0

    def reset(self) -> None:
        self._samples.clear()

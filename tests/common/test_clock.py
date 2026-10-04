from __future__ import annotations

import threading

import pytest

from archerytimer.common.clock import NS_PER_S, Clock, FakeClock, MonotonicClock


def test_fake_clock_advances_only_when_told(fake_clock: FakeClock) -> None:
    t0 = fake_clock.now_ns()
    assert fake_clock.now_ns() == t0
    fake_clock.advance(5)
    assert fake_clock.now_ns() == t0 + 5
    fake_clock.advance_s(1.5)
    assert fake_clock.now_ns() == t0 + 5 + 1_500_000_000


def test_fake_clock_rejects_going_backwards(fake_clock: FakeClock) -> None:
    with pytest.raises(ValueError):
        fake_clock.advance(-1)
    with pytest.raises(ValueError):
        fake_clock.set(fake_clock.now_ns() - 1)


def test_fake_clock_wait_jumps_to_timeout_when_not_set(fake_clock: FakeClock) -> None:
    ev = threading.Event()
    t0 = fake_clock.now_ns()
    assert fake_clock.wait(ev, 250 * 1_000_000) is False
    assert fake_clock.now_ns() == t0 + 250_000_000


def test_fake_clock_wait_returns_immediately_when_set(fake_clock: FakeClock) -> None:
    ev = threading.Event()
    ev.set()
    t0 = fake_clock.now_ns()
    assert fake_clock.wait(ev, NS_PER_S) is True
    assert fake_clock.now_ns() == t0


def test_monotonic_clock_is_monotonic_and_waits() -> None:
    clock: Clock = MonotonicClock()
    a = clock.now_ns()
    b = clock.now_ns()
    assert b >= a
    ev = threading.Event()
    assert clock.wait(ev, 0) is False
    ev.set()
    assert clock.wait(ev, NS_PER_S) is True


def test_both_clocks_satisfy_protocol() -> None:
    clocks: list[Clock] = [MonotonicClock(), FakeClock()]
    assert all(isinstance(c.now_ns(), int) for c in clocks)

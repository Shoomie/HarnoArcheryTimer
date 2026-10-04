from __future__ import annotations

import pytest

from archerytimer.common.clock import FakeClock


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock(start_ns=1_000_000_000)

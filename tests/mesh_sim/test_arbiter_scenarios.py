from __future__ import annotations

import pytest
from tools.mesh_sim.scenarios import DEFAULT_FILE, parse, run

SCENARIOS = parse(DEFAULT_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_scenario(sc) -> None:  # type: ignore[no-untyped-def]
    assert run(sc) == []

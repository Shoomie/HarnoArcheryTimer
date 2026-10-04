"""Parser and runner of ``firmware/arbiter_scenarios.txt`` for the Python arbiter.

Lines at the same ms run strictly in file order (an ``expect`` sees only events above it).
Run directly: ``python -m tools.mesh_sim.scenarios [file]``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from archerytimer.hardware.mesh_types import NO_SOUND_AGE, RadioSound, RadioTimer
from tools.mesh_sim.arbiter import Arbiter, lights_bits, lights_text

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "firmware" / "arbiter_scenarios.txt"


@dataclass
class Scenario:
    name: str
    config: dict[str, str] = field(default_factory=dict)
    # (time, order, kind, args)
    steps: list[tuple[int, int, str, dict[str, str]]] = field(default_factory=list)


def _kv(tokens: list[str]) -> dict[str, str]:
    return dict(t.split("=", 1) for t in tokens)


def parse(text: str) -> list[Scenario]:
    out: list[Scenario] = []
    order = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tok = line.split()
        if tok[0] == "scenario":
            out.append(Scenario(tok[1]))
            continue
        sc = out[-1]
        if tok[0] == "config":
            sc.config = _kv(tok[1:])
            continue
        assert tok[0] == "at", line
        t0 = int(tok[1])
        rest = tok[2:]
        times = [t0]
        if rest[0] == "every":
            step, until = int(rest[1]), int(rest[3])
            times = list(range(t0, until + 1, step))
            rest = rest[4:]
        kind = rest[0]
        if kind == "rx":
            kind, args = "rx_" + rest[1], _kv(rest[2:])
        elif kind == "host":
            kind, args = "host", (_kv(rest[1:]) if "=" in rest[1] else {"state": rest[1]})
        else:
            args = _kv(rest[1:])
        for t in times:
            order += 1
            sc.steps.append((t, order, kind, args))
    for sc in out:
        sc.steps.sort(key=lambda s: (s[0], s[1]))
    return out


def run(sc: Scenario) -> list[str]:
    """Run one scenario; returns the failure messages (empty = pass)."""
    cfg = sc.config
    own = int(cfg.get("master_id", "0"), 16)
    arb = Arbiter(cfg["role"], own, cfg["host"] == "alive")
    fails: list[str] = []
    for t, _, kind, a in sc.steps:
        now = float(t)
        if kind == "rx_TIMER":
            arb.on_timer(
                now,
                RadioTimer(
                    master_id=int(a["master"], 16), rank=int(a["rank"]),
                    lights=lights_bits(a["lights"]), flags=int(a.get("flags", "0")), mode=1,
                    phase=0, remaining_ms=0, end_no=1, total_ends=1, group=0, round=1,
                    total_rounds=1, session_rev=0, sound_seq=int(a.get("sound_seq", "0")),
                    sound_count=int(a.get("sound_count", "0")), sound_blast=50, sound_gap=50,
                    sound_age=int(a.get("sound_age", str(NO_SOUND_AGE))),
                    session=int(a.get("session", "1")),
                ),
            )  # fmt: skip
        elif kind == "rx_SOUND":
            arb.on_sound(
                now,
                RadioSound(
                    int(a["master"], 16),
                    int(a["seq"]),
                    int(a["count"]),
                    50,
                    50,
                    session=int(a.get("session", "1")),
                ),
            )
        elif kind == "reboot":
            arb.reboot()
            arb.set_host(cfg["host"] == "alive")  # host state is re-asserted by the host after boot
        elif kind == "host":
            if "state" in a:
                arb.set_host(a["state"] == "alive")
            else:
                arb.set_host_lights(lights_bits(a["lights"]))
        elif kind == "expect":
            fails += _expect(sc, arb, t, a)
        else:
            raise ValueError(f"unknown step {kind}")
    return fails


def _expect(sc: Scenario, arb: Arbiter, t: int, a: dict[str, str]) -> list[str]:
    now = float(t)
    f = arb.follow(now)
    got = {
        "follow": "none" if f is None else f"{f:08X}",
        "lights": lights_text(arb.lights(now)),
        "failsafe": str(int(arb.failsafe(now))),
        "conflict": str(int(arb.conflict(now))),
        "sound_started": str(arb.sound_started()),
        "tx_rank": str(arb.tx_rank(now)),
        "sound_active": str(int(arb.sound_active(now))),
    }
    bad = []
    for k, want in a.items():
        have = got[k]
        if k == "follow" and want != "none":
            want = f"{int(want, 16):08X}"
        if have != want:
            bad.append(f"{sc.name} @{t}ms: {k} expected {want}, got {have}")
    return bad


def run_file(path: Path = DEFAULT_FILE) -> dict[str, list[str]]:
    return {sc.name: run(sc) for sc in parse(path.read_text(encoding="utf-8"))}


if __name__ == "__main__":
    results = run_file(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE)
    for name, fails in results.items():
        print(("PASS " if not fails else "FAIL ") + name)
        for f in fails:
            print("   ", f)
    sys.exit(1 if any(results.values()) else 0)

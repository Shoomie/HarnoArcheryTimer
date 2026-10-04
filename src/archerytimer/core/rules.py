"""Load sequences from TOML. Rules live in config, never in code."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional

from archerytimer.common.clock import NS_PER_S
from archerytimer.core.models import Light, PhaseSpec, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib  # type: ignore[no-redef]


class RulesError(ValueError):
    pass


def _light(value: Any, where: str) -> Light:
    try:
        return Light[str(value).upper()]
    except KeyError:
        raise RulesError(f"{where}: unknown light {value!r}") from None


def parse_sequence(seq_id: str, data: Mapping[str, Any]) -> Sequence:
    phases = []
    for i, p in enumerate(data.get("phases", [])):
        where = f"sequence {seq_id!r} phase {i}"
        try:
            duration_ns = round(float(p["duration_s"]) * NS_PER_S)
            pid = str(p["id"])
            light = _light(p["light"], where)
        except KeyError as exc:
            raise RulesError(f"{where}: missing {exc.args[0]!r}") from None
        if duration_ns < 0:
            raise RulesError(f"{where}: negative duration")
        warn_at = p.get("warn_at_s")
        phases.append(
            PhaseSpec(
                id=pid,
                duration_ns=duration_ns,
                light=light,
                whistle_on_start=int(p.get("whistle_on_start", 0)),
                warn_at_ns=None if warn_at is None else round(float(warn_at) * NS_PER_S),
                warn_light=_light(p.get("warn_light", "YELLOW"), where),
            )
        )
    if not phases:
        raise RulesError(f"sequence {seq_id!r} has no phases")
    return Sequence(id=seq_id, name=dict(data.get("name", {})), phases=tuple(phases))


def parse_sequences(data: Mapping[str, Any]) -> Dict[str, Sequence]:
    return {sid: parse_sequence(sid, body) for sid, body in data.get("sequence", {}).items()}


def load_sequences(directory: Path) -> Dict[str, Sequence]:
    """Load every ``*.toml`` in ``directory``; later files may not redefine an id."""
    result: Dict[str, Sequence] = {}
    for path in sorted(directory.glob("*.toml")):
        with path.open("rb") as fh:
            for sid, seq in parse_sequences(tomllib.load(fh)).items():
                if sid in result:
                    raise RulesError(f"duplicate sequence id {sid!r} in {path.name}")
                result[sid] = seq
    return result


PREP_ID = "PREP"
SHOOT_ID = "SHOOT"


def apply_overrides(
    seq: Sequence, prep_ns: Optional[int], shoot_ns: Optional[int], warn_ns: Optional[int]
) -> Sequence:
    """A copy of ``seq`` with the operator's per-session timings applied."""
    phases = []
    for ph in seq.phases:
        if ph.id == PREP_ID and prep_ns is not None:
            ph = replace(ph, duration_ns=prep_ns)
        elif ph.id == SHOOT_ID:
            if shoot_ns is not None:
                ph = replace(ph, duration_ns=shoot_ns)
            if warn_ns is not None:
                ph = replace(ph, warn_at_ns=warn_ns if warn_ns > 0 else None)
        phases.append(ph)
    return replace(seq, phases=tuple(phases))


def timing_info(seq: Sequence) -> Dict[str, float]:
    """PREP / SHOOT / warning times in seconds, for the setup screens (0 when absent)."""
    out = {"prep_s": 0.0, "shoot_s": 0.0, "warn_s": 0.0}
    for ph in seq.phases:
        if ph.id == PREP_ID:
            out["prep_s"] = ph.duration_ns / NS_PER_S
        elif ph.id == SHOOT_ID:
            out["shoot_s"] = ph.duration_ns / NS_PER_S
            out["warn_s"] = (ph.warn_at_ns or 0) / NS_PER_S
    return out

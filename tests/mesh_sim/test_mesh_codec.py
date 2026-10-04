from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from archerytimer.hardware import mesh_codec as mc
from archerytimer.hardware.mesh_types import RadioSession

VECTORS = Path(__file__).resolve().parents[2] / "firmware" / "mesh_vectors.txt"


def _parse() -> tuple[dict[str, bytes], dict[str, str], list[dict[str, str]]]:
    keys: dict[str, bytes] = {}
    pair: dict[str, str] = {}
    frames: list[dict[str, str]] = []
    for line in VECTORS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        tok = line.split()
        if tok[0] == "key":
            keys[tok[1]] = bytes.fromhex(tok[2])
        elif tok[0] == "pairkey":
            pair = dict(t.split("=", 1) for t in tok[1:])
            keys["K"] = bytes.fromhex(pair["K"])
        elif tok[0] == "frame":
            head, _, verdict = line.partition("=>")
            f = dict(t.split("=", 1) for t in head.split()[1:])
            f["verdict"] = verdict.strip()
            frames.append(f)
    return keys, pair, frames


KEYS, PAIR, FRAMES = _parse()


def describe(frame: mc.MeshFrame) -> dict[str, str]:
    out = {"epoch": str(frame.epoch), "seq": str(frame.seq)}
    p = frame.payload
    if isinstance(p, RadioSession):
        out["flags"] = str(int(p.alternate_order) | (2 * int(p.auto_advance)))
        skip = {"alternate_order", "auto_advance"}
    else:
        skip = set()
    for f in dataclasses.fields(p):
        if f.name in skip:
            continue
        v = getattr(p, f.name)
        if isinstance(v, bytes):
            s = v.hex().upper()
        elif isinstance(v, tuple) and f.name == "fw":
            s = ".".join(map(str, v))
        elif isinstance(v, tuple):
            s = ",".join(v)
        else:
            s = str(v)
        out[f.name] = s
    return out


def _ring(f: dict[str, str]) -> mc.KeyRing:
    src = bytes.fromhex(f["src"])
    return mc.KeyRing(
        mesh_key=KEYS["mesh"],
        remote_keys={src: KEYS["remote"]},
        pairing_open=True,
        pair_key=KEYS["K"],
    )


@pytest.mark.parametrize(
    "f", FRAMES, ids=[f"{i}-{f['verdict'][:12]}" for i, f in enumerate(FRAMES)]
)
def test_vector(f: dict[str, str]) -> None:
    data, src = bytes.fromhex(f["hex"]), bytes.fromhex(f["src"])
    if f["verdict"] == "ERR":
        with pytest.raises(mc.FrameError):
            mc.decode(data, src, _ring(f))
        return
    parts = f["verdict"].split(" ", 2)
    assert parts[0] == "OK"
    want = dict(re.findall(r"(\w+)=(.*?)(?= \w+=|$)", parts[2]))  # a name may contain spaces
    frame = mc.decode(data, src, _ring(f))
    assert mc.TYPE_NAMES[frame.ptype] == parts[1]
    got = describe(frame)
    assert got == want
    # re-encoding reproduces the vector byte for byte
    assert mc.encode(frame, KEYS[f["key"]], src) == data


def test_pairkey_and_blob() -> None:
    shared = bytes.fromhex(PAIR["shared"])
    rmac, mmac = bytes.fromhex(PAIR["remote_mac"]), bytes.fromhex(PAIR["master_mac"])
    k = mc.derive_pair_key(shared, rmac, mmac)
    assert k.hex().upper() == PAIR["K"]
    rkey = bytes.fromhex(PAIR["remote_key"])
    blob = mc.pair_blob(k, KEYS["mesh"], rkey)
    assert blob.hex().upper() == PAIR["blob"]
    assert mc.open_blob(k, blob) == (KEYS["mesh"], rkey)


def test_pair_req_refused_while_window_closed() -> None:
    f = next(x for x in FRAMES if x["key"] == "zero")
    ring = _ring(f)
    ring.pairing_open = False
    with pytest.raises(mc.FrameError):
        mc.decode(bytes.fromhex(f["hex"]), bytes.fromhex(f["src"]), ring)


def test_dedupe_new_epoch_accepted_old_seq_rejected() -> None:
    d = mc.Dedupe()
    mac = b"\x01" * 6
    assert d.accept(mac, 100, 5000)
    assert not d.accept(mac, 100, 5000)  # repeat
    assert not d.accept(mac, 100, 4999)  # older
    assert d.accept(mac, 100, 5001)
    assert d.accept(mac, 7, 1)  # rebooted sender: new epoch, seq restarted (the v1 bug)
    assert d.accept(mac, 7, 2)
    d2 = mc.Dedupe()
    assert d2.accept(mac, 1, 0xFFFE)
    assert d2.accept(mac, 1, 0xFFFF)
    assert d2.accept(mac, 1, 0)  # int16 wrap
    assert not d2.accept(mac, 1, 0xFFFF)

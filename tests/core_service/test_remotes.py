import json

from archerytimer.common.clock import FakeClock
from archerytimer.core.models import Command
from archerytimer.core_service.remotes import (
    RemoteRegistry,
    RemoteStore,
    mask_from_perms,
    perms_from_mask,
)
from archerytimer.hardware import mesh_types as mt

MAC = "aa:bb:cc:dd:ee:01"


def make(tmp_path=None):
    clock = FakeClock(1_000_000_000)
    sent = []
    wall = [1000.0]
    store = RemoteStore(tmp_path / "r.json" if tmp_path else None)
    reg = RemoteRegistry(clock, store=store, send=sent.append, wall=lambda: wall[0])
    return reg, clock, sent, wall


def pair(reg, perms=("primary", "pause"), mac=MAC, name="Fjarr"):
    reg.open_pairing(30)
    reg.on_request(mt.PairRequest(mac, name, "B"))
    assert reg.accept(mac, list(perms))


def test_mask_roundtrip_emergency_implicit():
    mask = mask_from_perms(["primary", "nonsense"])
    assert mask == 1 | mt.EMERGENCY_MASK_BIT
    assert perms_from_mask(mask) == ["primary", "emergency"]


def test_pairing_window_countdown_and_expiry():
    reg, clock, sent, _ = make()
    reg.open_pairing(10)
    assert sent == [mt.PairOpen(10)] and reg.pairing_open and reg.seconds_left == 10
    clock.advance_s(4.5)
    assert reg.seconds_left == 6
    clock.advance_s(6)
    assert not reg.pairing_open and reg.seconds_left == 0 and reg.window_active
    reg.tick()
    assert sent[-1] == mt.PairClose() and not reg.window_active


def test_request_outside_window_is_rejected_and_inside_is_pending():
    reg, _, sent, _ = make()
    reg.on_request(mt.PairRequest(MAC, "X", ""))
    assert sent == [mt.PairReject(MAC)] and reg.message()["pending"] == []
    reg.open_pairing(30)
    reg.on_request(mt.PairRequest(MAC, "X", "B"))
    assert reg.message()["pending"] == [
        {"id": MAC, "name": "X", "mac": MAC, "caps": "B", "seen_s": 0}
    ]
    assert reg.reject(MAC) and sent[-1] == mt.PairReject(MAC)
    assert not reg.accept(MAC, [])


def test_accept_stores_remote_and_message():
    reg, _, sent, _ = make()
    pair(reg)
    assert sent[-1] == mt.PairAccept(MAC, mask_from_perms(["primary", "pause"]))
    msg = reg.message()
    assert msg["pairing_open"] and msg["pending"] == []
    (r,) = msg["remotes"]
    assert r["id"] == MAC and r["name"] == "Fjarr"
    assert r["perms"] == ["primary", "pause", "emergency"]
    assert reg.set_perms(MAC, ["next"]) and reg.get(MAC).mask == mask_from_perms(["next"])
    assert reg.remove(MAC) and sent[-1] == mt.PairDelete(MAC) and reg.message()["remotes"] == []


def test_authorize_allowed_denied_unknown():
    reg, _, _, _ = make()
    pair(reg)
    cmd, res = reg.authorize(mt.RemoteCommand(MAC, 1, 1))
    assert res == 0 and cmd == Command("primary", {"source": "remote:Fjarr"})
    cmd, res = reg.authorize(mt.RemoteCommand(MAC, 5, 2))  # next not allowed
    assert cmd is None and res == 1
    cmd, res = reg.authorize(mt.RemoteCommand(MAC, 7, 3))  # emergency always
    assert res == 0 and cmd.name == "emergency"
    cmd, res = reg.authorize(mt.RemoteCommand(MAC, 99, 4))
    assert cmd is None and res == 1
    cmd, res = reg.authorize(mt.RemoteCommand("ff:ff", 7, 1))  # unknown remote, even emergency
    assert cmd is None and res == 1


def test_retransmit_same_counter_not_run_twice_and_acked_again():
    reg, _, sent, _ = make()
    pair(reg)
    assert reg.handle_command(mt.RemoteCommand(MAC, 1, 9)) is not None
    assert reg.handle_command(mt.RemoteCommand(MAC, 1, 9)) is None
    assert sent[-2:] == [mt.PairAck(MAC, 9, 0), mt.PairAck(MAC, 9, 0)]


def test_rate_limit_spares_emergency_and_recovers():
    reg, clock, _, _ = make()
    pair(reg, perms=("primary",))
    results = [reg.authorize(mt.RemoteCommand(MAC, 1, c))[1] for c in range(1, 9)]
    assert results == [0] * 5 + [1] * 3
    assert reg.authorize(mt.RemoteCommand(MAC, 7, 20))[1] == 0
    clock.advance_s(1.1)
    assert reg.authorize(mt.RemoteCommand(MAC, 1, 30))[1] == 0


def test_persistence_and_damaged_file(tmp_path):
    reg, _, _, _ = make(tmp_path)
    pair(reg)
    reg2, _, _, _ = make(tmp_path)
    assert reg2.macs() == [MAC] and reg2.get(MAC).name == "Fjarr"
    (tmp_path / "r.json").write_text("{nope", encoding="utf-8")
    assert make(tmp_path)[0].macs() == []
    (tmp_path / "r.json").write_text(json.dumps({"remotes": [{"mac": 1}]}), encoding="utf-8")
    assert make(tmp_path)[0].macs() == []


def test_handle_ui_commands_and_pair_state():
    reg, _, _, _ = make()
    assert reg.handle_ui("pair_open", {"seconds": "20"}) and reg.seconds_left == 20
    reg.on_request(mt.PairRequest(MAC, "R", ""))
    assert reg.handle_ui("pair_accept", {"id": MAC, "perms": ["stop_end"]})
    assert reg.handle_ui("remote_perms", {"id": MAC, "perms": ["back"]})
    assert reg.handle_ui("remote_remove", {"id": MAC})
    assert reg.handle_ui("pair_close", {}) and not reg.window_active
    assert not reg.handle_ui("something", {})
    reg.open_pairing(30)
    reg.on_pair_state(mt.PairState(False, 0))
    assert not reg.window_active


def test_discovery_renews_window_and_expires_stale_requests():
    reg, clock, sent, _ = make()
    assert reg.handle_ui("pair_open", {"seconds": 120, "discover": True})
    assert reg.discovering and reg.needs_tick and sent == [mt.PairOpen(120)]
    reg.on_request(mt.PairRequest(MAC, "node-0001", "L"))
    clock.advance_s(30)
    reg.tick()  # asked 30 s ago, the MCU repeats every ~10 s: it is gone
    assert reg.message()["pending"] == []
    clock.advance_s(60)  # 30 s left: nothing yet; then 15 s left: renewed within the same search
    reg.tick()
    assert sent == [mt.PairOpen(120)]
    clock.advance_s(15)
    reg.tick()
    assert sent[-1] == mt.PairOpen(120) and len(sent) == 2 and reg.discovering


def test_discovery_waits_while_someone_is_pending_and_stops_after_the_cap():
    reg, clock, sent, _ = make()
    reg.open_pairing(120, discover=True)
    reg.on_request(mt.PairRequest(MAC, "node-0001", "L"))
    clock.advance_s(110)
    reg.on_request(mt.PairRequest(MAC, "node-0001", "L"))  # still asking
    reg.tick()
    assert len(sent) == 1 and len(reg.message()["pending"]) == 1  # no renewal under the operator
    clock.advance_s(700)
    reg.tick()
    assert not reg.discovering and sent[-1] == mt.PairClose()


def test_rejected_device_is_not_listed_again_during_the_search():
    reg, _, _, _ = make()
    reg.open_pairing(120, discover=True)
    reg.on_request(mt.PairRequest(MAC, "node-0001", "L"))
    assert reg.reject(MAC)
    reg.on_request(mt.PairRequest(MAC, "node-0001", "L"))
    assert reg.message()["pending"] == []
    reg.close_pairing()
    reg.open_pairing(120, discover=True)  # a new search forgets the refusal
    reg.on_request(mt.PairRequest(MAC, "node-0001", "L"))
    assert len(reg.message()["pending"]) == 1

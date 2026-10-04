"""Leader side of follower access: registry state machine, enforcement, and the wired CoreService."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, FakeClock, MonotonicClock
from archerytimer.core.models import Light, PhaseSpec, Sequence
from archerytimer.core_service.followers import FollowerRegistry
from archerytimer.core_service.service import CoreService
from archerytimer.ipc import access
from archerytimer.ipc.messages import auth_msg, cmd_msg, join_msg, settings_msg, snapshot_from_dict
from archerytimer.ipc.server import IpcClient
from archerytimer.ipc.transport_inproc import InprocListener

MESH = "0123456789ABCDEF" * 2
CONFIGURE = cmd_msg("configure", {"sequence_id": "t", "groups": ["AB"], "total_ends": 1})
SEQ = Sequence(
    "t",
    {"sv": "Test", "en": "Test"},
    (
        PhaseSpec("PREP", NS_PER_S // 4, Light.RED, whistle_on_start=2),
        PhaseSpec("SHOOT", 60 * NS_PER_S, Light.GREEN, 1),
        PhaseSpec("END", 0, Light.RED, 3),
    ),
)


class FakeConn:
    """What the registry needs of a connection."""

    def __init__(self, local: bool = False) -> None:
        self.is_local = local
        self.ctx: dict[str, Any] = {}
        self.sent: list[dict[str, Any]] = []

    def send(self, msg: Any) -> None:
        self.sent.append(msg)

    def last(self, kind: str) -> Optional[dict[str, Any]]:
        for m in reversed(self.sent):
            if m["type"] == kind:
                return m
        return None


def make(tmp_path: Optional[Path] = None, **kw: Any) -> FollowerRegistry:
    counter = iter(range(1, 1000))
    return FollowerRegistry(
        FakeClock(start_ns=1_000_000_000),
        path=(tmp_path / "core_followers.json") if tmp_path else None,
        mesh_key_hex=MESH,
        leader_name="Leader",
        wall=lambda: 1000.0,
        rng=lambda n: bytes([next(counter)] * n),
        **kw,
    )


def join(reg: FollowerRegistry, conn: FakeConn, fid: str = "f1", name: str = "Pi 1") -> None:
    assert reg.gate(conn, join_msg(fid, name)) is False


def authenticate(reg: FollowerRegistry, conn: FakeConn, fid: str, key: str) -> dict[str, Any]:
    join(reg, conn, fid)
    nonce = conn.last("challenge")["nonce"]  # type: ignore[index]
    assert reg.gate(conn, auth_msg(fid, access.auth_mac(key, nonce))) is False
    return conn.last("access")  # type: ignore[return-value]


def approve(reg: FollowerRegistry, conn: FakeConn, fid: str = "f1", perms: Any = None) -> str:
    join(reg, conn, fid)
    assert reg.approve(fid, perms)
    return conn.last("access")["key"]  # type: ignore[index]


# ---------------------------------------------------------------- join / approve / auth


def test_unknown_join_is_pending_and_watch_only():
    reg = make()
    c = FakeConn()
    join(reg, c)
    acc = c.last("access")
    assert acc["status"] == "pending" and acc["perms"] == [] and "key" not in acc
    assert reg.get("f1").status == "pending"  # type: ignore[union-attr]
    assert reg.gate(c, cmd_msg("primary")) is False
    assert c.last("denied")["name"] == "primary"
    assert reg.gate(c, cmd_msg("emergency")) is True
    assert reg.gate(c, settings_msg({"x": 1})) is False


def test_full_flow_approve_then_auth_on_new_connection():
    reg = make()
    c = FakeConn()
    join(reg, c)
    assert reg.approve("f1")  # default: operator preset
    acc = c.last("access")
    assert acc["status"] == "approved" and acc["perms"] == list(access.PRESETS["operator"])
    assert acc["preset"] == "operator" and acc["mesh_key"] == MESH and acc["leader"] == "Leader"
    key = acc["key"]
    assert len(key) == 32
    assert reg.gate(c, cmd_msg("primary")) is True  # live connection is trusted right away

    c2 = FakeConn()  # reconnect: must prove the key
    join(reg, c2)
    assert c2.last("challenge") is not None
    assert reg.gate(c2, cmd_msg("primary")) is False  # not yet authenticated
    nonce = c2.last("challenge")["nonce"]  # type: ignore[index]
    reg.gate(c2, auth_msg("f1", access.auth_mac(key, nonce)))
    ok = c2.last("access")
    assert ok["status"] == "approved" and "key" not in ok and ok["mesh_key"] == MESH
    assert reg.gate(c2, cmd_msg("primary")) is True
    assert reg.gate(c2, cmd_msg("reset")) is False  # not in the operator preset


def test_key_sent_once():
    reg = make()
    c = FakeConn()
    key = approve(reg, c)
    reg.set_perms("f1", ["primary"])
    c2 = FakeConn()
    authenticate(reg, c2, "f1", key)
    with_key = [m for m in c.sent + c2.sent if m.get("key")]
    assert len(with_key) == 1 and with_key[0]["key"] == key  # the access key goes once
    assert c2.last("access")["mesh_key"] == MESH  # the radio key on every authenticated connect


def test_radio_key_reset_reaches_connected_followers():
    reg = make()
    c = FakeConn()
    approve(reg, c)
    reg.set_mesh_key("AB" * 16)
    last = c.last("access")
    assert last["mesh_key"] == "AB" * 16 and "key" not in last


def test_wrong_mac_denied_and_challenge_single_use():
    reg = make()
    key = approve(reg, FakeConn())
    c = FakeConn()
    join(reg, c)
    nonce = c.last("challenge")["nonce"]  # type: ignore[index]
    reg.gate(c, auth_msg("f1", "00" * 32))
    assert c.last("access")["status"] == "denied"
    assert reg.gate(c, cmd_msg("primary")) is False
    # the right answer to the used-up challenge no longer counts
    reg.gate(c, auth_msg("f1", access.auth_mac(key, nonce)))
    assert reg.gate(c, cmd_msg("primary")) is False


def test_auth_for_other_id_or_malformed_ignored():
    reg = make()
    key = approve(reg, FakeConn(), "f1")
    approve(reg, FakeConn(), "f2")
    c = FakeConn()
    join(reg, c, "f1")
    nonce = c.last("challenge")["nonce"]  # type: ignore[index]
    reg.gate(c, auth_msg("f2", access.auth_mac(key, nonce)))
    assert reg.gate(c, cmd_msg("primary")) is False
    for bad in (
        {"type": "join", "v": 1},
        {"type": "join", "v": 1, "id": 5, "name": "x"},
        {"type": "join", "v": 1, "id": "", "name": "x"},
        {"type": "auth", "v": 1},
        {"type": "auth", "v": 1, "id": "f1", "mac": 7},
        {"type": "auth", "v": 1, "id": "f1", "mac": "zz"},
    ):
        assert reg.gate(FakeConn(), bad) is False
    c3 = FakeConn()
    join(reg, c3, "f1")
    reg.gate(c3, auth_msg("f1", "not-hex"))  # garbage mac: denied, no exception
    assert c3.last("access")["status"] == "denied"
    assert reg.ids() == ["f1", "f2"]


def test_loopback_always_allowed_and_only_loopback_runs_ui_commands():
    reg = make()
    local, remote = FakeConn(local=True), FakeConn()
    for name in ("primary", "reset", "configure", "clear_emergency"):
        assert reg.gate(local, cmd_msg(name)) is True
    assert reg.gate(local, settings_msg({"a": 1})) is True
    join(reg, remote)
    reg.gate(remote, cmd_msg("follower_approve", {"id": "f1"}))
    assert reg.get("f1").status == "pending"  # type: ignore[union-attr]
    assert remote.last("denied")["name"] == "follower_approve"
    reg.gate(local, cmd_msg("follower_approve", {"id": "f1"}))
    assert reg.get("f1").status == "approved"  # type: ignore[union-attr]


def test_unknown_things_from_remote_refused():
    reg = make()
    c = FakeConn()
    approve(reg, c)
    for msg in (cmd_msg("take_over"), cmd_msg("pair_open"), {"type": "bogus"}, cmd_msg("")):
        assert reg.gate(c, msg) is False


# ---------------------------------------------------------------- operator actions


def test_perms_update_takes_effect_at_once_and_is_pushed():
    reg = make()
    c = FakeConn()
    approve(reg, c)
    assert reg.gate(c, cmd_msg("primary")) is True
    assert reg.gate(c, cmd_msg("reset")) is False
    local = FakeConn(local=True)
    reg.gate(local, cmd_msg("follower_perms", {"id": "f1", "perms": ["reset", "bogus"]}))
    push = c.last("access")
    assert push["perms"] == ["reset"] and push["preset"] == "custom" and "key" not in push
    assert reg.gate(c, cmd_msg("reset")) is True
    assert reg.gate(c, cmd_msg("primary")) is False
    assert reg.gate(c, cmd_msg("emergency")) is True
    reg.set_perms("f1", list(access.PRESETS["full"]))
    assert c.last("access")["preset"] == "full"


def test_approve_with_explicit_perms_and_view():
    reg = make()
    c = FakeConn()
    join(reg, c)
    reg.gate(FakeConn(local=True), cmd_msg("follower_approve", {"id": "f1", "perms": []}))
    assert c.last("access")["perms"] == [] and c.last("access")["preset"] == "view"
    assert reg.gate(c, cmd_msg("primary")) is False
    assert reg.gate(c, cmd_msg("emergency")) is True


def test_block_cuts_live_connection_and_refuses_rejoin():
    reg = make()
    c = FakeConn()
    key = approve(reg, c)
    assert reg.block("f1")
    assert c.last("access")["status"] == "blocked"
    assert reg.gate(c, cmd_msg("primary")) is False
    c2 = FakeConn()
    join(reg, c2)
    assert c2.last("access")["status"] == "blocked" and c2.last("challenge") is None
    assert reg.get("f1").key == ""  # type: ignore[union-attr]
    # approving again unblocks with a new key
    c3 = FakeConn()
    join(reg, c3)
    assert reg.approve("f1") is True
    assert c.last("access")["status"] == "blocked"  # old connection stays cut
    assert key not in (reg.get("f1").key,)  # type: ignore[union-attr]


def test_remove_forgets_and_next_join_is_pending():
    reg = make()
    c = FakeConn()
    key = approve(reg, c)
    assert reg.remove("f1") and reg.get("f1") is None
    assert c.last("access")["status"] == "denied"
    assert reg.gate(c, cmd_msg("primary")) is False
    assert reg.remove("f1") is False
    c2 = FakeConn()
    join(reg, c2)
    assert c2.last("access")["status"] == "pending"
    assert reg.get("f1").key == ""  # type: ignore[union-attr]
    assert key  # old key is gone with the record


def test_persistence_across_restart(tmp_path: Path):
    reg = make(tmp_path)
    key = approve(reg, FakeConn(), "f1")
    join(reg, FakeConn(), "f2", "Pending one")
    reg.set_perms("f1", ["pause"])
    reg2 = make(tmp_path)
    assert reg2.ids() == ["f1", "f2"]
    assert reg2.get("f1").status == "approved" and reg2.get("f1").perms == ("pause",)  # type: ignore[union-attr]
    assert reg2.get("f2").status == "pending"  # type: ignore[union-attr]
    c = FakeConn()
    acc = authenticate(reg2, c, "f1", key)
    assert acc["status"] == "approved"
    assert reg2.gate(c, cmd_msg("pause")) is True
    assert reg2.gate(c, cmd_msg("primary")) is False
    assert not list(tmp_path.glob("*.tmp"))


def test_damaged_file_ignored(tmp_path: Path):
    (tmp_path / "core_followers.json").write_text("{not json", encoding="utf-8")
    assert make(tmp_path).ids() == []
    (tmp_path / "core_followers.json").write_text(
        json.dumps({"followers": [{"id": "a", "status": "approved", "key": "zz"}]}), "utf-8"
    )
    assert make(tmp_path).ids() == []


def test_followers_message_and_changes():
    changes: list[int] = []
    reg = make(on_change=lambda: changes.append(1))
    c = FakeConn()
    join(reg, c)
    assert changes
    snap = reg.message()["followers"]
    assert snap == [
        {
            "id": "f1",
            "name": "Pi 1",
            "status": "pending",
            "connected": True,
            "preset": "view",
            "perms": [],
            "last_seen_s": 0,
        }
    ]
    reg.approve("f1", ["primary"])
    row = reg.message()["followers"][0]
    assert row["status"] == "approved" and row["perms"] == ["primary"] and "key" not in row
    n = len(changes)
    reg.on_disconnect(c)
    assert len(changes) == n + 1
    assert reg.message()["followers"][0]["connected"] is False


def test_tick_updates_last_seen_and_reports_only_changes():
    reg = make()
    c = FakeConn()
    approve(reg, c)
    reg.published()
    reg.tick()
    reg.published()
    assert reg.tick() is False  # nothing visible changed


def test_list_is_capped():
    reg = make()
    for i in range(80):
        join(reg, FakeConn(), f"id{i}")
    assert len(reg.ids()) == 64


# ---------------------------------------------------------------- wired into the service


class PeerListener(InprocListener):
    """Marks connections made with ``connect(peer=...)`` as coming from that address."""

    def __init__(self) -> None:
        super().__init__()
        self.peers: list[str] = []

    def accept(self, timeout: float):  # type: ignore[no-untyped-def]
        conn = super().accept(timeout)
        if conn is not None and self.peers:
            conn.peer = self.peers.pop(0)  # type: ignore[attr-defined]
        return conn


def wait_for(cond: Callable[[], bool], timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def pump(client: IpcClient, kind: str, pred: Callable[[dict[str, Any]], bool] = lambda m: True):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        m = client.get(0.1)
        if m and m["type"] == kind and pred(m):
            return m
    raise AssertionError(f"no {kind} message")


def test_service_end_to_end():
    listener = PeerListener()
    reg = make()
    svc = CoreService(MonotonicClock(), {"t": SEQ}, listener, followers=reg)
    clients: list[IpcClient] = []

    def connect(peer: str) -> IpcClient:
        listener.peers.append(peer)
        c = IpcClient(listener.connect())
        clients.append(c)
        return c

    svc.start()
    try:
        ui = connect("127.0.0.1")
        pump(ui, "followers")  # sent on connect
        ui.send(CONFIGURE)
        pump(ui, "state", lambda m: snapshot_from_dict(m["state"]).total_ends == 1)

        remote = connect("192.168.1.20")
        remote.send(join_msg("f1", "Pi 1"))
        assert pump(remote, "access")["status"] == "pending"
        row = pump(ui, "followers", lambda m: bool(m["followers"]))["followers"][0]
        assert row["status"] == "pending" and row["connected"] is True

        remote.send(cmd_msg("primary"))
        assert pump(remote, "denied")["name"] == "primary"
        remote.send(cmd_msg("emergency"))
        pump(ui, "state", lambda m: snapshot_from_dict(m["state"]).emergency)

        remote.send(cmd_msg("follower_block", {"id": "f1"}))  # remote cannot run UI commands
        assert pump(remote, "denied")["name"] == "follower_block"
        assert reg.get("f1").status == "pending"  # type: ignore[union-attr]

        ui.send(cmd_msg("follower_approve", {"id": "f1"}))
        acc = pump(remote, "access", lambda m: m["status"] == "approved")
        assert acc["key"] and acc["mesh_key"] == MESH
        pump(ui, "followers", lambda m: m["followers"][0]["status"] == "approved")

        # a late UI gets the current list on connect
        ui2 = connect("127.0.0.1")
        assert pump(ui2, "followers")["followers"][0]["status"] == "approved"

        remote.send(cmd_msg("clear_emergency", {"mode": "continue"}))
        assert pump(remote, "denied")["name"] == "clear_emergency"

        ui.send(cmd_msg("follower_block", {"id": "f1"}))
        assert pump(remote, "access", lambda m: m["status"] == "blocked")
        remote.send(cmd_msg("primary"))
        assert pump(remote, "denied")["name"] == "primary"

        remote.close()
        clients.remove(remote)
        pump(ui, "followers", lambda m: m["followers"][0]["connected"] is False)
    finally:
        for c in clients:
            c.close()
        svc.stop()


def test_pending_follower_that_leaves_is_forgotten_but_approved_one_stays():
    reg = make()
    passer = FakeConn()
    join(reg, passer, "pi", "Pi passing by")
    assert reg.get("pi") is not None
    reg.on_disconnect(passer)
    assert reg.get("pi") is None  # never approved, gone: not listed
    kept = FakeConn()
    approve(reg, kept)
    reg.on_disconnect(kept)
    assert reg.get("f1") is not None and reg.get("f1").status == "approved"  # type: ignore[union-attr]

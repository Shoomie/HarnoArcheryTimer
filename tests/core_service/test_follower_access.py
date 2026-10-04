"""Follower side of the access contract: join, approval, challenge/auth, denial, gating."""

from __future__ import annotations

import json
import threading
import time

from archerytimer.common.clock import FakeClock
from archerytimer.core_service.cluster import FollowerService, FollowStore
from archerytimer.core_service.radio_keys import RadioKeys
from archerytimer.ipc import access
from archerytimer.ipc.messages import access_msg, challenge_msg, cmd_msg, denied_msg
from archerytimer.ipc.server import IpcClient
from archerytimer.ipc.transport import ConnectionClosed
from archerytimer.ipc.transport_inproc import InprocListener

KEY = "AB" * 32
MESH = "0123456789ABCDEF" * 2
NONCE = "11" * 16


def wait_for(cond, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class FakeLeader:
    """Accepts follower connections and speaks the contract; ``script`` decides per join."""

    def __init__(self, listener: InprocListener) -> None:
        self.listener = listener
        self.received: list[dict] = []
        self.mode = "pending"  # pending | approve | challenge
        self.perms = ["primary", "pause"]
        self._stop = threading.Event()
        self.conn = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            conn = self.listener.accept(0.05)
            if conn is None:
                continue
            self.conn = conn
            try:
                while not self._stop.is_set():
                    msg = conn.recv(0.05)
                    if msg is None:
                        continue
                    self.received.append(msg)
                    self._answer(conn, msg)
            except ConnectionClosed:
                pass

    def _answer(self, conn, msg) -> None:
        kind = msg.get("type")
        if kind == "join":
            if self.mode == "pending":
                conn.send(access_msg("pending", [], "view", "Leader"))
            elif self.mode == "approve":
                conn.send(
                    access_msg("approved", self.perms, "custom", "Leader", key=KEY, mesh_key=MESH)
                )
            else:
                conn.send(challenge_msg(NONCE))
        elif kind == "auth":
            if access.macs_equal(str(msg["mac"]), access.auth_mac(KEY, NONCE)):
                conn.send(access_msg("approved", self.perms, "custom", "Leader"))
            else:
                conn.send(access_msg("denied", [], "view", "Leader"))
                conn.send(denied_msg("auth"))

    def of(self, kind: str) -> list[dict]:
        return [m for m in list(self.received) if m.get("type") == kind]

    def stop(self) -> None:
        self._stop.set()
        if self.conn is not None:
            self.conn.close()
        self.thread.join(timeout=2)


def build(tmp_path, store_key: str | None = None, mode: str = "pending", perms=None):
    clock = FakeClock()
    leader_listener, own_listener = InprocListener(), InprocListener()
    leader = FakeLeader(leader_listener)
    leader.mode = mode
    if perms:
        leader.perms = perms
    path = tmp_path / "core_follow.json"
    if store_key:
        path.write_text(json.dumps({"key": store_key, "leader": "Leader"}), encoding="utf-8")
    keys = RadioKeys(tmp_path / "core_radio.json")
    svc = FollowerService(
        clock,
        leader_listener.connect,
        own_listener,
        node_id="abcd1234",
        node_name="Pi 2",
        access_store=FollowStore(path),
        radio_keys=keys,
    )
    svc.start()
    ui = IpcClient(own_listener.connect())
    return svc, leader, ui, keys, path


def last_follower(ui, store: list) -> dict | None:
    while True:
        msg = ui.get(0.01)
        if msg is None:
            return store[-1] if store else None
        if msg["type"] == "follower":
            store.append(msg)


def test_join_pending_then_approved_stores_key_and_mesh_key(tmp_path):
    svc, leader, ui, keys, path = build(tmp_path)
    seen: list[dict] = []
    try:
        assert wait_for(lambda: leader.of("join"))
        join = leader.of("join")[0]
        assert join["id"] == "abcd1234" and join["name"] == "Pi 2"
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("status") == "pending")

        leader.conn.send(
            access_msg("approved", ["primary", "pause"], "custom", "Leader", key=KEY, mesh_key=MESH)
        )
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("status") == "approved")
        assert seen[-1]["perms"] == ["primary", "pause"]
        assert json.loads(path.read_text(encoding="utf-8"))["key"] == KEY
        assert keys.mesh_key == MESH
        assert (
            json.loads((tmp_path / "core_radio.json").read_text(encoding="utf-8"))["mesh_key"]
            == MESH
        )
    finally:
        ui.close()
        svc.stop()
        leader.stop()


def test_reconnect_challenge_is_answered_with_the_stored_key(tmp_path):
    svc, leader, ui, _keys, _path = build(tmp_path, store_key=KEY, mode="challenge")
    seen: list[dict] = []
    try:
        assert wait_for(lambda: leader.of("auth"))
        assert leader.of("auth")[0]["mac"] == access.auth_mac(KEY, NONCE)
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("status") == "approved")
    finally:
        ui.close()
        svc.stop()
        leader.stop()


def test_wrong_key_is_denied_and_published(tmp_path):
    svc, leader, ui, _keys, _path = build(tmp_path, store_key="CD" * 32, mode="challenge")
    seen: list[dict] = []
    try:
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("status") == "denied")
        assert seen[-1]["perms"] == []
        assert seen[-1].get("last_denied") == "auth"
    finally:
        ui.close()
        svc.stop()
        leader.stop()


def test_commands_without_permission_are_not_forwarded_but_emergency_is(tmp_path):
    svc, leader, ui, _keys, _path = build(tmp_path, mode="approve", perms=["primary"])
    seen: list[dict] = []
    try:
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("status") == "approved")
        ui.send(cmd_msg("pause"))  # not allowed
        ui.send(cmd_msg("primary"))
        ui.send(cmd_msg("emergency"))
        assert wait_for(lambda: len(leader.of("cmd")) >= 2)
        time.sleep(0.2)
        names = [m["name"] for m in leader.of("cmd")]
        assert names == ["primary", "emergency"]
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("last_denied") == "pause")
    finally:
        ui.close()
        svc.stop()
        leader.stop()


def test_pending_follower_forwards_only_emergency(tmp_path):
    svc, leader, ui, _keys, _path = build(tmp_path)
    seen: list[dict] = []
    try:
        assert wait_for(lambda: (last_follower(ui, seen) or {}).get("status") == "pending")
        ui.send(cmd_msg("primary"))
        ui.send(cmd_msg("emergency"))
        assert wait_for(lambda: leader.of("cmd"))
        time.sleep(0.2)
        assert [m["name"] for m in leader.of("cmd")] == ["emergency"]
    finally:
        ui.close()
        svc.stop()
        leader.stop()


def test_link_message_carries_clock_sync_fields(tmp_path):
    svc, leader, ui, _keys, _path = build(tmp_path)
    try:
        svc._publish_link()
        link = None
        end = time.monotonic() + 3
        while time.monotonic() < end and link is None:
            msg = ui.get(0.1)
            if msg and msg["type"] == "link":
                link = msg
        assert link is not None
        assert "leader_rtt_ms" in link and "leader_offset_ms" in link
    finally:
        ui.close()
        svc.stop()
        leader.stop()


def test_store_ignores_damaged_file_and_radio_key_validates(tmp_path):
    bad = tmp_path / "core_follow.json"
    bad.write_text("{not json", encoding="utf-8")
    assert FollowStore(bad).key == ""
    keys = RadioKeys(None)
    for wrong in ("", "XYZ", "0" * 31, "G" * 32):
        try:
            keys.set_mesh_key(wrong)
        except ValueError:
            continue
        raise AssertionError(f"accepted {wrong!r}")
    keys.set_mesh_key(MESH.lower())
    assert keys.mesh_key == MESH

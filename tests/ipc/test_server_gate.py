"""IpcServer: client identity, the per-connection gate and the disconnect hook."""

from __future__ import annotations

import time
from typing import Any, Callable

from archerytimer.ipc.messages import cmd_msg, hello_msg
from archerytimer.ipc.server import ClientInfo, IpcClient, IpcServer, _is_loopback
from archerytimer.ipc.transport_inproc import InprocListener


class PeerListener(InprocListener):
    def __init__(self, *peers: str) -> None:
        super().__init__()
        self.peers = list(peers)

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


def hello() -> Any:
    return hello_msg("t", {}, {}, 0)


def test_is_loopback():
    assert _is_loopback(None) and _is_loopback("127.0.0.1") and _is_loopback("::1")
    assert _is_loopback("::ffff:127.0.0.1")
    assert not _is_loopback("192.168.1.5") and not _is_loopback("garbage")


def test_without_gate_behaviour_unchanged():
    got: list[Any] = []
    listener = PeerListener("10.0.0.9")
    server = IpcServer(listener, hello(), got.append)
    server.start()
    try:
        c = IpcClient(listener.connect())
        c.send(cmd_msg("primary"))
        c.send({"type": "join", "v": 1})  # unknown type: ignored
        assert wait_for(lambda: len(got) == 1)
        c.close()
    finally:
        server.stop()


def test_gate_sees_identity_answers_one_client_and_filters():
    seen: list[ClientInfo] = []
    got: list[Any] = []
    gone: list[ClientInfo] = []

    def gate(client: ClientInfo, msg: Any) -> bool:
        seen.append(client)
        client.ctx["n"] = client.ctx.get("n", 0) + 1
        if msg["type"] == "join":
            client.send({"type": "access", "v": 1, "status": "pending"})
            return False
        if msg["type"] == "boom":
            raise RuntimeError("gate bug")
        return client.is_local

    listener = PeerListener("127.0.0.1", "192.168.1.7")
    server = IpcServer(listener, hello(), got.append, gate=gate, on_disconnect=gone.append)
    server.start()
    try:
        local = IpcClient(listener.connect())
        local.get()
        remote = IpcClient(listener.connect())
        remote.get()
        remote.send({"type": "join", "v": 1})
        reply = remote.get()
        assert reply is not None and reply["type"] == "access"
        assert local.get(0.2) is None  # the answer went to that connection only
        remote.send({"type": "boom", "v": 1})  # gate raising fails closed
        remote.send(cmd_msg("primary"))  # not local: filtered
        local.send(cmd_msg("pause"))
        assert wait_for(lambda: len(got) == 1)
        assert got[0]["name"] == "pause"
        infos = {c.peer: c for c in seen}
        assert infos["127.0.0.1"].is_local and not infos["192.168.1.7"].is_local
        assert infos["192.168.1.7"].ctx["n"] == 3
        remote.close()
        assert wait_for(lambda: len(gone) == 1)
        assert gone[0].peer == "192.168.1.7"
        local.close()
    finally:
        server.stop()


def test_followers_snapshot_is_replayed_to_new_clients():
    listener = PeerListener()
    server = IpcServer(listener, hello(), lambda m: None)
    server.start()
    try:
        server.publish({"type": "followers", "v": 1, "followers": []})
        c = IpcClient(listener.connect())
        kinds = []
        while (m := c.get(0.3)) is not None:
            kinds.append(m["type"])
        assert kinds == ["hello", "followers"]
        c.close()
    finally:
        server.stop()

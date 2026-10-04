import json

from archerytimer.core import models as m
from archerytimer.core_service.netdisco import LeaderBrowser
from archerytimer.core_service.node import (
    NodeControl,
    NodeSettings,
    NodeStore,
    from_table,
)
from archerytimer.ui_client.screens.network import next_leader


def make(tmp_path, **kw):
    sent = []
    applied = []
    ctl = NodeControl(
        kw.pop("active", NodeSettings()),
        store=NodeStore(tmp_path / "n.json"),
        on_apply=lambda: applied.append(1),
        **kw,
    )
    ctl.bind(sent.append, None)
    return ctl, sent, applied


def settings(**values):
    return {"type": "settings", "values": values}


def snap(mode):
    return m.Snapshot(**{**_BASE, "mode": mode})


_BASE = {f: None for f in m.Snapshot.__dataclass_fields__}


def test_role_change_is_stored_and_needs_apply(tmp_path):
    ctl, sent, applied = make(tmp_path)
    assert ctl.handle_message(settings(node_role="follower", node_leader="10.0.0.5:8765"))
    assert sent[-1]["restart_needed"] and sent[-1]["active_role"] == "standalone"
    assert NodeStore(tmp_path / "n.json").load(NodeSettings()).role == "follower"
    assert ctl.handle_message({"type": "cmd", "name": "apply_network"})
    assert applied == [1]


def test_apply_refused_while_busy_or_locked_or_unchanged(tmp_path):
    ctl, _, applied = make(tmp_path)
    assert not ctl.apply()  # nothing pending
    ctl.on_settings({"node_role": "leader"})
    ctl._busy = True
    assert not ctl.apply()
    ctl._busy = False
    locked, _, applied2 = make(tmp_path, locked=True)
    locked.on_settings({"node_role": "leader"})
    assert locked.wanted.role == "standalone" and not locked.apply()
    assert applied == [] and applied2 == []


def test_invalid_values_ignored_and_foreign_keys_not_consumed(tmp_path):
    ctl, _, _ = make(tmp_path)
    assert ctl.handle_message(settings(node_role="boss", espnow="loud"))
    assert ctl.wanted == NodeSettings()
    assert not ctl.handle_message(settings(node_role="leader", volume=0.5))  # volume is not ours


def test_from_table_leader_means_follower():
    assert from_table({"leader": "1.2.3.4:8765", "espnow": "auto"}) == NodeSettings(
        "follower", "1.2.3.4:8765", "auto"
    )
    assert from_table({}) == NodeSettings()


def test_store_survives_garbage(tmp_path):
    p = tmp_path / "n.json"
    p.write_text("{nope", encoding="utf-8")
    assert NodeStore(p).load(NodeSettings(role="leader")).role == "leader"
    p.write_text(json.dumps({"role": "follower"}), encoding="utf-8")
    assert NodeStore(p).load(NodeSettings()).role == "follower"


def test_browser_lists_and_expires_leaders():
    now = [0.0]
    changes = []
    b = LeaderBrowser(on_change=lambda: changes.append(1), now=lambda: now[0])
    b.hear(
        json.dumps({"app": "archerytimer", "port": 8765, "name": "Klubben"}).encode(), "10.0.0.2"
    )
    b.hear(b"not json", "10.0.0.9")
    b.hear(json.dumps({"app": "other", "port": 1}).encode(), "10.0.0.9")
    assert b.leaders() == [{"name": "Klubben", "addr": "10.0.0.2:8765"}]
    now[0] = 10.0
    assert b.leaders() == []
    b.notify()
    assert len(changes) == 2


def test_next_leader_cycles():
    found = [{"name": "A", "addr": "a:1"}, {"name": "B", "addr": "b:1"}]
    assert next_leader("", found) == "a:1"
    assert next_leader("a:1", found) == "b:1"
    assert next_leader("b:1", found) == ""
    assert next_leader("old:1", found) == ""


def test_lights_toggle_applies_without_restart_and_survives_locking(tmp_path):
    class Worker:
        def __init__(self):
            self.calls = []

        def set_lights(self, on):
            self.calls.append(on)

        def set_espnow_mode(self, mode):
            pass

    for locked in (False, True):
        ctl, sent, _ = make(tmp_path, locked=locked)
        w = Worker()
        ctl.bind(sent.append, w)
        ctl.start()
        ctl.handle_message(settings(lights=False, node_role="leader"))
        assert w.calls == [True, False]
        # the role change in the same message is a pending restart unless start flags lock it
        assert sent[-1]["lights"] is False and sent[-1]["restart_needed"] == (not locked)
        assert NodeStore(tmp_path / "n.json").load(NodeSettings()).lights is False
        assert ctl.wanted.role == ("standalone" if locked else "leader")


# ---- mesh v2: name, take over, roster, remotes -------------------------------------------


def make_mesh(tmp_path, **kw):
    from archerytimer.common.clock import FakeClock
    from archerytimer.core_service.remotes import RemoteRegistry
    from archerytimer.core_service.roster import Roster

    sent, cmds, resets, frames = [], [], [], []
    clock = FakeClock(1_000_000_000)
    remotes = RemoteRegistry(clock, send=frames.append)
    ctl = NodeControl(
        kw.pop("active", NodeSettings(role="leader")),
        store=NodeStore(tmp_path / "n.json"),
        roster=Roster("me"),
        node_id="me",
        remotes=remotes,
        submit_command=cmds.append,
        on_reset_key=lambda: resets.append(1),
        on_forget_key=lambda: resets.append("forget"),
        **kw,
    )
    ctl.bind(sent.append, None)
    return ctl, sent, cmds, resets, frames, clock


def test_node_name_setting_is_live_stored_and_not_locked(tmp_path):
    ctl, sent, *_ = make_mesh(tmp_path, locked=True)
    ctl.start()
    assert ctl.handle_message(settings(node_name="  Hallen  "))
    assert (
        ctl.name == "Hallen"
        and NodeStore(tmp_path / "n.json").load(NodeSettings()).name == "Hallen"
    )
    roster = [s for s in sent if s["type"] == "roster"][-1]
    assert roster["devices"][0]["name"] == "Hallen" and roster["master"] == "Hallen"


def test_take_over_rules(tmp_path):
    ctl, _, _, _, _, _ = make_mesh(tmp_path, active=NodeSettings(role="follower", leader="x:1"))
    applied = []
    ctl._on_apply = lambda: applied.append(1)
    ctl._busy = True
    assert ctl.take_over() == "busy" and applied == [] and ctl.wanted.role == "follower"
    assert ctl.take_over(force=True) == "restart" and applied == [1]
    assert ctl.wanted.role == "leader" and ctl.wanted.leader == ""
    assert NodeStore(tmp_path / "n.json").load(NodeSettings()).role == "leader"
    ctl2, *_ = make_mesh(tmp_path, active=NodeSettings(role="follower"), locked=True)
    assert ctl2.take_over(force=True) == "locked"
    ctl3, *_ = make_mesh(tmp_path)
    assert ctl3.take_over() == "already"


def test_take_over_command_passes_force(tmp_path):
    ctl, *_ = make_mesh(tmp_path, active=NodeSettings(role="follower"))
    applied = []
    ctl._on_apply = lambda: applied.append(1)
    ctl._busy = True
    assert ctl.handle_message({"type": "cmd", "name": "take_over", "args": {}})
    assert applied == []
    assert ctl.handle_message({"type": "cmd", "name": "take_over", "args": {"force": True}})
    assert applied == [1]


def test_pairing_commands_remote_commands_and_reset_key(tmp_path):
    from archerytimer.hardware import mesh_types as mt

    ctl, sent, cmds, resets, frames, clock = make_mesh(tmp_path)
    ctl.start()
    assert ctl.handle_message({"type": "cmd", "name": "pair_open", "args": {"seconds": 30}})
    assert sent[-1]["type"] == "remotes" and sent[-1]["pairing_open"]
    ctl.on_mesh(mt.PairRequest("m1", "Fjarr", "B"))
    assert sent[-1]["pending"][0]["id"] == "m1"
    ctl.handle_message(
        {"type": "cmd", "name": "pair_accept", "args": {"id": "m1", "perms": ["primary"]}}
    )
    assert sent[-1]["remotes"][0]["name"] == "Fjarr"
    ctl.on_mesh(mt.RemoteCommand("m1", 1, 1))
    assert [c.name for c in cmds] == ["primary"] and frames[-1] == mt.PairAck("m1", 1, 0)
    ctl.on_mesh(mt.RemoteCommand("m1", 5, 2))
    assert len(cmds) == 1 and frames[-1] == mt.PairAck("m1", 2, 1)
    assert ctl.handle_message({"type": "cmd", "name": "radio_reset_key"}) and resets == [1]
    assert ctl.handle_message({"type": "cmd", "name": "radio_forget_key"})
    assert resets == [1, "forget"]
    clock.advance_s(31)
    ctl.tick()
    assert sent[-1]["pairing_open"] is False


def test_roster_published_from_radio_and_lan(tmp_path):
    from archerytimer.core_service.netdisco import LeaderBrowser
    from archerytimer.hardware import mesh_types as mt

    browser = LeaderBrowser(own_id="me")
    ctl, sent, *_ = make_mesh(tmp_path, browser=browser)
    browser.start = lambda: None  # no sockets in unit tests
    ctl.start()
    browser.hear(
        json.dumps(
            {"app": "archerytimer", "port": 1, "id": "o", "name": "Annan", "role": "leader"}
        ).encode(),
        "10.0.0.2",
    )
    r = [s for s in sent if s["type"] == "roster"][-1]
    assert r["conflict"] == ["Annan", ctl.name]
    ctl.on_mesh(mt.RosterEntry("aa", mt.KIND_NODE, "", 60, "1", "Lampa"))
    r = [s for s in sent if s["type"] == "roster"][-1]
    assert {d["id"] for d in r["devices"]} == {"me", "o", "aa"}


def test_radio_sentinel_is_accepted_and_persisted(tmp_path):
    ctl, _, _ = make(tmp_path)
    assert ctl.handle_message(settings(node_role="follower", node_leader="radio"))
    assert ctl.wanted.role == "follower" and ctl.wanted.leader == "radio"
    loaded = NodeStore(tmp_path / "n.json").load(NodeSettings())
    assert (loaded.role, loaded.leader) == ("follower", "radio")
    assert from_table({"leader": "radio"}) == NodeSettings("follower", "radio")

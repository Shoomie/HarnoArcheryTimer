from archerytimer.core_service.netdisco import Instance
from archerytimer.core_service.roster import Roster, signal_label
from archerytimer.hardware import mesh_types as mt


def make(role="leader", follows=""):
    now = [100.0]
    r = Roster("me", now=lambda: now[0])
    r.set_self("Min", role, follows, "idle", "0.0.1")
    return r, now


def test_self_only_leader_is_master():
    r, _ = make()
    (d,) = r.devices()
    assert d["this"] and d["role"] == "leader" and d["via"] == "self" and d["kind"] == "core"
    assert r.master() == "Min" and r.conflict() == []
    assert r.message()["type"] == "roster"


def test_standalone_maps_to_alone():
    r, _ = make("standalone")
    assert r.devices()[0]["role"] == "alone" and r.master() == "Min"


def test_follower_master_from_lan_and_followers_listed_on_leader():
    r, _ = make("follower", "Huvud")
    r.set_instances(
        [
            Instance("h", "Huvud", "10.0.0.1:8765", "leader", state="running"),
            Instance("me", "Min", "x:1", "follower"),  # own echo is dropped
        ]
    )
    assert r.master() == "Huvud" and len(r.devices()) == 2
    assert r.devices()[0]["follows"] == "Huvud" and r.devices()[1]["via"] == "lan"
    lead, _ = make("leader")
    lead.set_instances(
        [
            Instance("f", "Fa", "a:1", "follower", follows="Min"),
            Instance("g", "Ga", "b:1", "follower", follows="X"),
        ]
    )
    assert lead.followers() == ["Fa"]


def test_leader_conflict_lan_and_own():
    r, _ = make("leader")
    r.set_instances([Instance("o", "Annan", "a:1", "leader")])
    assert r.conflict() == ["Annan", "Min"]
    r2, _ = make("standalone")
    r2.set_instances([Instance("o", "Annan", "a:1", "leader")])
    assert r2.conflict() == []


def test_radio_devices_and_gone_and_signal():
    r, now = make()
    r.on_mesh(mt.RosterEntry("aa", mt.KIND_NODE, "L", 60, "1.0", "Lampa"))
    r.on_mesh(mt.RosterEntry("bb", mt.KIND_REMOTE, "", 90, "1.0", ""))
    now[0] = 105.0
    devs = {d["id"]: d for d in r.devices()}
    assert devs["aa"]["kind"] == "module" and devs["aa"]["role"] == "node"
    assert devs["aa"]["signal"] == "good" and devs["aa"]["last_seen_s"] == 5.0
    assert devs["bb"]["kind"] == "remote" and devs["bb"]["name"] == "bb"
    assert devs["bb"]["signal"] == "weak"
    r.on_mesh(mt.RosterGone("aa"))
    assert [d["id"] for d in r.devices()] == ["me", "bb"]
    assert signal_label(0) == ""


def test_radio_conflict_flag_adds_radio_master_names():
    r, _ = make("standalone")
    r.on_mesh(mt.RosterEntry("m1", mt.KIND_MASTER, "", 50, "1", "RadioM"))
    r.on_mesh(mt.MeshStatus("M", "H", 1, True, 5, 1))
    assert r.conflict() == ["RadioM"]


def test_changed_ignores_ageing_but_sees_real_changes():
    r, now = make()
    assert r.changed() and not r.changed()
    r.on_mesh(mt.RosterEntry("aa", mt.KIND_NODE, "", 60, "1", "L"))
    assert r.changed()
    now[0] += 3
    assert not r.changed()
    r.set_self("Min", "leader", "", "running", "0.0.1")
    assert r.changed()

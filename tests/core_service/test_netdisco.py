import json

from archerytimer.core_service.netdisco import Beacon, LeaderBrowser


def beacon(**kw):
    return json.dumps({"app": "archerytimer", "v": 2, "port": 8765, **kw}).encode()


def make():
    now = [0.0]
    changes = []
    b = LeaderBrowser(on_change=lambda: changes.append(1), now=lambda: now[0], own_id="me")
    return b, now, changes


def test_beacon_payload_carries_v2_fields_and_updates():
    bc = Beacon(8765, "Ett", node_id="id1", role="alone", version="0.0.1")
    body = json.loads(bc.payload())
    assert body["v"] == 2 and body["id"] == "id1" and body["role"] == "alone"
    assert body["ver"] == "0.0.1"
    bc.update(role="leader", state="running", bogus=1)
    body = json.loads(bc.payload())
    assert body["role"] == "leader" and body["state"] == "running" and "bogus" not in body


def test_old_beacon_parses_as_leader():
    b, _, _ = make()
    b.hear(json.dumps({"app": "archerytimer", "port": 8765, "name": "Gammal"}).encode(), "10.0.0.2")
    (inst,) = b.instances()
    assert inst.role == "leader" and inst.addr == "10.0.0.2:8765" and inst.id == "10.0.0.2:8765"
    assert b.leaders() == [{"name": "Gammal", "addr": "10.0.0.2:8765"}]


def test_lists_all_instances_but_leaders_only_in_leaders_and_ignores_self():
    b, now, changes = make()
    b.hear(beacon(name="A", id="a", role="leader", state="running", ver="1"), "10.0.0.1")
    b.hear(beacon(name="B", id="b", role="follower", follows="A", radio="ok"), "10.0.0.2")
    b.hear(beacon(name="Me", id="me", role="leader"), "10.0.0.3")  # own broadcast
    b.hear(beacon(name="C", id="c", role="weird", state="odd"), "10.0.0.4")
    b.hear(b"junk", "10.0.0.5")
    got = {i.name: i for i in b.instances()}
    assert set(got) == {"A", "B", "C"}
    assert got["B"].follows == "A" and got["B"].radio == "ok" and got["A"].state == "running"
    assert got["C"].role == "alone" and got["C"].state == ""
    assert [d["name"] for d in b.leaders()] == ["A"]
    now[0] = 10.0
    assert b.instances() == []
    b.notify()
    assert len(changes) >= 2


def test_conflict_names_both_leaders_and_ours():
    b, _, _ = make()
    b.hear(beacon(name="A", id="a", role="leader"), "10.0.0.1")
    assert b.conflict() == []
    b.hear(beacon(name="B", id="b", role="leader"), "10.0.0.2")
    assert b.conflict() == ["A", "B"]
    b2, _, _ = make()
    b2.hear(beacon(name="A", id="a", role="leader"), "10.0.0.1")
    assert b2.conflict("Me") == ["A", "Me"]

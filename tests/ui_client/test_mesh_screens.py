"""Mesh v2 UI: timer network screen, wireless remotes, status chip (fake roster/remotes messages)."""

from __future__ import annotations

import pygame
from tests.ui_client.test_screens import click, key, rig  # noqa: F401

from archerytimer.ipc.messages import remotes_msg, roster_msg
from archerytimer.ui_client.sections.status_bar import network_chip, status_items


def dev(name, role, **kw):
    base = dict(id=name, name=name, kind="core", role=role, via="lan", follows="", state="idle",
                signal="", fw="1.2", last_seen_s=3.0, caps="", this=False)  # fmt: skip
    base.update(kw)
    return base


def set_roster(link, devices, master="", conflict=()):
    m = roster_msg(devices, master, list(conflict))
    link.roster = {k: v for k, v in m.items() if k not in ("type", "v")}


def set_remotes(link, remotes=(), pairing_open=False, seconds_left=0, pending=()):
    m = remotes_msg(list(remotes), pairing_open, seconds_left, list(pending))
    link.remotes = {k: v for k, v in m.items() if k not in ("type", "v")}


def texts(app):
    return [w.text for w in app.screens[-1].widgets(app.make_context())]


def cmds(link):
    return [(m["name"], m["args"]) for m in link.sent if m["type"] == "cmd"]


def open_screen(app, wid):
    key(app, pygame.K_m)
    click(app, wid)


def test_roster_lists_devices_marks_master_and_this(rig):  # noqa: F811
    app, link, _ = rig
    set_roster(
        link,
        [dev("Klubben", "leader", via="self"),
         dev("Mål", "follower", follows="Klubben", this=True),
         dev("Låda", "node", via="radio", signal="weak")],
        master="Klubben",
    )  # fmt: skip
    open_screen(app, "roster")
    lines = texts(app)
    assert any("[MAIN TIMER]" in x and "Klubben" in x for x in lines)
    assert any("[this device]" in x and "follows Klubben" in x for x in lines)
    assert any("radio light box" in x and "radio" in x and "signal weak" in x for x in lines)
    assert not any("Two main timers" in x for x in lines)


def test_conflict_banner_names_both_masters(rig):  # noqa: F811
    app, link, _ = rig
    set_roster(link, [dev("A", "leader", this=True), dev("B", "leader")], "A", ["A", "B"])
    open_screen(app, "roster")
    assert "Two main timers: A and B. Stop one." in texts(app)


def test_take_over_asks_first_and_cancel_is_default(rig):  # noqa: F811
    app, link, _ = rig
    set_roster(link, [dev("A", "leader"), dev("B", "follower", this=True)], "A")
    open_screen(app, "roster")
    click(app, "take_over")
    assert app.screens[-1].name == "confirm" and not cmds(link)
    key(app, pygame.K_SPACE)  # primary = cancel
    assert app.screens[-1].name == "roster" and not cmds(link)
    click(app, "take_over")
    click(app, "yes")
    assert cmds(link) == [("take_over", {})]


def test_take_over_disabled_when_already_main_timer(rig):  # noqa: F811
    app, link, _ = rig
    set_roster(link, [dev("A", "leader", this=True)], "A")
    open_screen(app, "roster")
    w = {w.id: w for w in app.screens[-1].widgets(app.make_context()) if w.id}
    assert not w["take_over"].enabled


def test_status_chip_from_roster(rig):  # noqa: F811
    app, link, _ = rig
    cases = [
        ([dev("A", "leader", this=True)], [], "Main timer"),
        ([dev("A", "leader"), dev("B", "follower", follows="A", this=True)], [], "Follows A"),
        ([dev("A", "alone", this=True)], [], "Works alone"),
        ([dev("A", "node", this=True)], [], "Radio only"),
        ([dev("A", "leader", this=True)], ["A", "B"], "Two main timers!"),
    ]
    for devices, conflict, expected in cases:
        set_roster(link, devices, "", conflict)
        ctx = app.make_context()
        ctx.roster = link.roster  # app.make_context passes it once integrated (see report)
        chip = network_chip(ctx)
        assert chip is not None and chip[0] == expected
        assert chip in status_items(ctx)
    ctx.roster = None
    assert network_chip(ctx) is None


def test_remotes_pairing_flow_reject_is_default(rig):  # noqa: F811
    app, link, _ = rig
    pend = {
        "id": "AA:BB:CC:00:11:22",
        "name": "Finish line",
        "mac": "AA:BB:CC:00:11:22",
        "caps": "",
    }
    pend["id"] = "r1"
    set_remotes(link, pending=[pend])
    open_screen(app, "remotes")  # opening the screen starts the search by itself
    name, args = cmds(link)[-1]
    assert name == "pair_open" and args["seconds"] > 0 and args["discover"] is True
    assert "Finish line (AA:BB:CC:00:11:22)" in texts(app)
    set_remotes(link, pairing_open=True, seconds_left=42, pending=[pend])
    assert any("Searching" in x for x in texts(app))
    click(app, "open0")  # rights are chosen before accepting
    assert app.screens[-1].name == "pending_remote"
    assert any("AA:BB:CC:00:11:22" in x for x in texts(app))
    click(app, "perm_next")
    click(app, "accept")
    name, args = cmds(link)[-1]
    assert name == "pair_accept" and args["id"] == "r1" and "next" in args["perms"]
    assert app.screens[-1].name == "remotes"
    key(app, pygame.K_SPACE)  # primary rejects
    assert cmds(link)[-1] == ("pair_reject", {"id": "r1"})
    click(app, "accept0")
    name, args = cmds(link)[-1]
    assert name == "pair_accept" and args["id"] == "r1" and "next" not in args["perms"]
    assert "emergency" not in args["perms"] and "reset" not in args["perms"]
    click(app, "pair")
    assert cmds(link)[-1][0] == "pair_close"


def test_leaving_remotes_closes_pairing_window(rig):  # noqa: F811
    app, link, _ = rig
    set_remotes(link, pairing_open=True, seconds_left=10)
    open_screen(app, "remotes")
    click(app, "back")
    assert cmds(link)[-1][0] == "pair_close"


def test_remote_permissions_toggle_and_remove(rig):  # noqa: F811
    app, link, _ = rig
    set_remotes(
        link,
        remotes=[
            {
                "id": "r1",
                "name": "Mål",
                "perms": ["primary", "pause"],
                "last_seen_s": 2.0,
                "via": "radio",
            }
        ],
    )
    open_screen(app, "remotes")
    click(app, "remote0")
    assert app.screens[-1].name == "remote_perms"
    labels = texts(app)
    assert any("always allowed" in x for x in labels)
    assert not any("Reset" in x or "Quit" in x for x in labels if x.startswith(("Reset:", "Quit:")))
    click(app, "perm_next")
    assert cmds(link)[-1] == ("remote_perms", {"id": "r1", "perms": ["primary", "pause", "next"]})
    click(app, "perm_pause")
    assert cmds(link)[-1] == ("remote_perms", {"id": "r1", "perms": ["primary"]})
    click(app, "remove")
    assert app.screens[-1].name == "confirm"
    key(app, pygame.K_SPACE)
    assert cmds(link)[-1][0] == "remote_perms"  # cancelled: nothing removed
    click(app, "remove")
    click(app, "yes")
    assert cmds(link)[-1] == ("remote_remove", {"id": "r1"})
    assert app.screens[-1].name == "remotes"


def test_reset_radio_network_needs_confirmation(rig):  # noqa: F811
    app, link, _ = rig
    set_remotes(link)
    open_screen(app, "remotes")
    click(app, "reset_radio")
    assert app.screens[-1].name == "confirm"
    assert not any(c[0] == "radio_reset_key" for c in cmds(link))
    click(app, "yes")
    assert cmds(link)[-1] == ("radio_reset_key", {})


def test_emergency_closes_mesh_screens(rig):  # noqa: F811
    app, link, _ = rig
    set_remotes(link)
    open_screen(app, "remotes")
    app.close_all_screens()  # what UiApp does when the core reports an emergency
    assert not app.screens

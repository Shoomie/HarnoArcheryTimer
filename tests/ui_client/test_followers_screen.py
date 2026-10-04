"""Follower access UI: Followers screen (leader), greyed buttons and sync chip (follower side)."""

from __future__ import annotations

import pygame
from tests.ui_client.test_mesh_screens import cmds, open_screen, texts
from tests.ui_client.test_screens import click, key, rig  # noqa: F401

from archerytimer.ipc.access import PRESETS
from archerytimer.ipc.messages import follower_state_msg, followers_msg
from archerytimer.ui_client.context import buttons_for
from archerytimer.ui_client.sections.status_bar import status_items


def fol(fid, name, status="approved", perms=(), preset="custom", connected=True):
    return dict(id=fid, name=name, status=status, perms=list(perms), preset=preset,
                connected=connected, last_seen_s=1.0)  # fmt: skip


def set_followers(link, items):
    m = followers_msg(list(items))
    link.followers = {k: v for k, v in m.items() if k not in ("type", "v")}


def set_follower(app, link, status, perms=(), preset="custom"):
    m = follower_state_msg(status, list(perms), preset, "Klubben")
    link.follower = {k: v for k, v in m.items() if k not in ("type", "v")}


def ctx_of(app, link):
    ctx = app.make_context()
    ctx.follower = getattr(link, "follower", None)  # app.make_context passes it once integrated
    return ctx


def test_menu_entry_and_empty_list(rig):  # noqa: F811
    app, link, _ = rig
    open_screen(app, "followers")
    assert app.screens[-1].name == "followers"
    assert any("No other timers" in x for x in texts(app))


def test_pending_first_reject_is_default_approve_uses_operator(rig):  # noqa: F811
    app, link, _ = rig
    set_followers(
        link, [fol("a", "Mål", perms=["primary"]), fol("b", "Café", "pending", connected=True)]
    )
    open_screen(app, "followers")
    lines = texts(app)
    assert "Café: connected, waiting for approval" in lines[1]
    key(app, pygame.K_SPACE)
    assert cmds(link)[-1] == ("follower_remove", {"id": "b"})
    click(app, "approve0")
    name, args = cmds(link)[-1]
    assert name == "follower_approve" and args["id"] == "b"
    assert args["perms"] == list(PRESETS["operator"])


def test_chosen_rights_before_approving(rig):  # noqa: F811
    app, link, _ = rig
    set_followers(link, [fol("b", "Café", "pending")])
    open_screen(app, "followers")
    click(app, "open0")
    assert app.screens[-1].name == "follower"
    click(app, "preset_full")
    assert not cmds(link)  # nothing sent until Approve
    click(app, "perm_reset")
    click(app, "approve")
    name, args = cmds(link)[-1]
    assert name == "follower_approve" and args["id"] == "b"
    assert "reset" not in args["perms"] and "primary" in args["perms"]
    assert app.screens[-1].name == "followers"


def test_permissions_presets_block_remove(rig):  # noqa: F811
    app, link, _ = rig
    set_followers(link, [fol("a", "Mål", perms=["primary", "pause"])])
    open_screen(app, "followers")
    click(app, "open0")
    assert any("always allowed" in x for x in texts(app))
    click(app, "perm_reset")
    assert cmds(link)[-1] == ("follower_perms", {"id": "a", "perms": ["primary", "pause", "reset"]})
    click(app, "perm_pause")
    assert cmds(link)[-1] == ("follower_perms", {"id": "a", "perms": ["primary"]})
    click(app, "preset_operator")
    assert cmds(link)[-1] == ("follower_perms", {"id": "a", "perms": list(PRESETS["operator"])})
    click(app, "preset_view")
    assert cmds(link)[-1] == ("follower_perms", {"id": "a", "perms": []})
    click(app, "block")
    assert cmds(link)[-1] == ("follower_block", {"id": "a"})
    n = len(cmds(link))
    click(app, "remove")
    assert app.screens[-1].name == "confirm"
    key(app, pygame.K_SPACE)  # cancel is the default
    assert len(cmds(link)) == n
    click(app, "remove")
    click(app, "yes")
    assert cmds(link)[-1] == ("follower_remove", {"id": "a"})
    assert app.screens[-1].name == "followers"


def test_blocked_follower_cannot_be_edited(rig):  # noqa: F811
    app, link, _ = rig
    set_followers(link, [fol("a", "Mål", "blocked")])
    open_screen(app, "followers")
    click(app, "open0")
    w = {w.id: w for w in app.screens[-1].widgets(app.make_context()) if w.id}
    assert not w["perm_primary"].enabled and not w["block"].enabled


def test_emergency_closes_followers_screens(rig):  # noqa: F811
    app, link, _ = rig
    set_followers(link, [fol("a", "Mål")])
    open_screen(app, "followers")
    click(app, "open0")
    app.close_all_screens()
    assert not app.screens


def by_id(ctx):
    return {b.id: b for b in buttons_for(ctx)}


def test_pending_follower_is_display_only(rig):  # noqa: F811
    app, link, _ = rig
    set_follower(app, link, "pending")
    b = by_id(ctx_of(app, link))
    assert b["primary"].label == "Waiting for approval from the main timer"
    assert not b["primary"].enabled and b["primary"].action == ""
    assert b["emergency"].enabled and b["menu"].enabled
    assert ("Waiting for approval", False) in status_items(ctx_of(app, link))


def test_missing_permissions_are_greyed(rig):  # noqa: F811
    app, link, _ = rig
    set_follower(app, link, "approved", ["pause"])  # idle: primary is "choose session" (configure)
    b = by_id(ctx_of(app, link))
    assert not b["primary"].enabled
    set_follower(app, link, "approved", ["configure"])
    assert by_id(ctx_of(app, link))["primary"].enabled
    set_follower(app, link, "approved", list(PRESETS["full"]))
    full = buttons_for(ctx_of(app, link))
    link.follower = None
    assert [(x.id, x.enabled) for x in full] == [
        (x.id, x.enabled) for x in buttons_for(ctx_of(app, link))
    ]


def test_blocked_and_denied_chips(rig):  # noqa: F811
    app, link, _ = rig
    for status, chip in (("blocked", "Blocked by the main timer"), ("denied", "Watch only")):
        set_follower(app, link, status)
        ctx = ctx_of(app, link)
        assert (chip, False) in status_items(ctx)
        assert not by_id(ctx)["primary"].enabled and by_id(ctx)["emergency"].enabled


def test_leader_sync_chip_and_hardware_row(rig):  # noqa: F811
    app, link, _ = rig
    ctx = ctx_of(app, link)
    ctx.leader_rtt_ms = 6.0
    assert ("Sync with main timer: ±3 ms", True) in status_items(ctx)
    link.leader_rtt_ms = 8.0
    open_screen(app, "hardware")
    assert "Sync with main timer: ±4 ms" in texts(app)

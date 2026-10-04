"""Network screen: the 'Radio only' choice (follower that takes the timer from the ESP32 radio)."""

from __future__ import annotations

import pygame
from tests.ui_client.test_screens import _node, _widgets, click, key, rig  # noqa: F401


def _open(app):
    key(app, pygame.K_m)
    click(app, "network")


def test_radio_only_sends_follower_and_radio_sentinel(rig):  # noqa: F811
    app, link, _ = rig
    link.node = _node()
    _open(app)
    assert _widgets(app)["leader_radio"].enabled
    click(app, "leader_radio")
    assert link.sent[-1]["values"] == {"node_role": "follower", "node_leader": "radio"}


def test_radio_only_selected_shows_help_and_toggles_off(rig):  # noqa: F811
    app, link, _ = rig
    link.node = _node(role="follower", leader="radio")
    link.espnow = {"mode": "follow", "peers": 3}
    _open(app)
    w = _widgets(app)
    assert w["leader_radio"].selected
    texts = [x.text for x in app.screens[-1].widgets(app.make_context())]
    t = app.t
    assert t("network.hint_radio") in " ".join(texts)
    assert "3" in " ".join(texts)
    click(app, "leader_radio")
    assert link.sent[-1]["values"] == {"node_leader": ""}


def test_radio_only_apply_refused_while_session_runs(rig):  # noqa: F811
    app, link, _ = rig
    link.node = _node(role="follower", leader="radio", restart_needed=True, busy=True)
    _open(app)
    assert not _widgets(app)["apply"].enabled
    link.node = _node(role="follower", leader="radio", restart_needed=True)
    assert _widgets(app)["apply"].enabled


def test_radio_only_locked_by_start_flags(rig):  # noqa: F811
    app, link, _ = rig
    link.node = _node(locked=True, role="follower", leader="radio")
    _open(app)
    assert not _widgets(app)["leader_radio"].enabled

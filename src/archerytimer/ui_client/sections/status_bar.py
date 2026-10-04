"""Plain-language status: is the timer reachable, are the lights connected, clock sync."""

from __future__ import annotations

from collections.abc import Hashable

import pygame

from archerytimer.ui_client import theme
from archerytimer.ui_client.context import CORE_OK, ViewContext, follower_status
from archerytimer.ui_client.sections.base import Section

WARN: theme.Color = (255, 170, 0)


def network_chip(ctx: ViewContext) -> tuple[str, bool] | None:
    """Plain-words role of this device from the roster: (text, ok); None without a roster."""
    roster = ctx.roster
    if not roster:
        return None
    t = ctx.t
    conflict = [str(c) for c in roster.get("conflict", [])]
    if conflict:
        return t("status.net_conflict"), False
    me = next((d for d in roster.get("devices", []) if d.get("this")), None)
    if me is None:
        return None
    role = str(me.get("role", ""))
    if role == "leader":
        return t("status.net_master"), True
    if role in ("follower", "mirror"):
        name = str(me.get("follows") or roster.get("master") or "")
        return (t("status.net_follows", name=name) if name else t("status.net_master")), True
    if role in ("node", "radio"):
        return t("status.net_radio"), True
    if role == "alone":
        return t("status.net_alone"), True
    return None


def status_items(ctx: ViewContext) -> list[tuple[str, bool]]:
    """(text, ok) pairs, left to right."""
    t = ctx.t
    core_ok = ctx.core_state == CORE_OK
    items = [(t("status.timer_ok" if core_ok else "status.timer_down"), core_ok)]
    if core_ok and ctx.snap is not None:
        lights = ctx.snap.link == "up"
        items.append((t("status.lights_up" if lights else "status.lights_down"), lights))
    chip = network_chip(ctx) if core_ok else None
    if chip is not None:
        items.append(chip)
    access = follower_status(ctx)
    if core_ok and access in ("pending", "blocked", "denied"):
        items.append((t("status.access_" + access), False))
    if core_ok and ctx.leader_rtt_ms is not None:
        items.append((t("status.leader_sync", ms=max(1, round(ctx.leader_rtt_ms / 2))), True))
    elif core_ok and ctx.synced and abs(ctx.offset_ns) > 5_000_000:  # only worth showing off-box
        items.append((t("status.sync", ms=max(1, ctx.rtt_ns // 2_000_000)), True))
    return items


class StatusBar(Section):
    name = "status"

    def key(self, ctx: ViewContext) -> Hashable:
        return tuple(status_items(ctx))

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill(theme.PANEL)
        w, h = surf.get_size()
        x = w // 50
        for text, ok in status_items(ctx):
            img = self.fonts.fit("status", text, w // 3, theme.FG if ok else WARN)
            surf.blit(img, (x, (h - img.get_height()) // 2))
            x += img.get_width() + w // 25

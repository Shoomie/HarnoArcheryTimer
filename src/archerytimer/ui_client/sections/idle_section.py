"""Idle screen: a big clock (or a dim one, or black) while nothing is running.

It replaces every other section, so it costs one redraw per minute, and none at all in the
black style. Any input, or any change reported by the core, brings the normal view back.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.core.models import Mode
from archerytimer.ui_client import theme
from archerytimer.ui_client.context import NS_PER_S, ViewContext
from archerytimer.ui_client.sections.base import Section, blit_center


def clock_text(ctx: ViewContext) -> str:
    return ctx.wall_text[:5]  # HH:MM


def session_text(ctx: ViewContext) -> str:
    snap = ctx.snap
    if snap is None or snap.mode is Mode.IDLE:
        return ""
    return ctx.sequence_name or snap.sequence_id


class IdleSection(Section):
    name = "idle"

    def key(self, ctx: ViewContext) -> Hashable:
        if ctx.idle_style == "black":
            return "black"
        return (ctx.idle_style, clock_text(ctx), session_text(ctx))

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        if ctx.idle_style == "black":
            return None
        seconds = int(ctx.wall_text[6:8] or 0)  # wake at the next minute boundary
        return (60 - seconds) * NS_PER_S - ctx.wall_frac_ns

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill((0, 0, 0))
        if ctx.idle_style == "black":
            return
        dim = ctx.idle_style == "dim"
        w, h = surf.get_size()
        imgs = [self.fonts.glyphs[c] for c in clock_text(ctx)]
        total = sum(i.get_width() for i in imgs)
        gh = self.fonts.glyph_height
        line = pygame.Surface((total, gh), pygame.SRCALPHA)
        x = 0
        for img in imgs:
            line.blit(img, (x, 0))
            x += img.get_width()
        if dim:
            line.fill((*theme.IDLE_DIM, 255), special_flags=pygame.BLEND_RGBA_MULT)
        scale = min(1.0, w * 0.8 / total) * 1.6  # bigger than the countdown: nothing else to show
        scale = min(scale, w * 0.9 / total, h * 0.7 / gh)
        line = pygame.transform.smoothscale(line, (int(total * scale), int(gh * scale)))
        blit_center(surf, line, (w // 2, h * 45 // 100))
        name = session_text(ctx)
        if name:
            color = theme.IDLE_DIM if dim else theme.MUTED
            blit_center(
                surf, self.fonts.fit("info", name, w * 9 // 10, color), (w // 2, h * 85 // 100)
            )

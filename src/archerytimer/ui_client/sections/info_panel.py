"""Clock, preset name, end x of y, line group."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.core.models import Mode
from archerytimer.ui_client import theme
from archerytimer.ui_client.context import CORE_OK, NS_PER_S, ViewContext, light_colors, light_view
from archerytimer.ui_client.presets import OPEN_ENDED
from archerytimer.ui_client.renderer.base import Overlay, OverlayImage, OverlayRect
from archerytimer.ui_client.sections.base import Section, blit_center


def info_lines(ctx: ViewContext) -> list[str]:
    t, snap = ctx.t, ctx.snap
    lines = [ctx.wall_text]
    if snap is None or ctx.core_state != CORE_OK or snap.mode is Mode.IDLE:
        lines.append(t("info.no_session"))
        return lines
    lines.append(ctx.sequence_name or snap.sequence_id)
    key = "info.practice" if snap.practice else "info.end"
    if snap.total_ends >= OPEN_ENDED:  # free training: no end count to aim for
        key += "_open"
    lines.append(t(key, n=snap.end_no, total=snap.total_ends))
    lines.append(t("info.line", group=snap.group))
    return lines


class InfoPanel(Section):
    """The static lines are the picture; the clock (it ticks every second) is an overlay."""

    name = "info"

    def key(self, ctx: ViewContext) -> Hashable:
        return tuple(info_lines(ctx)[1:])  # the light-coloured strip is an overlay

    def overlay_key(self, ctx: ViewContext) -> Optional[Hashable]:
        return (ctx.wall_text, len(info_lines(ctx)), light_view(ctx).light)

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        # The clock shows seconds: wake at the next wall-clock second boundary.
        return NS_PER_S - ctx.wall_frac_ns

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill(theme.PANEL)
        w, h = surf.get_size()
        lines = info_lines(ctx)
        for i, text in enumerate(lines):
            if i == 0:
                continue  # the clock: overlay
            img = self.fonts.fit("info", text, w * 9 // 10, theme.FG)
            blit_center(surf, img, (w // 2, h * (2 * i + 1) // (2 * len(lines))))

    def overlay(self, size: tuple[int, int], ctx: ViewContext) -> list[Overlay]:
        w, h = size
        glyphs = self.fonts.glyph_set("info", theme.MUTED)
        imgs = [glyphs[c] for c in ctx.wall_text]
        n = len(info_lines(ctx))
        x = (w - sum(i.get_width() for i in imgs)) // 2
        y = h // (2 * n) - imgs[0].get_height() // 2
        strip = max(4, w // 40)
        items: list[Overlay] = [
            OverlayRect(light_colors(light_view(ctx).light)[0], w - strip, 0, strip, h)
        ]
        for img in imgs:
            items.append(OverlayImage(img, x, y))
            x += img.get_width()
        return items

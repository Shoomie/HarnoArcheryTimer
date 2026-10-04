"""Host section for operator screens: a light/countdown banner on top, the screen below."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.ui_client import theme
from archerytimer.ui_client.context import (
    CORE_OK,
    ViewContext,
    banner_view,
    light_colors,
    next_text_change_ns,
    remaining_ns,
)
from archerytimer.ui_client.fonts import Fonts
from archerytimer.ui_client.renderer.base import Overlay, OverlayImage, OverlayRect
from archerytimer.ui_client.sections.base import Section
from archerytimer.ui_client.widgets import (
    INTERACTIVE,
    Widget,
    draw_widgets,
    hit_widget,
    hover_image,
    to_pixels,
)

BANNER_FRACTION = 0.12


def content_area(size: tuple[int, int]) -> pygame.Rect:
    w, h = size
    top = round(h * BANNER_FRACTION)
    return pygame.Rect(0, top, w, h - top)


class ScreenSection(Section):
    name = "screen"

    def __init__(self, fonts: Fonts) -> None:
        super().__init__(fonts)
        self._hover_cache: dict[tuple[Widget, tuple[int, int]], pygame.Surface] = {}

    def key(self, ctx: ViewContext) -> Hashable:
        # The widgets only. The banner (light colour, label, countdown) and the hovered widget
        # are overlays, so a ticking second or a hover change repaints nothing.
        return tuple(ctx.screen.widgets(ctx)) if ctx.screen is not None else ()

    def overlay_key(self, ctx: ViewContext) -> Optional[Hashable]:
        lv, text = banner_view(ctx)
        hover = ctx.hover if ctx.hover and ctx.hover.startswith("w:") else None
        widgets = tuple(ctx.screen.widgets(ctx)) if ctx.screen is not None else ()
        return (lv, text, hover, widgets)

    def overlay(self, size: tuple[int, int], ctx: ViewContext) -> list[Overlay]:
        w, h = size
        lv, text = banner_view(ctx)
        bg, fg = light_colors(lv.light)
        banner = pygame.Rect(0, 0, w, round(h * BANNER_FRACTION))
        items: list[Overlay] = [OverlayRect(bg, 0, 0, banner.width, banner.height)]
        label = self.fonts.fit("button", lv.label, banner.width * 7 // 10, fg)
        items.append(
            OverlayImage(label, banner.width // 50, banner.centery - label.get_height() // 2)
        )
        if text:
            glyphs = self.fonts.glyph_set("title", fg)
            if all(c in glyphs for c in text):
                imgs = [glyphs[c] for c in text]
            else:
                imgs = [self.fonts.fit("title", text, banner.width // 4, fg)]
            x = banner.width - banner.width // 50 - sum(i.get_width() for i in imgs)
            for img in imgs:
                items.append(OverlayImage(img, x, banner.centery - img.get_height() // 2))
                x += img.get_width()
        if ctx.screen is not None and ctx.hover and ctx.hover.startswith("w:"):
            wid = ctx.hover[2:]
            area = content_area(size)
            for wd in ctx.screen.widgets(ctx):
                if wd.id == wid and wd.kind in INTERACTIVE and wd.enabled:
                    r = to_pixels(wd.rect, area)
                    ck = (wd, r.size)
                    hover_img = self._hover_cache.get(ck)
                    if hover_img is None:
                        if len(self._hover_cache) > 64:
                            self._hover_cache.clear()
                        hover_img = self._hover_cache[ck] = hover_image(wd, r.size, self.fonts)
                    items.append(OverlayImage(hover_img, r.x, r.y))
                    break
        return items

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        snap = ctx.snap
        if snap is None or ctx.core_state != CORE_OK or snap.paused or snap.emergency:
            return None
        rem = remaining_ns(snap, ctx.now_core_ns)
        if rem is None or rem <= 0:
            return None
        return next_text_change_ns(rem, ctx.tenths)

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill(theme.BG)
        w, h = surf.get_size()
        if ctx.screen is not None:
            draw_widgets(surf, ctx.screen.widgets(ctx), content_area((w, h)), self.fonts, None)

    def hit(self, pos: tuple[int, int], size: tuple[int, int], ctx: ViewContext) -> Optional[str]:
        if ctx.screen is None:
            return None
        wid = hit_widget(ctx.screen.widgets(ctx), pos, content_area(size))
        return None if wid is None else "w:" + wid

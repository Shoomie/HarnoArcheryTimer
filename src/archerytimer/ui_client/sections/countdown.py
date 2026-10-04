"""Huge countdown from cached glyphs, plus a progress bar for the phase.

The picture (``draw``) holds only what changes rarely: background, the light-coloured frame and
the bar track. The digits and the bar fill are overlays: the GPU draws pre-rendered glyph
textures every present, so a ticking second costs no CPU painting and no texture upload.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.core.models import Mode
from archerytimer.ui_client import theme
from archerytimer.ui_client.context import (
    CORE_OK,
    NS_PER_S,
    ViewContext,
    countdown_text,
    display_ns,
    light_colors,
    light_view,
    next_text_change_ns,
)
from archerytimer.ui_client.fonts import Fonts
from archerytimer.ui_client.renderer.base import Overlay, OverlayImage, OverlayRect
from archerytimer.ui_client.sections.base import Section


def _rem(ctx: ViewContext) -> Optional[int]:
    if ctx.snap is None or ctx.core_state != CORE_OK:
        return None
    return display_ns(ctx.snap, ctx.now_core_ns)


def _bar_total(ctx: ViewContext) -> int:
    """Phase length in ns if a progress bar is shown, else 0."""
    snap = ctx.snap
    if snap is None or snap.mode is not Mode.RUNNING or _rem(ctx) is None:
        return 0
    return max(0, snap.deadline_ns - snap.phase_start_ns)


def _bar_frac(ctx: ViewContext) -> float:
    """Bar fill, stepped in whole seconds so it moves in step with the digits."""
    rem, total = _rem(ctx), _bar_total(ctx)
    if rem is None or total <= 0:
        return 0.0
    whole = -(-rem // NS_PER_S) * NS_PER_S  # ceil, like the whole-second display
    return max(0.0, min(1.0, whole / total))


def _bar_rect(size: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = size
    bar_h = max(4, h // 20)
    return w // 20, h - 2 * bar_h, w * 9 // 10, bar_h


class Countdown(Section):
    name = "countdown"

    def __init__(self, fonts: Fonts) -> None:
        super().__init__(fonts)
        self._glyph_cache: dict[tuple[str, int], pygame.Surface] = {}

    def key(self, ctx: ViewContext) -> Hashable:
        return _bar_total(ctx) > 0  # the light-coloured frame is an overlay

    def overlay_key(self, ctx: ViewContext) -> Optional[Hashable]:
        rem = _rem(ctx)
        total = _bar_total(ctx)
        frac = _bar_frac(ctx)
        snap = ctx.snap
        light = snap.light if snap is not None else None
        return (
            countdown_text(rem, ctx.tenths),
            round(frac * 10000),
            light,
            total > 0,
            light_view(ctx).light,
        )

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        rem = _rem(ctx)
        if rem is None or ctx.snap is None or ctx.snap.paused or ctx.snap.emergency:
            return None
        if ctx.snap.mode is not Mode.RUNNING:
            return None
        if rem <= 0:
            return None
        return next_text_change_ns(rem, ctx.tenths)

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill(theme.BG)
        w, h = surf.get_size()
        if _bar_total(ctx) > 0:
            pygame.draw.rect(surf, theme.PANEL, _bar_rect((w, h)))

    def overlay(self, size: tuple[int, int], ctx: ViewContext) -> list[Overlay]:
        w, h = size
        rem = _rem(ctx)
        text = countdown_text(rem, ctx.tenths)
        glyphs = self.fonts.glyphs
        total = sum(glyphs[c].get_width() for c in text)
        # narrow sections: shrink the whole line (glyphs are scaled once and cached per scale)
        scale = min(1.0, w * 0.96 / total)
        imgs = [self._glyph(c, scale) for c in text]
        x = (w - sum(i.get_width() for i in imgs)) // 2
        y = h * 45 // 100 - imgs[0].get_height() // 2
        # a frame in the light colour down the screen edge: visible from the line at a glance
        frame = light_colors(light_view(ctx).light)[0]
        items: list[Overlay] = [OverlayRect(frame, 0, 0, max(4, w // 60), h)]
        for img in imgs:
            items.append(OverlayImage(img, x, y))
            x += img.get_width()
        bar_total = _bar_total(ctx)
        snap = ctx.snap
        if bar_total > 0 and rem is not None and snap is not None:
            bx, by, bw, bh = _bar_rect(size)
            fill = int(bw * _bar_frac(ctx))
            if fill > 0:
                items.append(OverlayRect(theme.LIGHT_COLORS[snap.light], bx, by, fill, bh))
        return items

    def _glyph(self, ch: str, scale: float) -> pygame.Surface:
        key = (ch, round(scale * 1000))
        img = self._glyph_cache.get(key)
        if img is None:
            img = self.fonts.glyphs[ch]
            if scale < 1.0:
                img = pygame.transform.smoothscale(
                    img,
                    (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))),
                )
            self._glyph_cache[key] = img
        return img

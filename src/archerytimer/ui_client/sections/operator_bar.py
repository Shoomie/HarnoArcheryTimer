"""Operator button bar: mouse (and later touch) targets. Hideable for a clean audience view.

Hover is an overlay: the bar picture is painted in the normal state and the hovered button is a
cached picture the GPU draws on top, so moving the mouse over buttons repaints nothing.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.ui_client import theme
from archerytimer.ui_client.context import ButtonView, ViewContext, buttons_for
from archerytimer.ui_client.fonts import Fonts
from archerytimer.ui_client.renderer.base import Overlay, OverlayImage
from archerytimer.ui_client.sections.base import Section, blit_center

EMERGENCY_FRACTION = 0.2


def button_rects(buttons: list[ButtonView], size: tuple[int, int]) -> list[pygame.Rect]:
    """Buttons share the bar by weight. The emergency button is always first (leftmost)."""
    w, h = size
    gap = max(2, w // 200)
    usable = w - gap * (len(buttons) + 1)
    fixed = usable * EMERGENCY_FRACTION  # the emergency button never changes size or place
    others = sum(b.weight for b in buttons if b.kind != "emergency")
    rects, x = [], float(gap)
    for b in buttons:
        bw = fixed if b.kind == "emergency" else (usable - fixed) * b.weight / others
        rects.append(pygame.Rect(round(x), h // 10, round(bw), h * 8 // 10))
        x += bw + gap
    return rects


def _colors(b: ButtonView, hover: bool) -> tuple[theme.Color, theme.Color]:
    if not b.enabled:
        return theme.BUTTON_DISABLED, theme.MUTED
    if b.kind == "emergency":
        return (theme.EMERGENCY_HOVER if hover else theme.EMERGENCY), theme.FG
    if b.kind == "undo":
        return (theme.UNDO_HOVER if hover else theme.UNDO), (0, 0, 0)
    if b.kind == "primary":
        return (theme.PRIMARY_HOVER if hover else theme.PRIMARY), theme.FG
    return (theme.BUTTON_HOVER if hover else theme.BUTTON), theme.FG


def _paint_button(
    surf: pygame.Surface, fonts: Fonts, b: ButtonView, rect: pygame.Rect, hover: bool
) -> None:
    bg, fg = _colors(b, hover)
    pygame.draw.rect(surf, bg, rect, border_radius=rect.height // 6)
    img = fonts.fit("button", b.label, rect.width * 9 // 10, fg)
    if b.sub:
        small = fonts.fit("status", b.sub, rect.width * 9 // 10, fg)
        gap = rect.height // 14
        top = rect.centery - (img.get_height() + gap + small.get_height()) // 2
        surf.blit(img, img.get_rect(midtop=(rect.centerx, top)))
        surf.blit(small, small.get_rect(midtop=(rect.centerx, top + img.get_height() + gap)))
    else:
        blit_center(surf, img, rect.center)


def _button_key(b: ButtonView) -> tuple[object, ...]:
    return (b.id, b.label, b.sub, b.enabled, b.kind)


class OperatorBar(Section):
    name = "operator"

    def __init__(self, fonts: Fonts) -> None:
        super().__init__(fonts)
        self._hover_cache: dict[tuple[object, ...], pygame.Surface] = {}

    def key(self, ctx: ViewContext) -> Hashable:
        return tuple(_button_key(b) for b in buttons_for(ctx))

    def overlay_key(self, ctx: ViewContext) -> Optional[Hashable]:
        hover = None if ctx.hover is None or ctx.hover.startswith("w:") else ctx.hover
        return (hover, tuple(_button_key(b) for b in buttons_for(ctx)))

    def overlay(self, size: tuple[int, int], ctx: ViewContext) -> list[Overlay]:
        if ctx.hover is None or ctx.hover.startswith("w:"):
            return []
        buttons = buttons_for(ctx)
        for b, rect in zip(buttons, button_rects(buttons, size)):
            if b.id == ctx.hover and b.enabled:
                ck = (_button_key(b), rect.size)
                img = self._hover_cache.get(ck)
                if img is None:
                    if len(self._hover_cache) > 32:
                        self._hover_cache.clear()
                    img = pygame.Surface(rect.size)
                    img.fill(theme.BG)
                    _paint_button(img, self.fonts, b, pygame.Rect((0, 0), rect.size), True)
                    self._hover_cache[ck] = img
                return [OverlayImage(img, rect.x, rect.y)]
        return []

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        return ctx.undo_left_ns if ctx.undo and ctx.undo_left_ns > 0 else None

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill(theme.BG)
        buttons = buttons_for(ctx)
        for b, rect in zip(buttons, button_rects(buttons, surf.get_size())):
            _paint_button(surf, self.fonts, b, rect, False)

    def hit(self, pos: tuple[int, int], size: tuple[int, int], ctx: ViewContext) -> Optional[str]:
        """The button id under ``pos`` (enabled or not), so hover and clicks agree."""
        buttons = buttons_for(ctx)
        for b, rect in zip(buttons, button_rects(buttons, size)):
            if rect.collidepoint(pos):
                return b.id
        return None

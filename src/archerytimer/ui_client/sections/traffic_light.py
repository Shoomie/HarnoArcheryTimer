"""The traffic light: a big colour field, plain words, and a shape (not colour alone).

Everything visible here is an overlay: the colour field is a rectangle, the icon and the words are
cached pictures. A light change therefore repaints and uploads nothing; the first time a state
shows, its icon and text are rendered once and kept.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.ui_client import theme
from archerytimer.ui_client.context import ViewContext, light_colors, light_view
from archerytimer.ui_client.fonts import Fonts
from archerytimer.ui_client.renderer.base import Overlay, OverlayImage, OverlayRect
from archerytimer.ui_client.sections.base import Section


class TrafficLight(Section):
    name = "light"

    def __init__(self, fonts: Fonts) -> None:
        super().__init__(fonts)
        self._cache: dict[tuple[object, ...], list[Overlay]] = {}

    def key(self, ctx: ViewContext) -> Hashable:
        return "static"  # the picture under the overlays never changes

    def overlay_key(self, ctx: ViewContext) -> Optional[Hashable]:
        v = light_view(ctx)
        return (v.label, v.light, v.shape)

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        return None

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        surf.fill(theme.BG)

    def overlay(self, size: tuple[int, int], ctx: ViewContext) -> list[Overlay]:
        v = light_view(ctx)
        ck = (v.label, v.light, v.shape, size)
        items = self._cache.get(ck)
        if items is None:
            if len(self._cache) > 40:
                self._cache.clear()
            items = self._cache[ck] = self._build(size, v.label, v.light, v.shape)
        return items

    def _build(self, size: tuple[int, int], label: str, light: object, shape: str) -> list[Overlay]:
        w, h = size
        bg, fg = light_colors(light)  # type: ignore[arg-type]
        items: list[Overlay] = [OverlayRect(bg, 0, 0, w, h)]
        if shape != "none":
            icon = _icon(shape, fg, bg, h)
            half = icon.get_width() // 2
            for cx in (h // 2 + h // 12, w - h // 2 - h // 12):
                items.append(OverlayImage(icon, cx - half, h // 2 - half))
        margin = h * 85 // 100 if shape != "none" else h // 4
        avail = w - 2 * margin
        head, sep, tail = label.partition(" – ")
        full = self.fonts["light"].size(label)[0]
        if sep and full > avail:  # too wide for one line: "SHOOT" over "Line AB"
            big = self.fonts.fit("light", head, avail, fg)
            small = self.fonts.fit("info", tail, avail, fg)
            gap = h // 20
            top = (h - big.get_height() - gap - small.get_height()) // 2
            items.append(OverlayImage(big, w // 2 - big.get_width() // 2, top))
            items.append(
                OverlayImage(small, w // 2 - small.get_width() // 2, top + big.get_height() + gap)
            )
            return items
        img = self.fonts.fit("light", label, avail, fg)
        items.append(
            OverlayImage(img, w // 2 - img.get_width() // 2, h // 2 - img.get_height() // 2)
        )
        return items


def _icon(shape: str, color: theme.Color, bg: theme.Color, h: int) -> pygame.Surface:
    """Big icon, readable without colour: tick = go, ! = hurry, X = stop. On the field colour."""
    s = int(h * 0.62)
    line = max(4, s // 9)
    r = s // 2
    side = s + 2
    img = pygame.Surface((side, side))
    img.fill(bg)
    cx = cy = side // 2
    if shape == "circle":
        pygame.draw.circle(img, color, (cx, cy), r)
        pts = [(cx - r * 45 // 100, cy), (cx - r * 10 // 100, cy + r * 35 // 100),
               (cx + r * 50 // 100, cy - r * 35 // 100)]  # fmt: skip
        pygame.draw.lines(img, bg, False, pts, line)
    elif shape == "square":
        pygame.draw.rect(img, color, (cx - r, cy - r, s, s), border_radius=s // 10)
        d = r * 55 // 100
        pygame.draw.line(img, bg, (cx - d, cy - d), (cx + d, cy + d), line)
        pygame.draw.line(img, bg, (cx - d, cy + d), (cx + d, cy - d), line)
    elif shape == "triangle":
        pygame.draw.polygon(img, color, [(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)])
        pygame.draw.line(img, bg, (cx, cy - r // 4), (cx, cy + r // 3), line)
        pygame.draw.circle(img, bg, (cx, cy + r * 62 // 100), max(2, line // 2 + 1))
    return img

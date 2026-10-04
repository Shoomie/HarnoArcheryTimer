"""Declarative widgets for the operator screens (setup, menu, settings...).

A screen returns a list of ``Widget`` values (immutable, so they double as the section's
dirty key); ``draw_widgets`` paints them and ``hit_widget`` resolves a click. Rects are
fractions of the screen's content area, so nothing is sized in pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pygame

from archerytimer.ui_client import theme
from archerytimer.ui_client.fonts import Fonts

Rect = tuple[float, float, float, float]
WARN: theme.Color = (255, 170, 0)
INTERACTIVE = frozenset({"button", "primary", "danger", "card"})


@dataclass(frozen=True)
class Widget:
    id: str
    kind: str  # title | text | value | row | warn | button | primary | danger | card
    rect: Rect
    text: str = ""
    sub: str = ""
    enabled: bool = True
    selected: bool = False


def to_pixels(rect: Rect, area: pygame.Rect) -> pygame.Rect:
    x, y, w, h = rect
    return pygame.Rect(
        area.x + round(x * area.w),
        area.y + round(y * area.h),
        max(1, round(w * area.w)),
        max(1, round(h * area.h)),
    )


def hit_widget(widgets: list[Widget], pos: tuple[int, int], area: pygame.Rect) -> Optional[str]:
    for w in widgets:
        if w.kind in INTERACTIVE and w.enabled and to_pixels(w.rect, area).collidepoint(pos):
            return w.id
    return None


def _button_colors(w: Widget, hover: bool) -> tuple[theme.Color, theme.Color]:
    if not w.enabled:
        return theme.BUTTON_DISABLED, theme.MUTED
    if w.kind == "danger":
        return (theme.EMERGENCY_HOVER if hover else theme.EMERGENCY), theme.FG
    if w.kind == "primary" or w.selected:
        return (theme.PRIMARY_HOVER if hover else theme.PRIMARY), theme.FG
    return (theme.BUTTON_HOVER if hover else theme.BUTTON), theme.FG


def draw_widgets(
    surf: pygame.Surface,
    widgets: list[Widget],
    area: pygame.Rect,
    fonts: Fonts,
    hover: Optional[str],
) -> None:
    for w in widgets:
        draw_widget(surf, w, to_pixels(w.rect, area), fonts, hover == w.id)


def draw_widget(surf: pygame.Surface, w: Widget, r: pygame.Rect, fonts: Fonts, hover: bool) -> None:
    if w.kind in ("title", "text", "value", "row", "warn"):
        _draw_text(surf, w, r, fonts)
        return
    bg, fg = _button_colors(w, hover)
    radius = r.height // 6
    pygame.draw.rect(surf, bg, r, border_radius=radius)
    if w.selected and w.enabled and w.kind != "primary":
        width = max(2, r.height // 25)
        pygame.draw.rect(surf, theme.FG, r, width=width, border_radius=radius)
    if w.sub:
        main = fonts.fit("button", w.text, r.width * 9 // 10, fg)
        sub = fonts.fit("status", w.sub, r.width * 9 // 10, fg if w.enabled else theme.MUTED)
        gap = r.height // 12
        top = r.centery - (main.get_height() + gap + sub.get_height()) // 2
        surf.blit(main, main.get_rect(midtop=(r.centerx, top)))
        surf.blit(sub, sub.get_rect(midtop=(r.centerx, top + main.get_height() + gap)))
    else:
        img = fonts.fit("button", w.text, r.width * 9 // 10, fg)
        surf.blit(img, img.get_rect(center=r.center))


def hover_image(w: Widget, size: tuple[int, int], fonts: Fonts) -> pygame.Surface:
    """The widget in its hover state, alone, on the screen background (corners match it)."""
    img = pygame.Surface(size)
    img.fill(theme.BG)
    draw_widget(img, w, pygame.Rect(0, 0, *size), fonts, True)
    return img


def _draw_text(surf: pygame.Surface, w: Widget, r: pygame.Rect, fonts: Fonts) -> None:
    key = "title" if w.kind == "title" else "body"
    color = {"text": theme.MUTED, "warn": WARN}.get(w.kind, theme.FG)
    lines = w.text.split("\n")
    line_h = r.height // len(lines)
    for i, line in enumerate(lines):
        img = fonts.fit(key, line, r.width, color)
        y = r.y + i * line_h + (line_h - img.get_height()) // 2
        if w.kind == "value":
            surf.blit(img, img.get_rect(midtop=(r.centerx, y)))
        else:
            surf.blit(img, (r.x, y))

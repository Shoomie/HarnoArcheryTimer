"""Section framework: each section knows when its picture would change.

``key(ctx)`` is everything the section's pixels depend on; the app redraws a section only
when its key differs from the last drawn one. ``next_change_ns(ctx)`` says how long until
the key would change *by itself* (a second ticking over), so the frame loop can sleep
exactly that long instead of polling.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Optional

import pygame

from archerytimer.ui_client.context import ViewContext
from archerytimer.ui_client.fonts import Fonts
from archerytimer.ui_client.renderer.base import Overlay


class Section:
    name = ""

    def __init__(self, fonts: Fonts) -> None:
        self.fonts = fonts

    def key(self, ctx: ViewContext) -> Hashable:
        raise NotImplementedError

    def next_change_ns(self, ctx: ViewContext) -> Optional[int]:
        """Nanoseconds from now until ``key`` changes on its own; None if it never does."""
        return None

    def draw(self, surf: pygame.Surface, ctx: ViewContext) -> None:
        raise NotImplementedError

    def overlay_key(self, ctx: ViewContext) -> Optional[Hashable]:
        """Everything the section's overlay depends on; None = this section has no overlay.
        Parts that tick every second (digits, progress) go here, not into ``key``: the section
        picture is then repainted and uploaded only when something else changes."""
        return None

    def overlay(self, size: tuple[int, int], ctx: ViewContext) -> list[Overlay]:
        return []

    def hit(self, pos: tuple[int, int], size: tuple[int, int], ctx: ViewContext) -> Optional[str]:
        """The action under ``pos`` (section-local pixels), if this section has controls."""
        return None


def blit_center(surf: pygame.Surface, img: pygame.Surface, center: tuple[int, int]) -> None:
    surf.blit(img, img.get_rect(center=center))

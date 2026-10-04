"""Software backend: CPU blits of the cached section surfaces, then a display flip.

Used where the SDL renderer API is unavailable or fails. Renders at the output resolution
(scaling a full frame on the CPU would cost more than it saves).
"""

from __future__ import annotations

from typing import Optional

import pygame

from archerytimer.ui_client.layout import PixelRect
from archerytimer.ui_client.renderer.base import DisplayConfig, Overlay, OverlayImage


class SoftwareRenderer:
    name = "software"

    def __init__(self, cfg: DisplayConfig) -> None:
        pygame.display.init()
        flags = pygame.FULLSCREEN if cfg.fullscreen else pygame.RESIZABLE
        size = (0, 0) if cfg.fullscreen else cfg.size
        try:
            self._screen = pygame.display.set_mode(
                size, flags, display=cfg.display, vsync=1 if cfg.vsync else 0
            )
        except pygame.error:
            self._screen = pygame.display.set_mode(size, flags)
        pygame.display.set_caption(cfg.title)
        if cfg.hide_cursor:
            pygame.mouse.set_visible(False)
        self.logical_size = self._screen.get_size()
        self._sections: dict[str, tuple[pygame.Surface, PixelRect]] = {}
        self._overlays: dict[str, tuple[list[Overlay], tuple[int, int]]] = {}

    def set_section(self, name: str, surface: pygame.Surface, rect: PixelRect) -> None:
        self._sections[name] = (surface, rect)

    def set_overlay(self, name: str, items: list[Overlay], origin: tuple[int, int]) -> None:
        self._overlays[name] = (items, origin)

    def clear_sections(self) -> None:
        self._sections.clear()
        self._overlays.clear()

    def present(self) -> None:
        self._screen.fill((0, 0, 0))
        for surface, rect in self._sections.values():
            self._screen.blit(surface, rect[:2])
        for items, (ox, oy) in self._overlays.values():
            for item in items:
                if isinstance(item, OverlayImage):
                    self._screen.blit(item.surface, (item.x + ox, item.y + oy))
                else:
                    self._screen.fill(item.color, (item.x + ox, item.y + oy, item.w, item.h))
        pygame.display.flip()

    def refresh_size(self) -> bool:
        surface = pygame.display.get_surface()
        assert surface is not None
        self._screen = surface
        size = surface.get_size()
        changed = size != self.logical_size
        self.logical_size = size
        return changed

    def to_logical(self, pos: tuple[int, int]) -> Optional[tuple[int, int]]:
        w, h = self.logical_size
        return pos if 0 <= pos[0] < w and 0 <= pos[1] < h else None

    def close(self) -> None:
        pygame.display.quit()

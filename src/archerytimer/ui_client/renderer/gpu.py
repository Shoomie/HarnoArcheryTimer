"""GPU backend: SDL2 renderer API. One streaming texture per section; the GPU composes and
scales them to the output. The logical canvas is capped at 1080p height, so a 4K display
costs the CPU nothing extra."""

from __future__ import annotations

import contextlib
from typing import Any, Optional

import pygame

from archerytimer.ui_client.layout import PixelRect, logical_size_for
from archerytimer.ui_client.renderer.base import (
    DisplayConfig,
    Overlay,
    OverlayImage,
)

_POS_CENTERED_DISPLAY = 0x2FFF0000  # SDL_WINDOWPOS_CENTERED_DISPLAY(n) = this | n


class GpuRenderer:
    name = "gpu"

    def __init__(self, cfg: DisplayConfig) -> None:
        from pygame._sdl2 import video

        self._video = video
        pygame.display.init()
        sizes = pygame.display.get_desktop_sizes()
        display = cfg.display if 0 <= cfg.display < len(sizes) else 0
        kwargs: dict[str, Any] = {}
        if display:
            pos = _POS_CENTERED_DISPLAY | display
            kwargs["position"] = (pos, pos)
        if cfg.fullscreen:
            self._window = video.Window(
                cfg.title, size=sizes[display], fullscreen_desktop=True, **kwargs
            )
        else:
            self._window = video.Window(cfg.title, size=cfg.size, resizable=True, **kwargs)
        self._renderer = video.Renderer(self._window, vsync=cfg.vsync)
        if cfg.hide_cursor:
            pygame.mouse.set_visible(False)
        self._output = tuple(self._window.size)
        self.logical_size = logical_size_for(self._output)  # type: ignore[arg-type]
        self._renderer.logical_size = self.logical_size
        self._textures: dict[str, tuple[Any, PixelRect]] = {}
        self._overlays: dict[str, tuple[list[Overlay], tuple[int, int]]] = {}
        # glyph surface id -> (surface kept alive so the id stays valid, texture)
        self._glyph_tex: dict[int, tuple[pygame.Surface, Any]] = {}

    def set_section(self, name: str, surface: pygame.Surface, rect: PixelRect) -> None:
        entry = self._textures.get(name)
        if (
            entry is None
            or entry[0].width != surface.get_width()
            or entry[0].height != surface.get_height()
        ):
            tex = self._video.Texture(self._renderer, surface.get_size(), streaming=True)
        else:
            tex = entry[0]
        tex.update(surface)
        self._textures[name] = (tex, rect)

    def set_overlay(self, name: str, items: list[Overlay], origin: tuple[int, int]) -> None:
        self._overlays[name] = (items, origin)

    def _texture_for(self, surface: pygame.Surface) -> Any:
        entry = self._glyph_tex.get(id(surface))
        if entry is None:
            tex = self._video.Texture.from_surface(self._renderer, surface)
            with contextlib.suppress(Exception):
                tex.blend_mode = 1  # SDL_BLENDMODE_BLEND: glyphs carry their own alpha
            entry = (surface, tex)
            self._glyph_tex[id(surface)] = entry
        return entry[1]

    def clear_sections(self) -> None:
        self._textures.clear()
        self._overlays.clear()
        self._glyph_tex.clear()

    def present(self) -> None:
        self._renderer.draw_color = (0, 0, 0, 255)
        self._renderer.clear()
        for tex, rect in self._textures.values():
            tex.draw(dstrect=rect)
        for items, (ox, oy) in self._overlays.values():
            for item in items:
                if isinstance(item, OverlayImage):
                    w, h = item.surface.get_size()
                    self._texture_for(item.surface).draw(dstrect=(item.x + ox, item.y + oy, w, h))
                else:
                    self._renderer.draw_color = (*item.color, 255)
                    self._renderer.fill_rect((item.x + ox, item.y + oy, item.w, item.h))
        self._renderer.present()

    def refresh_size(self) -> bool:
        output = tuple(self._window.size)
        if output == self._output:
            return False
        self._output = output
        new = logical_size_for(output)  # type: ignore[arg-type]
        changed = new != self.logical_size
        self.logical_size = new
        self._renderer.logical_size = new
        return changed

    def to_logical(self, pos: tuple[int, int]) -> Optional[tuple[int, int]]:
        ow, oh = self._output
        lw, lh = self.logical_size
        if ow <= 0 or oh <= 0:
            return None
        scale = min(ow / lw, oh / lh)  # same rule as SDL's logical-size letterboxing
        x = (pos[0] - (ow - lw * scale) / 2) / scale
        y = (pos[1] - (oh - lh * scale) / 2) / scale
        return (int(x), int(y)) if 0 <= x < lw and 0 <= y < lh else None

    def close(self) -> None:
        self._textures.clear()
        self._window.destroy()
        pygame.display.quit()

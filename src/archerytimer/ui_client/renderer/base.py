"""Renderer interface. Sections are drawn on the CPU into small surfaces; the renderer
keeps one cached texture per section and recomposes them on ``present``.

Recomposing everything (instead of patching the screen) is deliberate: with page flipping
(KMSDRM) the back buffer's contents are undefined after a flip, so partial repaints would
flicker. Cost still tracks what changed, because only dirty sections are redrawn on the CPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Union

import pygame

from archerytimer.ui_client.layout import PixelRect


@dataclass(frozen=True)
class OverlayImage:
    """A cached glyph/picture drawn over a section; ``x``/``y`` are relative to the section."""

    surface: pygame.Surface
    x: int
    y: int


@dataclass(frozen=True)
class OverlayRect:
    color: tuple[int, int, int]
    x: int
    y: int
    w: int
    h: int


Overlay = Union[OverlayImage, OverlayRect]


@dataclass(frozen=True)
class DisplayConfig:
    kind: str = "auto"  # "auto" | "gpu" | "software"
    fullscreen: bool = False
    display: int = 0  # monitor index (multi-monitor PCs; the Pi has one)
    size: tuple[int, int] = (1280, 720)  # windowed size
    vsync: bool = False
    title: str = "Archery Timer"
    hide_cursor: bool = False


class Renderer(Protocol):
    name: str
    logical_size: tuple[int, int]  # sections are laid out and drawn at this size

    def set_section(self, name: str, surface: pygame.Surface, rect: PixelRect) -> None: ...

    def set_overlay(self, name: str, items: list[Overlay], origin: tuple[int, int]) -> None:
        """Things that change every second (digits, progress): drawn each present over the
        section pictures. On the GPU path they cost a few quads, not a CPU repaint + upload."""
        ...

    def clear_sections(self) -> None: ...

    def present(self) -> None: ...

    def refresh_size(self) -> bool:
        """Re-read the output size. True if ``logical_size`` changed (sections must be redone)."""
        ...

    def to_logical(self, pos: tuple[int, int]) -> Optional[tuple[int, int]]:
        """Window pixel (mouse) to logical canvas pixel; None if outside the canvas."""
        ...

    def close(self) -> None: ...

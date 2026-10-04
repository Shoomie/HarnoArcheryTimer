"""Font cache scaled from output height, plus pre-rendered countdown glyphs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pygame

from archerytimer.ui_client import theme

# Font height as a fraction of the output height.
SIZES = {
    "title": 0.07,
    "body": 0.045,
    "light": 0.10,
    "countdown": 0.38,
    "info": 0.055,
    "button": 0.042,
    "status": 0.032,
}
GLYPHS = "0123456789:.-"
_TEXT_CACHE_MAX = 300
FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"


def find_font(directory: Path = FONT_DIR) -> Optional[Path]:
    """The bundled UI font: the first ``*.ttf`` / ``*.otf`` in assets/fonts (open-licensed
    fonts only, see assets/fonts/README.md). None falls back to pygame's built-in font."""
    for pattern in ("*.ttf", "*.otf"):
        for path in sorted(directory.glob(pattern)) if directory.is_dir() else []:
            return path
    return None


FONT_PATH = find_font()
# Inter sets larger than pygame's built-in font at the same pixel size.
FONT_SCALE = 0.84 if FONT_PATH is not None else 1.0


_FONT_CACHE: dict[int, pygame.font.Font] = {}


def make_font(size: int) -> pygame.font.Font:
    font = _FONT_CACHE.get(size)
    if font is None:
        font = _load_font(size)
        _FONT_CACHE[size] = font
    return font


def _load_font(size: int) -> pygame.font.Font:
    if FONT_PATH is not None:
        try:
            return pygame.font.Font(str(FONT_PATH), size)
        except (OSError, pygame.error):
            pass
    return pygame.font.Font(None, size)


class Fonts:
    def __init__(self, output_height: int) -> None:
        pygame.font.init()
        self._text_cache: dict[tuple[str, str, int, theme.Color], pygame.Surface] = {}
        self._glyph_sets: dict[tuple[str, theme.Color], dict[str, pygame.Surface]] = {}
        self.height = output_height
        self._fonts = {
            key: make_font(max(8, int(output_height * frac * FONT_SCALE)))
            for key, frac in SIZES.items()
        }
        font = self._fonts["countdown"]
        self.glyphs = {ch: font.render(ch, True, theme.FG) for ch in GLYPHS}
        self.glyph_height = font.get_height()

    def glyph_set(self, key: str, color: theme.Color) -> dict[str, pygame.Surface]:
        """Pre-rendered digits and separators of font ``key`` (cached): clock-style text
        built from these needs no text rendering at run time."""
        ck = (key, color)
        gs = self._glyph_sets.get(ck)
        if gs is None:
            font = self._fonts[key]
            gs = {ch: font.render(ch, True, color) for ch in GLYPHS}
            self._glyph_sets[ck] = gs
        return gs

    def __getitem__(self, key: str) -> pygame.font.Font:
        return self._fonts[key]

    def fit(
        self, key: str, text: str, max_width: int, color: theme.Color = theme.FG
    ) -> pygame.Surface:
        """Render ``text``, shrinking the font if it would not fit in ``max_width``."""
        ck = (key, text, max_width, color)
        img = self._text_cache.get(ck)
        if img is not None:
            return img
        font = self._fonts[key]
        img = font.render(text, True, color)
        if img.get_width() > max_width:
            size = max(8, int(font.get_height() * max_width / img.get_width() * 0.95))
            img = make_font(size).render(text, True, color)
        if len(self._text_cache) >= _TEXT_CACHE_MAX:
            self._text_cache.clear()
        self._text_cache[ck] = img
        return img

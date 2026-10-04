"""Time the pieces of a section repaint (fill, rect, text render, blit, texture upload).

Run on the Pi to see where repaint time goes:
  SDL_VIDEODRIVER=dummy python scripts/profile_paint.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from archerytimer.ui_client import theme
from archerytimer.ui_client.fonts import Fonts, make_font


def timed(label: str, fn, n: int = 20) -> None:  # type: ignore[no-untyped-def]
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    print(f"  {label:42s} {(time.perf_counter() - t0) / n * 1000:7.2f} ms")


def main() -> None:
    pygame.display.init()
    pygame.display.set_mode((64, 64))
    fonts = Fonts(1080)
    surf = pygame.Surface((730, 540))
    print("surface", surf.get_bitsize(), "bit, section 730x540")
    timed("fill 730x540", lambda: surf.fill(theme.PANEL))
    timed("draw.rect", lambda: pygame.draw.rect(surf, (0, 170, 60), (700, 0, 30, 540)))
    font = make_font(50)
    timed("font.render 8 chars (fresh, antialias)", lambda: font.render("07:25:03", True, theme.FG))
    timed("font.render 8 chars (no antialias)", lambda: font.render("07:25:03", False, theme.FG))
    timed(
        "font.render long line 30 chars",
        lambda: font.render("Utomhus kvalificering 6 pilar", True, theme.FG),
    )
    img = font.render("07:25:03", True, theme.FG)
    timed("blit rendered text", lambda: surf.blit(img, (100, 100)))
    for key in ("info", "button", "status"):
        timed(
            f"fonts.fit({key}) uncached",
            lambda k=key: fonts[k].render("Ände 3 av 10", True, theme.FG),
        )
    print("font px for info:", fonts["info"].get_height())
    try:
        from pygame._sdl2 import video

        win = video.Window("p", size=(64, 64))
        ren = video.Renderer(win)
        tex = video.Texture(ren, surf.get_size(), streaming=True)
        timed("texture.update 730x540", lambda: tex.update(surf))
        full = pygame.Surface((1920, 1080))
        big = video.Texture(ren, full.get_size(), streaming=True)
        timed("texture.update 1920x1080", lambda: big.update(full), n=5)
    except Exception as exc:
        print("texture test skipped:", exc)


if __name__ == "__main__":
    main()

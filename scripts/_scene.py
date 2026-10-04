"""A representative timer screen and two render backends, for the M0 benchmarks.

This is spike code: it approximates the planned main screen (big traffic light,
countdown, info panel, operator bar, status bar) closely enough to measure
rendering costs. The real UI lives in ``archerytimer.ui_client`` from M5 on.

Render modes:
  A  full redraw every frame: every section repainted on the CPU with uncached
     text, the whole frame pushed to the screen.
  B  sectioned + cached: only the countdown section (tenths + progress bar)
     changes each frame, drawn from cached glyphs; other sections are cached.
  C  sectioned idle: countdown and clock repaint once per second; nothing is
     drawn in between.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pygame

import _benchutil  # noqa: F401  (side effects: sys.path, quiet pygame)

Rect = tuple[int, int, int, int]

# Relative layout (x, y, w, h) on the logical canvas.
LAYOUT: dict[str, tuple[float, float, float, float]] = {
    "light": (0.0, 0.0, 1.0, 0.33),
    "countdown": (0.0, 0.33, 0.65, 0.50),
    "info": (0.65, 0.33, 0.35, 0.50),
    "operator": (0.0, 0.83, 1.0, 0.11),
    "status": (0.0, 0.94, 1.0, 0.06),
}

GREEN = (0, 170, 60)
YELLOW = (240, 200, 0)
BG = (16, 16, 20)
PANEL = (32, 34, 40)
FG = (240, 240, 240)
BUTTON = (60, 64, 76)
EMERGENCY = (200, 20, 20)

END_S = 120.0
WARN_S = 30.0


def remaining_s(now_s: float) -> float:
    return END_S - (now_s % END_S)


class Scene:
    """Paints the benchmark screen's sections onto surfaces."""

    def __init__(self, size: tuple[int, int]) -> None:
        pygame.font.init()
        self.size = size
        w, h = size
        self.rects: dict[str, Rect] = {
            name: (round(x * w), round(y * h), round(rw * w), round(rh * h))
            for name, (x, y, rw, rh) in LAYOUT.items()
        }
        self.fonts = {
            "light": pygame.font.Font(None, max(8, int(h * 0.14))),
            "countdown": pygame.font.Font(None, max(8, int(h * 0.38))),
            "info": pygame.font.Font(None, max(8, int(h * 0.055))),
            "operator": pygame.font.Font(None, max(8, int(h * 0.045))),
            "status": pygame.font.Font(None, max(8, int(h * 0.035))),
        }
        self.glyphs = {ch: self.fonts["countdown"].render(ch, True, FG) for ch in "0123456789:."}
        self.surfaces = {name: pygame.Surface((r[2], r[3])) for name, r in self.rects.items()}

    # -- painters -------------------------------------------------------------

    def _text(
        self,
        surf: pygame.Surface,
        font_key: str,
        text: str,
        center: tuple[int, int],
        color: tuple[int, int, int] = FG,
    ) -> None:
        img = self.fonts[font_key].render(text, True, color)
        surf.blit(img, img.get_rect(center=center))

    def _countdown_text(self, now_s: float, tenths: bool) -> str:
        rem = remaining_s(now_s)
        if tenths:
            whole = int(rem)
            return f"{whole // 60}:{whole % 60:02d}.{int((rem - whole) * 10)}"
        whole = int(rem + 0.999)
        return f"{whole // 60}:{whole % 60:02d}"

    def paint(
        self, name: str, surf: pygame.Surface, now_s: float, cached: bool, tenths: bool = False
    ) -> None:
        w, h = surf.get_size()
        if name == "light":
            green = remaining_s(now_s) > WARN_S
            surf.fill(GREEN if green else YELLOW)
            label = "SKJUT - Linje AB" if green else "30 SEKUNDER KVAR"
            self._text(surf, "light", label, (w // 2, h // 2), (0, 0, 0))
        elif name == "countdown":
            surf.fill(BG)
            text = self._countdown_text(now_s, tenths)
            if cached:
                imgs = [self.glyphs[c] for c in text]
                total = sum(i.get_width() for i in imgs)
                x = (w - total) // 2
                y = (h - imgs[0].get_height()) // 2
                for img in imgs:
                    surf.blit(img, (x, y))
                    x += img.get_width()
            else:
                self._text(surf, "countdown", text, (w // 2, h // 2))
            frac = remaining_s(now_s) / END_S
            bar_h = max(2, h // 25)
            pygame.draw.rect(surf, PANEL, (w // 20, h - 2 * bar_h, w * 9 // 10, bar_h))
            pygame.draw.rect(surf, GREEN, (w // 20, h - 2 * bar_h, int(w * 9 // 10 * frac), bar_h))
        elif name == "info":
            surf.fill(PANEL)
            lines = [
                time.strftime("%H:%M:%S"),
                "Inomhus 18 m",
                "Omgång 3 av 12",
                "Linje AB",
            ]
            for i, line in enumerate(lines):
                self._text(surf, "info", line, (w // 2, h * (2 * i + 1) // (2 * len(lines))))
        elif name == "operator":
            surf.fill(BG)
            labels = [("NÖDSTOPP", EMERGENCY), ("Paus", BUTTON), ("Nästa omgång", BUTTON)]
            bw = w // len(labels)
            for i, (label, color) in enumerate(labels):
                rect = pygame.Rect(i * bw + w // 100, h // 10, bw - w // 50, h * 8 // 10)
                pygame.draw.rect(surf, color, rect, border_radius=h // 8)
                self._text(surf, "operator", label, rect.center)
        elif name == "status":
            surf.fill(PANEL)
            self._text(
                surf, "status", "Ljus: anslutna  |  Ljud: på  |  Benchmark", (w // 2, h // 2)
            )

    def paint_all_into(self, target: pygame.Surface, now_s: float) -> None:
        """Mode A: paint every section into the full-frame target, uncached."""
        for name, r in self.rects.items():
            self.paint(name, target.subsurface(r), now_s, cached=False)


# --------------------------------------------------------------------------- backends


class SoftwareBackend:
    """Classic pygame display surface: CPU blits, then a full flip."""

    name = "software"

    def __init__(self, size: tuple[int, int], fullscreen: bool, vsync: bool) -> None:
        pygame.display.init()
        flags = pygame.FULLSCREEN if fullscreen else 0
        self.screen = pygame.display.set_mode((0, 0) if fullscreen else size, flags)
        pygame.display.set_caption("archerytimer benchmark (software)")
        self.size = self.screen.get_size()
        self.sections: dict[str, tuple[pygame.Surface, Rect]] = {}

    def full_target(self) -> pygame.Surface:
        return self.screen

    def present_full(self) -> None:
        pygame.display.flip()

    def update_section(self, name: str, surf: pygame.Surface, rect: Rect) -> None:
        self.sections[name] = (surf, rect)

    def compose_and_present(self) -> None:
        for surf, rect in self.sections.values():
            self.screen.blit(surf, rect[:2])
        pygame.display.flip()

    def close(self) -> None:
        pygame.display.quit()


class GpuBackend:
    """SDL2 renderer API: section textures composed and scaled on the GPU."""

    name = "gpu"

    def __init__(self, size: tuple[int, int], fullscreen: bool, vsync: bool) -> None:
        from pygame._sdl2 import video

        self._video = video
        pygame.display.init()
        if fullscreen:
            self.window = video.Window("archerytimer benchmark (gpu)", fullscreen_desktop=True)
        else:
            self.window = video.Window("archerytimer benchmark (gpu)", size=size)
        self.renderer = video.Renderer(self.window, vsync=vsync)
        self.renderer.logical_size = size  # GPU scales the logical canvas to the output
        self.size = size
        self._full_surface: pygame.Surface | None = None
        self._full_texture: Any = None
        self.textures: dict[str, tuple[Any, Rect]] = {}

    def full_target(self) -> pygame.Surface:
        if self._full_surface is None:
            self._full_surface = pygame.Surface(self.size)
            self._full_texture = self._video.Texture(self.renderer, self.size, streaming=True)
        return self._full_surface

    def present_full(self) -> None:
        self._full_texture.update(self._full_surface)
        self.renderer.clear()
        self._full_texture.draw()
        self.renderer.present()

    def update_section(self, name: str, surf: pygame.Surface, rect: Rect) -> None:
        entry = self.textures.get(name)
        if entry is None:
            tex = self._video.Texture(self.renderer, surf.get_size(), streaming=True)
            self.textures[name] = (tex, rect)
        else:
            tex = entry[0]
        tex.update(surf)

    def compose_and_present(self) -> None:
        self.renderer.draw_color = (0, 0, 0, 255)
        self.renderer.clear()
        for tex, rect in self.textures.values():
            tex.draw(dstrect=rect)
        self.renderer.present()

    def close(self) -> None:
        self.window.destroy()
        pygame.display.quit()


def open_backend(name: str, size: tuple[int, int], fullscreen: bool, vsync: bool) -> Any:
    cls = {"gpu": GpuBackend, "software": SoftwareBackend}[name]
    return cls(size, fullscreen, vsync)


# --------------------------------------------------------------------------- frame loop


def busy_python(ms: float) -> None:
    """Pure-Python CPU work holding the GIL, with allocation churn (overload mode)."""
    end = time.perf_counter() + ms / 1000
    junk: list[dict[str, int]] = []
    while time.perf_counter() < end:
        junk.append({"a": len(junk)})
        if len(junk) > 2000:
            junk = []


def run_frames(
    backend: Any,
    mode: str,
    fps_cap: float,
    should_stop: Callable[[], bool],
    extra_python_ms: float = 0.0,
) -> dict[str, Any]:
    """Run the frame loop for one render mode until ``should_stop()``.

    Returns raw per-frame timings in ns: ``work`` (frame start to before
    present), ``present`` (present call), ``interval`` (between frame starts).
    """
    scene = Scene(backend.size)
    now_s = time.time
    for name, rect in scene.rects.items():
        scene.paint(name, scene.surfaces[name], now_s(), cached=True)
        backend.update_section(name, scene.surfaces[name], rect)
    backend.compose_and_present()

    work: list[int] = []
    present: list[int] = []
    interval: list[int] = []
    period = 1.0 / fps_cap if fps_cap > 0 else 0.0
    next_frame = time.perf_counter()
    last_start = 0
    last_second = int(now_s())
    perf_ns = time.perf_counter_ns
    aborted = False

    while not should_stop():
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                aborted = True
        if aborted:
            break

        if mode == "C":
            sec = int(now_s())
            if sec == last_second:
                wait = min(0.05, (sec + 1) - now_s())
                if wait > 0:
                    time.sleep(wait)
                continue
            last_second = sec

        t_start = perf_ns()
        if last_start:
            interval.append(t_start - last_start)
        last_start = t_start
        t = now_s()

        if mode == "A":
            scene.paint_all_into(backend.full_target(), t)
            if extra_python_ms:
                busy_python(extra_python_ms)
            t_pre = perf_ns()
            backend.present_full()
        else:
            dirty = ["countdown"] if mode == "B" else ["countdown", "info"]
            for name in dirty:
                scene.paint(name, scene.surfaces[name], t, cached=True, tenths=(mode == "B"))
                backend.update_section(name, scene.surfaces[name], scene.rects[name])
            if extra_python_ms:
                busy_python(extra_python_ms)
            t_pre = perf_ns()
            backend.compose_and_present()
        t_end = perf_ns()
        work.append(t_pre - t_start)
        present.append(t_end - t_pre)

        if period and mode != "C":
            next_frame += period
            delay = next_frame - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -period:
                next_frame = time.perf_counter()  # fell behind: don't try to catch up

    return {"work": work, "present": present, "interval": interval, "aborted": aborted}

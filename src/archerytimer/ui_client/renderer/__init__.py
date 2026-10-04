"""Renderer backends. ``open_renderer`` picks the GPU path and falls back to software."""

from __future__ import annotations

import logging
import os
import sys

from archerytimer.ui_client.renderer.base import DisplayConfig, Renderer

log = logging.getLogger("archerytimer.ui")

__all__ = ["DisplayConfig", "Renderer", "open_renderer"]


def _prefer_gles_on_console() -> None:
    """KMSDRM gives a GLES context, but SDL lists the desktop-GL 'opengl' render driver first:
    it picks that, every GL call is invalid and the screen stays black. Ask for GLES."""
    on_console = (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    )
    if on_console or os.environ.get("SDL_VIDEODRIVER") == "kmsdrm":
        os.environ.setdefault("SDL_RENDER_DRIVER", "opengles2")
        os.environ.setdefault("SDL_FRAMEBUFFER_ACCELERATION", "opengles2")


def open_renderer(cfg: DisplayConfig) -> Renderer:
    _prefer_gles_on_console()
    if cfg.kind in ("auto", "gpu"):
        try:
            from archerytimer.ui_client.renderer.gpu import GpuRenderer

            return GpuRenderer(cfg)
        except Exception as exc:
            if cfg.kind == "gpu":
                raise
            log.warning("GPU renderer unavailable (%s); using software", exc)
    from archerytimer.ui_client.renderer.software import SoftwareRenderer

    return SoftwareRenderer(cfg)

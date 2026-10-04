"""Section layout as fractions of the output, per view profile."""

from __future__ import annotations

Rel = tuple[float, float, float, float]  # x, y, w, h as fractions
PixelRect = tuple[int, int, int, int]

PROFILES = ("full", "audience")

# Full: archers' view plus the operator bar. Audience: the same without any controls.
_FULL: dict[str, Rel] = {
    "light": (0.0, 0.0, 1.0, 0.33),
    "countdown": (0.0, 0.33, 0.62, 0.50),
    "info": (0.62, 0.33, 0.38, 0.50),
    "operator": (0.0, 0.83, 1.0, 0.11),
    "status": (0.0, 0.94, 1.0, 0.06),
}
_AUDIENCE: dict[str, Rel] = {
    "light": (0.0, 0.0, 1.0, 0.36),
    "countdown": (0.0, 0.36, 0.62, 0.58),
    "info": (0.62, 0.36, 0.38, 0.58),
    "status": (0.0, 0.94, 1.0, 0.06),
}


# An operator screen replaces light, countdown and info (they live on as a banner) but never
# the operator bar: the emergency stop must always be on screen.
_SCREEN: dict[str, Rel] = {
    "screen": (0.0, 0.0, 1.0, 0.83),
    "operator": (0.0, 0.83, 1.0, 0.11),
    "status": (0.0, 0.94, 1.0, 0.06),
}


_IDLE: dict[str, Rel] = {"idle": (0.0, 0.0, 1.0, 1.0)}


def layout_for(
    profile: str, show_operator: bool, screen_open: bool = False, idle: bool = False
) -> dict[str, Rel]:
    """The operator bar exists only in the ``full`` profile and can be hidden there. The idle
    screen replaces everything: it only shows while nothing runs, and any input ends it."""
    if idle:
        return _IDLE
    if screen_open and profile == "full":
        return _SCREEN
    return _FULL if profile == "full" and show_operator else _AUDIENCE


def pixel_rects(rels: dict[str, Rel], size: tuple[int, int]) -> dict[str, PixelRect]:
    """Integer rects that tile the output exactly (edges are rounded, never sized)."""
    w, h = size
    out: dict[str, PixelRect] = {}
    for name, (x, y, rw, rh) in rels.items():
        x0, y0 = round(x * w), round(y * h)
        x1, y1 = round((x + rw) * w), round((y + rh) * h)
        out[name] = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
    return out


def logical_size_for(output: tuple[int, int], max_height: int = 1080) -> tuple[int, int]:
    """GPU path: render at most 1080p-high and let the GPU scale up (4K displays)."""
    w, h = output
    if h <= max_height:
        return output
    scale = max_height / h
    return (max(1, round(w * scale)), max_height)

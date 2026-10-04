"""Colours. Sizes are never hardcoded in pixels: everything is a fraction of the output."""

from __future__ import annotations

from archerytimer.core.models import Light

Color = tuple[int, int, int]

BG: Color = (16, 16, 20)
PANEL: Color = (32, 34, 40)
FG: Color = (240, 240, 240)
MUTED: Color = (150, 154, 166)
BUTTON: Color = (60, 64, 76)
BUTTON_HOVER: Color = (84, 90, 108)
BUTTON_DISABLED: Color = (36, 38, 46)
PRIMARY: Color = (30, 110, 200)
PRIMARY_HOVER: Color = (50, 134, 230)
EMERGENCY: Color = (200, 20, 20)
EMERGENCY_HOVER: Color = (230, 50, 50)
NEUTRAL: Color = (70, 74, 86)
UNDO: Color = (214, 150, 0)
UNDO_HOVER: Color = (240, 176, 20)
IDLE_DIM: Color = (64, 66, 74)

LIGHT_COLORS: dict[Light, Color] = {
    Light.GREEN: (0, 170, 60),
    Light.YELLOW: (240, 200, 0),
    Light.RED: (200, 20, 20),
    Light.OFF: (40, 40, 46),
}
# Text colour that reads well on each light colour.
LIGHT_TEXT: dict[Light, Color] = {
    Light.GREEN: (0, 0, 0),
    Light.YELLOW: (0, 0, 0),
    Light.RED: (255, 255, 255),
    Light.OFF: (230, 230, 230),
}

"""Operator screens: a stack of declarative pages shown above the main timer view.

A screen turns the current context into ``Widget`` values and reacts to widget activations
and to the few keyboard actions screens understand (back, primary, confirm). The timer
itself stays visible as a banner and the operator bar (with the emergency stop) stays
on screen, so opening a menu never hides the light.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from archerytimer.ui_client.context import ViewContext
from archerytimer.ui_client.widgets import Rect, Widget

if TYPE_CHECKING:
    from archerytimer.ui_client.app import UiApp

MARGIN = 0.03
TITLE_RECT: Rect = (MARGIN, 0.02, 1 - 2 * MARGIN, 0.10)
NAV_Y, NAV_H = 0.85, 0.13


class Screen:
    name = ""

    def __init__(self, app: UiApp) -> None:
        self.app = app

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        raise NotImplementedError

    def activate(self, wid: str) -> None:
        """A widget was clicked (``wid`` is the widget id)."""

    def primary(self) -> None:
        """Space / Enter / clicker "next": the screen's obvious forward action, if any."""

    def confirm(self) -> None:
        """The explicit "yes" key; only confirm dialogs react."""

    def back(self) -> None:
        self.app.close_screen()


def title(text: str) -> Widget:
    return Widget("", "title", TITLE_RECT, text)


def nav_back(label: str, wid: str = "back") -> Widget:
    return Widget(wid, "button", (MARGIN, NAV_Y, 0.25, NAV_H), label)


def nav_next(label: str, wid: str = "next", *, enabled: bool = True) -> Widget:
    return Widget(wid, "primary", (0.60, NAV_Y, 1 - 0.60 - MARGIN, NAV_H), label, enabled=enabled)


def grid(
    n: int, cols: int, top: float, bottom: float, max_h: float = 0.2, gap: float = 0.02
) -> list[Rect]:
    """``n`` equal cells filling [top, bottom] row by row; the last row is left-aligned."""
    if n == 0:
        return []
    rows = -(-n // cols)
    cell_h = min(max_h, (bottom - top - gap * (rows - 1)) / rows)
    cell_w = (1 - 2 * MARGIN - gap * (cols - 1)) / cols
    out: list[Rect] = []
    for i in range(n):
        r, c = divmod(i, cols)
        out.append((MARGIN + c * (cell_w + gap), top + r * (cell_h + gap), cell_w, cell_h))
    return out


def stepper(wid: str, label: str, value: str, y: float, h: float = 0.10) -> list[Widget]:
    """A labelled value with minus and plus buttons: ids ``<wid>-`` and ``<wid>+``."""
    return [
        Widget("", "row", (MARGIN, y, 0.44, h), label),
        Widget(f"{wid}-", "button", (0.50, y, 0.12, h), "−"),
        Widget("", "value", (0.62, y, 0.22, h), value),
        Widget(f"{wid}+", "button", (0.84, y, 0.12, h), "+"),
    ]


def fmt_seconds(seconds: float, off_text: str = "") -> str:
    s = round(seconds)
    if s <= 0 and off_text:
        return off_text
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else f"{s} s"

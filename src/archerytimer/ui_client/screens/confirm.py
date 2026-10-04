"""Confirm dialog for destructive actions: reset, quit, replacing a session.

Cancel is the safe default: Space/Enter (primary) and Back cancel; only a click on the red
button or the explicit confirm key ("y") goes through.
"""

from __future__ import annotations

from typing import Any, Callable

from archerytimer.ui_client.context import ViewContext
from archerytimer.ui_client.screens.base import MARGIN, Screen
from archerytimer.ui_client.widgets import Widget


class ConfirmScreen(Screen):
    name = "confirm"

    def __init__(self, app: Any, message: str, yes_label: str, on_yes: Callable[[], None]) -> None:
        super().__init__(app)
        self.message = message
        self.yes_label = yes_label
        self.on_yes = on_yes

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        return [
            Widget("", "value", (MARGIN, 0.18, 1 - 2 * MARGIN, 0.30), self.message),
            Widget("cancel", "primary", (0.08, 0.60, 0.40, 0.20), ctx.t("common.cancel")),
            Widget("yes", "danger", (0.52, 0.60, 0.40, 0.20), self.yes_label),
        ]

    def activate(self, wid: str) -> None:
        if wid == "yes":
            self.confirm()
        elif wid == "cancel":
            self.back()

    def primary(self) -> None:
        self.back()

    def confirm(self) -> None:
        self.app.close_screen()
        self.on_yes()

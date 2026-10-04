"""Timers: quick timer lengths plus a custom timer (preparation, shooting, yellow warning).

The choice is the default for every new session until changed; "Standard" goes back to each
preset's own timing. The wizard's Advanced page can still tweak one session.
"""

from __future__ import annotations

from typing import Any, Optional

from archerytimer.ui_client.context import ViewContext
from archerytimer.ui_client.screens.base import (
    MARGIN,
    Screen,
    fmt_seconds,
    grid,
    nav_back,
    stepper,
    title,
)
from archerytimer.ui_client.screens.setup import step_timing
from archerytimer.ui_client.widgets import Widget

KEYS = ("prep_s", "shoot_s", "warn_s")
# Where a "standard" value starts when the operator first presses + or -.
START_VALUES = {"prep_s": 10.0, "shoot_s": 120.0, "warn_s": 30.0}


class TimersScreen(Screen):
    name = "timers"

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    def _timing(self) -> dict[str, Optional[float]]:
        cur = self.app.prefs_data.timing or {}
        return {k: cur.get(k) for k in KEYS}

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        cur = self._timing()
        standard = all(v is None for v in cur.values())
        out = [title(t("timers.title"))]
        cards = [("std", t("timers.standard"), t("timers.standard_sub"), standard)]
        for tp in self.app.timing_presets:
            same = (cur["prep_s"], cur["shoot_s"], cur["warn_s"]) == (
                tp.prep_s,
                tp.shoot_s,
                tp.warn_s,
            )
            sub = f"{fmt_seconds(tp.prep_s)} + {fmt_seconds(tp.shoot_s)}"
            cards.append((f"tp:{tp.id}", ctx.t.pick(tp.name, tp.id), sub, same))
        for (wid, label, sub, selected), rect in zip(cards, grid(len(cards), 4, 0.13, 0.40, 0.13)):
            out.append(Widget(wid, "card", rect, label, sub, selected=selected))
        off = t("common.off")
        std = t("timers.standard")
        for i, (key, label) in enumerate(
            (
                ("prep_s", "advanced.prep"),
                ("shoot_s", "advanced.shoot"),
                ("warn_s", "advanced.warn"),
            )
        ):
            v = cur[key]
            text = std if v is None else fmt_seconds(v, off)
            out += stepper(key, t(label), text, 0.42 + i * 0.115)
        out.append(Widget("", "text", (MARGIN, 0.785, 1 - 2 * MARGIN, 0.05), t("timers.hint")))
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        app = self.app
        if wid == "back":
            self.back()
        elif wid == "std":
            app.set_timing(None)
        elif wid.startswith("tp:"):
            for tp in app.timing_presets:
                if tp.id == wid[3:]:
                    app.set_timing(
                        {"prep_s": tp.prep_s, "shoot_s": tp.shoot_s, "warn_s": tp.warn_s}
                    )
        elif wid[:-1] in KEYS:
            key, sign = wid[:-1], 1 if wid[-1] == "+" else -1
            cur = self._timing()
            if all(v is None for v in cur.values()):
                cur = dict(START_VALUES)  # first edit turns "standard" into a custom timer
            val = cur[key]
            cur[key] = step_timing(START_VALUES[key] if val is None else val, key, sign)
            app.set_timing(cur)

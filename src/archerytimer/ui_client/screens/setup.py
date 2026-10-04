"""Setup in three steps: pick a preset card, confirm lines and ends, start the session.

Timing overrides and toggles sit on a separate Advanced page. The last used setup is
remembered and offered as one button on step 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from archerytimer.core.models import Mode
from archerytimer.ui_client.context import ViewContext
from archerytimer.ui_client.presets import Preset, find
from archerytimer.ui_client.screens.base import (
    MARGIN,
    Screen,
    fmt_seconds,
    grid,
    nav_back,
    nav_next,
    stepper,
    title,
)
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.widgets import Widget

MAX_ENDS = 99
MAX_PRACTICE = 9
# (min, max, step) in seconds for the Advanced steppers
PREP_RANGE = (0, 60, 5)
SHOOT_RANGE = (10, 900, 10)
WARN_RANGE = (0, 120, 5)


@dataclass
class SetupState:
    preset: Preset
    groups: tuple[str, ...]
    ends: int
    practice: int
    prep_s: Optional[float] = None  # None: keep the sequence's own value
    shoot_s: Optional[float] = None
    warn_s: Optional[float] = None
    auto_advance: bool = False
    alternate: bool = True

    @classmethod
    def from_preset(
        cls, preset: Preset, timing: Optional[dict[str, Optional[float]]] = None
    ) -> SetupState:
        st = cls(preset, preset.groups, preset.ends, preset.practice_ends)
        for key, value in (timing or {}).items():  # the operator's default timer, if any
            setattr(st, key, value)
        return st

    @classmethod
    def from_saved(cls, saved: Any, presets: list[Preset]) -> Optional[SetupState]:
        """Rebuild the remembered setup; None if it no longer fits the known presets."""
        try:
            preset = find(presets, str(saved["preset"]))
            if preset is None:
                return None
            groups = tuple(str(g) for g in saved["groups"])
            if not groups:
                return None
            st = cls(preset, groups, int(saved["ends"]), int(saved["practice"]))
            for key in ("prep_s", "shoot_s", "warn_s"):
                if saved.get(key) is not None:
                    setattr(st, key, float(saved[key]))
            st.auto_advance = bool(saved.get("auto_advance", False))
            st.alternate = bool(saved.get("alternate", True))
            return st
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    def to_saved(self) -> dict[str, Any]:
        return {
            "preset": self.preset.id,
            "groups": list(self.groups),
            "ends": self.ends,
            "practice": self.practice,
            "prep_s": self.prep_s,
            "shoot_s": self.shoot_s,
            "warn_s": self.warn_s,
            "auto_advance": self.auto_advance,
            "alternate": self.alternate,
        }

    def to_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "sequence_id": self.preset.sequence,
            "groups": list(self.groups),
            "total_ends": self.ends,
            "practice_ends": self.practice,
            "alternate_order": self.alternate,
            "auto_advance": self.auto_advance,
        }
        for key in ("prep_s", "shoot_s", "warn_s"):
            if getattr(self, key) is not None:
                args[key] = getattr(self, key)
        return args


def lines_label(groups: tuple[str, ...]) -> str:
    return " / ".join(groups)


def describe(app: Any, st: SetupState) -> str:
    """One line for cards and summaries: shooting time, lines, number of ends."""
    t = app.t
    parts = []
    shoot = (
        st.shoot_s
        if st.shoot_s is not None
        else app.link.timings(st.preset.sequence).get("shoot_s")
    )
    if shoot:
        parts.append(fmt_seconds(shoot))
    parts.append(lines_label(st.groups))
    if st.preset.open_ended:
        parts.append(t("setup.open_ended"))
    else:
        counts = []
        if st.ends:
            counts.append(t("setup.n_ends", n=st.ends))
        if st.practice:
            counts.append(t("setup.n_practice", n=st.practice))
        parts.append(" + ".join(counts))
    return " · ".join(parts)


class SetupScreen(Screen):
    name = "setup"

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.step = 1
        self.state: Optional[SetupState] = None

    # ------------------------------------------------------------ helpers

    def _presets(self) -> list[Preset]:
        known = set(self.app.link.sequence_ids())
        return [p for p in self.app.presets if p.sequence in known]

    def _last(self) -> Optional[SetupState]:
        return SetupState.from_saved(self.app.prefs_data.last_setup, self._presets())

    def _in_progress(self) -> bool:
        snap = self.app.link.snapshot
        return snap is not None and (
            snap.mode in (Mode.RUNNING, Mode.FINISHED)
            or (snap.mode is Mode.WAITING and snap.round_index > 0)
        )

    # ------------------------------------------------------------ widgets

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        if self.step == 1 or self.state is None:
            return self._step1(ctx)
        st = self.state
        out = [title(t(f"setup.step{self.step}_title"))]
        if self.step == 2:
            out += self._step2(ctx, st)
        else:
            out += self._step3(ctx, st)
        return out

    def _step1(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        out = [title(t("setup.step1_title")), nav_back(t("common.cancel"), "cancel")]
        presets = self._presets()
        top = 0.14
        last = self._last()
        if last is not None:
            name = t.pick(last.preset.name, last.preset.id)
            out.append(
                Widget(
                    "last",
                    "card",
                    (MARGIN, top, 1 - 2 * MARGIN, 0.14),
                    t("setup.use_last", name=name),
                    describe(self.app, last),
                )
            )
            top += 0.17
        if not presets:
            out.append(
                Widget("", "text", (MARGIN, 0.4, 1 - 2 * MARGIN, 0.1), t("setup.no_presets"))
            )
        for p, rect in zip(presets, grid(len(presets), 2, top, 0.82)):
            st = SetupState.from_preset(p, self.app.prefs_data.timing)
            out.append(
                Widget(
                    f"preset:{p.id}", "card", rect, ctx.t.pick(p.name, p.id), describe(self.app, st)
                )
            )
        return out

    def _step2(self, ctx: ViewContext, st: SetupState) -> list[Widget]:
        t = ctx.t
        out = [Widget("", "text", (MARGIN, 0.13, 1 - 2 * MARGIN, 0.07), t("setup.lines"))]
        opts = st.preset.line_options
        gap = 0.02
        w = (1 - 2 * MARGIN - gap * (len(opts) - 1)) / len(opts)
        for i, groups in enumerate(opts):
            out.append(
                Widget(
                    f"lines:{i}",
                    "button",
                    (MARGIN + i * (w + gap), 0.21, w, 0.12),
                    lines_label(groups),
                    selected=groups == st.groups,
                )
            )
        if st.preset.open_ended:
            out.append(
                Widget("", "row", (MARGIN, 0.42, 1 - 2 * MARGIN, 0.10), t("setup.open_ended_hint"))
            )
        else:
            out += stepper("ends", t("setup.ends"), str(st.ends), 0.40)
            out += stepper("practice", t("setup.practice"), str(st.practice), 0.54)
        out.append(Widget("advanced", "button", (MARGIN, 0.70, 0.34, 0.11), t("setup.advanced")))
        out += [nav_back(t("common.back")), nav_next(t("common.next"), enabled=self._valid(st))]
        return out

    @staticmethod
    def _valid(st: SetupState) -> bool:
        return st.ends + st.practice >= 1

    def _step3(self, ctx: ViewContext, st: SetupState) -> list[Widget]:
        t = ctx.t
        lines = [
            ctx.t.pick(st.preset.name, st.preset.id),
            describe(self.app, st),
        ]
        out = [Widget("", "value", (MARGIN, 0.16, 1 - 2 * MARGIN, 0.26), "\n".join(lines))]
        if self._in_progress():
            out.append(
                Widget("", "warn", (MARGIN, 0.46, 1 - 2 * MARGIN, 0.08), t("setup.replaces"))
            )
        out.append(Widget("advanced", "button", (MARGIN, 0.60, 0.34, 0.11), t("setup.advanced")))
        out += [nav_back(t("common.back")), nav_next(t("setup.start"), "start")]
        return out

    # ------------------------------------------------------------ actions

    def activate(self, wid: str) -> None:
        st = self.state
        if wid == "cancel":
            self.app.close_screen()
        elif wid == "back":
            self.back()
        elif wid == "last":
            last = self._last()
            if last is not None:
                self.state, self.step = last, 3
        elif wid.startswith("preset:"):
            preset = find(self._presets(), wid[7:])
            if preset is not None:
                self.state, self.step = (
                    SetupState.from_preset(preset, self.app.prefs_data.timing),
                    2,
                )
        elif st is None:
            return
        elif wid.startswith("lines:"):
            st.groups = st.preset.line_options[int(wid[6:])]
        elif wid in ("ends-", "ends+"):
            st.ends = _clamp(st.ends + (1 if wid[-1] == "+" else -1), 0, MAX_ENDS)
        elif wid in ("practice-", "practice+"):
            st.practice = _clamp(st.practice + (1 if wid[-1] == "+" else -1), 0, MAX_PRACTICE)
        elif wid == "advanced":
            self.app.open_screen(AdvancedScreen(self.app, st))
        elif wid == "next":
            if self._valid(st):
                self.step = 3
        elif wid == "start":
            self._start(st)

    def primary(self) -> None:
        if self.step == 2:
            self.activate("next")
        elif self.step == 3:
            self.activate("start")

    def back(self) -> None:
        if self.step > 1 and self.state is not None:
            self.step -= 1
        else:
            self.app.close_screen()

    def _start(self, st: SetupState) -> None:
        snap = self.app.link.snapshot
        if snap is not None and snap.mode is Mode.RUNNING:
            return  # the engine refuses to reconfigure mid-end; the menu does not offer it either
        if self._in_progress():
            self.app.open_screen(
                ConfirmScreen(
                    self.app,
                    self.app.t("confirm.replace"),
                    self.app.t("confirm.replace_yes"),
                    lambda: self._apply(st),
                )
            )
        else:
            self._apply(st)

    def _apply(self, st: SetupState) -> None:
        self.app.apply_setup(st.to_args(), st.to_saved())


class AdvancedScreen(Screen):
    """Timing and behaviour toggles for the session being set up."""

    name = "advanced"

    def __init__(self, app: Any, state: SetupState) -> None:
        super().__init__(app)
        self.state = state

    def _defaults(self) -> dict[str, float]:
        return self.app.link.timings(self.state.preset.sequence)

    def _value(self, key: str) -> float:
        own = getattr(self.state, key)
        return float(own) if own is not None else self._defaults().get(key, 0.0)

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        st = self.state
        off = t("common.off")
        out = [title(t("advanced.title"))]
        out += stepper("prep_s", t("advanced.prep"), fmt_seconds(self._value("prep_s"), off), 0.14)
        out += stepper("shoot_s", t("advanced.shoot"), fmt_seconds(self._value("shoot_s")), 0.27)
        out += stepper("warn_s", t("advanced.warn"), fmt_seconds(self._value("warn_s"), off), 0.40)
        out.append(
            Widget(
                "auto_advance",
                "button",
                (MARGIN, 0.55, 0.46, 0.12),
                t(
                    "advanced.auto_advance",
                    state=t("common.on" if st.auto_advance else "common.off"),
                ),
                selected=st.auto_advance,
            )
        )
        out.append(
            Widget(
                "alternate",
                "button",
                (0.51, 0.55, 0.46, 0.12),
                t("advanced.alternate", state=t("common.on" if st.alternate else "common.off")),
                selected=st.alternate,
            )
        )
        out.append(Widget("", "text", (MARGIN, 0.70, 1 - 2 * MARGIN, 0.08), t("advanced.hint")))
        out.append(nav_next(t("common.done"), "done"))
        return out

    def activate(self, wid: str) -> None:
        st = self.state
        if wid == "done":
            self.app.close_screen()
        elif wid == "auto_advance":
            st.auto_advance = not st.auto_advance
        elif wid == "alternate":
            st.alternate = not st.alternate
        elif wid[:-1] in ("prep_s", "shoot_s", "warn_s"):
            key, sign = wid[:-1], 1 if wid[-1] == "+" else -1
            setattr(st, key, step_timing(self._value(key), key, sign))

    def primary(self) -> None:
        self.app.close_screen()


TIMING_RANGES = {"prep_s": PREP_RANGE, "shoot_s": SHOOT_RANGE, "warn_s": WARN_RANGE}


def step_timing(current: float, key: str, sign: int) -> float:
    """One +/- step of a timing value, snapped to the stepper's grid and range."""
    lo, hi, step = TIMING_RANGES[key]
    return float(_clamp(round(current / step) * step + sign * step, lo, hi))


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

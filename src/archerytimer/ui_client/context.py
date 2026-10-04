"""What the sections draw from: a snapshot plus local view state, and pure helpers on it.

The countdown follows the deadline principle: the core sends a deadline on its own
monotonic clock and each frame computes ``deadline - now_core``, where ``now_core`` is the
local monotonic clock plus the measured offset to the core (about 0 on the same machine).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from archerytimer.common.i18n import Translator
from archerytimer.core.models import Light, Mode, Snapshot
from archerytimer.ui_client import theme
from archerytimer.ui_client.presets import OPEN_ENDED

CORE_CONNECTING = "connecting"
CORE_OK = "ok"
CORE_LOST = "lost"

NS_PER_S = 1_000_000_000


@dataclass
class ViewContext:
    snap: Optional[Snapshot]
    core_state: str  # CORE_CONNECTING / CORE_OK / CORE_LOST
    t: Translator
    sequence_name: str = ""
    now_core_ns: int = 0
    offset_ns: int = 0
    rtt_ns: int = 0
    synced: bool = False
    wall_s: int = 0
    wall_text: str = ""
    wall_frac_ns: int = 0  # how far into the current wall-clock second we are
    tenths: bool = False
    hover: Optional[str] = None
    show_operator: bool = True
    screen: Any = None  # the open operator screen, if any
    idle_style: str = "clock"
    undo: bool = False  # the undo window after Stop end / Next is open
    undo_left_ns: int = 0
    roster: Optional[dict[str, Any]] = None  # last `roster` message (mesh v2), if any
    follower: Optional[dict[str, Any]] = (
        None  # last `follower` message (this core's access), if any
    )
    leader_rtt_ms: Optional[float] = None  # follower core: round trip to the main timer


@dataclass(frozen=True)
class LightView:
    label: str
    light: Light
    shape: str  # "circle" | "triangle" | "square" | "none": not colour alone


@dataclass(frozen=True)
class ButtonView:
    id: str
    action: str  # what pressing sends; "" when disabled
    label: str
    enabled: bool
    kind: str  # "emergency" | "primary" | "undo" | "normal"
    weight: float
    sub: str = ""  # small second line, e.g. what the next end is


def remaining_ns(snap: Snapshot, now_core_ns: int) -> Optional[int]:
    """Time left in the current phase, or None when no countdown applies."""
    if snap.mode is not Mode.RUNNING:
        return None
    if snap.paused or snap.emergency:
        return snap.remaining_at_pause_ns
    return max(0, snap.deadline_ns - now_core_ns)


def display_ns(snap: Snapshot, now_core_ns: int) -> Optional[int]:
    """What the countdown shows: time left, or the planned time while the next end waits."""
    rem = remaining_ns(snap, now_core_ns)
    if rem is None and snap.mode is Mode.WAITING and snap.planned_ns > 0:
        return snap.planned_ns
    return rem


def banner_view(ctx: ViewContext) -> tuple[LightView, str]:
    """Compact light + countdown shown above operator screens, so the light never hides."""
    lv = light_view(ctx)
    if ctx.snap is None or ctx.core_state != CORE_OK:
        return lv, ""
    rem = remaining_ns(ctx.snap, ctx.now_core_ns)
    return lv, "" if rem is None else countdown_text(rem, ctx.tenths)


def _step_ns(rem_ns: int, tenths: bool) -> int:
    """Granularity of the displayed text: 100 ms in the last 10 s if tenths are on."""
    return NS_PER_S // 10 if tenths and rem_ns <= 10 * NS_PER_S else NS_PER_S


def countdown_text(rem_ns: Optional[int], tenths: bool) -> str:
    if rem_ns is None:
        return "-:--"
    if _step_ns(rem_ns, tenths) != NS_PER_S:
        tenth = -(-rem_ns // (NS_PER_S // 10))  # ceil, like the whole-second display
        whole = tenth // 10
        return f"{whole // 60}:{whole % 60:02d}.{tenth % 10}"
    whole = -(-rem_ns // NS_PER_S)  # ceil: 0:01 stays until the very end
    return f"{whole // 60}:{whole % 60:02d}"


def next_text_change_ns(rem_ns: int, tenths: bool) -> int:
    """How much time must pass before ``countdown_text`` shows something different (> 0)."""
    step = _step_ns(rem_ns, tenths)
    return (rem_ns - 1) % step + 1


def light_view(ctx: ViewContext) -> LightView:
    t, snap = ctx.t, ctx.snap
    if ctx.core_state == CORE_LOST:
        return LightView(t("light.lost"), Light.RED, "square")
    if snap is None or ctx.core_state == CORE_CONNECTING:
        return LightView(t("light.connecting"), Light.OFF, "none")
    group = snap.group
    if snap.emergency:
        return LightView(t("light.emergency"), Light.RED, "square")
    if snap.mode is Mode.IDLE:
        return LightView(t("light.idle"), Light.OFF, "none")
    if snap.mode is Mode.FINISHED:
        return LightView(t("light.finished"), Light.RED, "square")
    if snap.mode is Mode.WAITING:
        key = "light.stop" if snap.phase_id == "END" else "light.ready"
        return LightView(t(key, group=group), Light.RED, "square")
    if snap.paused:
        return LightView(t("light.paused"), Light.RED, "square")
    if snap.phase_id == "PREP":
        return LightView(t("light.prep", group=group), snap.light, "square")
    if snap.light is Light.YELLOW:
        return LightView(t("light.warn", group=group), Light.YELLOW, "triangle")
    if snap.light is Light.GREEN:
        return LightView(t("light.shoot", group=group), Light.GREEN, "circle")
    return LightView(t("light.stop"), snap.light, "square")


def next_end_text(ctx: ViewContext) -> str:
    """ "Line CD · End 4 of 10": what the primary button will start."""
    snap, t = ctx.snap, ctx.t
    if snap is None:
        return ""
    key = "info.practice" if snap.practice else "info.end"
    if snap.total_ends >= OPEN_ENDED:
        key += "_open"
    return f"{t('info.line', group=snap.group)} · {t(key, n=snap.end_no, total=snap.total_ends)}"


def primary_button(ctx: ViewContext) -> ButtonView:
    t, snap = ctx.t, ctx.snap
    off = ButtonView("primary", "", t("button.primary_idle"), False, "primary", 3.0)
    if snap is None or ctx.core_state != CORE_OK:
        return off
    if snap.mode is Mode.WAITING:
        key = "button.primary_next" if snap.phase_id == "END" else "button.primary_start"
        return ButtonView("primary", "primary", t(key), True, "primary", 3.0, next_end_text(ctx))
    if snap.mode is Mode.RUNNING and snap.paused and not snap.emergency:
        return ButtonView("primary", "primary", t("button.primary_resume"), True, "primary", 3.0)
    if snap.mode is Mode.RUNNING:
        return ButtonView("primary", "", t("button.primary_running"), False, "primary", 3.0)
    if snap.mode is Mode.FINISHED:
        return ButtonView("primary", "", t("button.primary_finished"), False, "primary", 3.0)
    if snap.mode is Mode.IDLE:  # no session yet: the obvious next step is to set one up
        return ButtonView("primary", "setup", t("button.primary_idle"), True, "primary", 3.0)
    return off


# Permission (ipc/access.py) each button action needs on a follower; others are never restricted.
ACTION_PERM = {
    "primary": "primary",
    "start": "primary",
    "pause": "pause",
    "resume": "resume",
    "stop_end": "stop_end",
    "next": "next",
    "back": "back",
    "reset": "reset",
    "setup": "configure",
    "configure": "configure",
    "settings": "settings",
    "clear_emergency_continue": "clear_emergency",
    "clear_emergency_restart": "clear_emergency",
}
WATCH_ONLY = {
    "pending": "button.wait_approval",
    "blocked": "button.blocked",
    "denied": "button.watch_only",
}


def follower_status(ctx: ViewContext) -> str:
    """This core's access status when it follows a leader, else ``""``."""
    f = ctx.follower
    return str(f.get("status", "")) if isinstance(f, dict) else ""


def apply_access(ctx: ViewContext, buttons: list[ButtonView]) -> list[ButtonView]:
    """Grey out what a follower may not do. Emergency and the menu are never disabled."""
    status = follower_status(ctx)
    if not status or status == "waiting" or ctx.follower is None:
        return buttons
    perms = set(ctx.follower.get("perms", [])) if status == "approved" else set()
    out = []
    for b in buttons:
        if b.kind == "emergency" or b.id == "menu":
            out.append(b)
        elif status != "approved" or ACTION_PERM.get(b.action, "") not in perms:
            label = b.label
            if b.id == "primary" and status in WATCH_ONLY:
                label = ctx.t(WATCH_ONLY[status])
            out.append(ButtonView(b.id, "", label, False, b.kind, b.weight, ""))
        else:
            out.append(b)
    return out


def buttons_for(ctx: ViewContext) -> list[ButtonView]:
    """The operator bar, left to right. The emergency button never moves."""
    return apply_access(ctx, _buttons(ctx))


def _buttons(ctx: ViewContext) -> list[ButtonView]:
    t, snap = ctx.t, ctx.snap
    online = snap is not None and ctx.core_state == CORE_OK
    emergency = ButtonView(
        "emergency", "emergency", t("button.emergency"), online, "emergency", 2.0
    )
    if snap is not None and online and snap.emergency:
        return [
            emergency,
            ButtonView(
                "clear_continue",
                "clear_emergency_continue",
                t("button.clear_continue"),
                True,
                "primary",
                3.0,
            ),
            ButtonView(
                "clear_restart",
                "clear_emergency_restart",
                t("button.clear_restart"),
                True,
                "normal",
                3.0,
            ),
        ]
    running = online and snap is not None and snap.mode is Mode.RUNNING
    paused = running and snap is not None and snap.paused
    if paused:
        pause = ButtonView("pause", "resume", t("button.resume"), True, "normal", 1.5)
    else:
        pause = ButtonView(
            "pause", "pause" if running else "", t("button.pause"), running, "normal", 1.5
        )
    stop = ButtonView(
        "stop_end", "stop_end" if running else "", t("button.stop_end"), running, "normal", 1.5
    )
    can_back = online and snap is not None and snap.mode is Mode.WAITING and snap.round_index > 0
    if can_back and ctx.undo:
        back = ButtonView("back", "back", t("button.undo"), True, "undo", 1.5)
    else:
        back = ButtonView(
            "back", "back" if can_back else "", t("button.back"), can_back, "normal", 1.5
        )
    menu = ButtonView("menu", "menu", t("button.menu"), online, "normal", 1.0)
    return [emergency, primary_button(ctx), pause, stop, back, menu]


def light_colors(light: Light) -> tuple[theme.Color, theme.Color]:
    return theme.LIGHT_COLORS[light], theme.LIGHT_TEXT[light]

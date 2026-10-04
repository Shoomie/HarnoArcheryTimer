"""The UI frame loop: on-demand rendering of cached sections.

Per loop iteration: sleep until something can change (input, IPC message, or the next
second tick of the countdown or clock), handle events, draw only the sections whose
``key`` changed, and present only if something was drawn. The UI holds no timing
authority: it renders the core's snapshot and sends commands.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any, Callable, Optional

import pygame

from archerytimer.common.clock import NS_PER_S, Clock, MonotonicClock
from archerytimer.common.i18n import Translator
from archerytimer.core.models import Mode
from archerytimer.ipc.messages import Message, cmd_msg, settings_msg
from archerytimer.ui_client.context import (
    CORE_CONNECTING,
    CORE_LOST,
    CORE_OK,
    ViewContext,
    buttons_for,
)
from archerytimer.ui_client.core_link import CoreLink
from archerytimer.ui_client.fonts import Fonts
from archerytimer.ui_client.input import JoystickMap, KeyMap
from archerytimer.ui_client.layout import layout_for, pixel_rects
from archerytimer.ui_client.prefs import (
    ECO_FPS,
    IDLE_DELAYS_MIN,
    IDLE_STYLES,
    Prefs,
    PrefsStore,
)
from archerytimer.ui_client.presets import Preset, TimingPreset
from archerytimer.ui_client.renderer import Renderer
from archerytimer.ui_client.screens.base import Screen
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.screens.menu import MenuScreen, confirm_quit
from archerytimer.ui_client.screens.setup import SetupScreen
from archerytimer.ui_client.sections import (
    Countdown,
    IdleSection,
    InfoPanel,
    OperatorBar,
    ScreenSection,
    Section,
    StatusBar,
    TrafficLight,
)

log = logging.getLogger("archerytimer.ui")

WAKE_EVENT = pygame.USEREVENT + 1
# With no contact for this long the display goes RED: no contact means stop.
LOST_GRACE_NS = NS_PER_S
IDLE_POLL_MS = 1000
SLOW_FRAME_NS = 25_000_000
# What a view-only (audience) display may do. Emergency must work from anywhere.
AUDIENCE_ACTIONS = frozenset({"emergency", "quit"})
# Actions that stay in the UI and are never sent to the core.
LOCAL_ACTIONS = frozenset({"menu", "confirm", "quit", "toggle_operator", "setup"})
# Operator actions that can be taken back for a few seconds (the bar shows an Undo button).
UNDOABLE = frozenset({"stop_end", "next"})
UNDO_WINDOW_NS = 5 * NS_PER_S

SECTION_CLASSES: dict[str, type[Section]] = {
    "light": TrafficLight,
    "countdown": Countdown,
    "info": InfoPanel,
    "operator": OperatorBar,
    "screen": ScreenSection,
    "idle": IdleSection,
    "status": StatusBar,
}


@dataclass
class DisplaySettings:
    fps_cap: int = 60  # also 30, 15; 0 = uncapped
    tenths: bool = False  # tenths of a second in the final 10 s
    idle_render: str = "change"  # "change": only when something changed; "constant"


def post_wake() -> None:
    """Thread-safe: wake the UI loop from the link thread."""
    with contextlib.suppress(pygame.error):
        pygame.event.post(pygame.event.Event(WAKE_EVENT))


class UiApp:
    def __init__(
        self,
        link: CoreLink,
        renderer: Renderer,
        translator: Translator,
        *,
        profile: str = "full",
        display: Optional[DisplaySettings] = None,
        keymap: Optional[KeyMap] = None,
        joymap: Optional[JoystickMap] = None,
        clock: Optional[Clock] = None,
        wall: Callable[[], float] = time.time,
        autoconfigure: Optional[dict[str, Any]] = None,
        presets: Optional[list[Preset]] = None,
        timings: Optional[list[TimingPreset]] = None,
        prefs: Optional[PrefsStore] = None,
    ) -> None:
        self.link = link
        self.renderer = renderer
        self.t = translator
        self.profile = profile
        self.display = display or DisplaySettings()
        self.keymap = keymap or KeyMap()
        self.joymap = joymap or JoystickMap()
        self.clock: Clock = clock or MonotonicClock()
        self._wall = wall
        self._autoconfigure = autoconfigure
        self.running = True
        self.show_operator = True
        self.hover: Optional[str] = None
        self.presets: list[Preset] = presets or []
        self.timing_presets: list[TimingPreset] = timings or []
        self.prefs_store = prefs or PrefsStore(None)
        self.screens: list[Screen] = []
        self.idle_active = False
        self._last_activity_ns = self.clock.now_ns()
        self._seen_seq: Optional[int] = None
        self._undo_round = -1
        self._undo_until_ns = 0
        self._base_fps = self.display.fps_cap
        self._slow_log_ns = -NS_PER_S
        self._base_tenths = self.display.tenths
        self._apply_display_prefs()

        self.sections: dict[str, Section] = {}
        self.rects: dict[str, tuple[int, int, int, int]] = {}
        self.surfaces: dict[str, pygame.Surface] = {}
        self._last_keys: dict[str, Hashable] = {}
        self._last_overlay_keys: dict[str, Optional[Hashable]] = {}
        self._fonts: Optional[Fonts] = None
        self._last_present_ns = 0
        # counters, for tests and the benchmark
        self.presents = 0
        self.redraws: list[str] = []

    # ------------------------------------------------------------------ layout

    def build(self) -> None:
        """(Re)create section surfaces for the current output size and view settings."""
        size = self.renderer.logical_size
        if self._fonts is None or self._fonts.height != size[1]:
            self._fonts = Fonts(size[1])
        rels = layout_for(self.profile, self.show_operator, bool(self.screens), self.idle_active)
        self.rects = pixel_rects(rels, size)
        self.sections = {name: SECTION_CLASSES[name](self._fonts) for name in rels}
        self.surfaces = {name: pygame.Surface((r[2], r[3])) for name, r in self.rects.items()}
        self.renderer.clear_sections()
        self._last_keys.clear()
        self._last_overlay_keys.clear()

    # ------------------------------------------------------------------ context

    def make_context(self) -> ViewContext:
        now = self.clock.now_ns()
        link = self.link
        offset = link.estimator.offset_ns if link.estimator.synced else 0
        if not link.ever_connected:
            state = CORE_CONNECTING
        elif link.connected:
            state = CORE_OK if link.upstream_ok else CORE_LOST
        elif link.lost_since_ns is not None and now - link.lost_since_ns >= LOST_GRACE_NS:
            state = CORE_LOST
        else:
            state = CORE_OK  # a short blip: keep showing the last state
        wall = self._wall()
        snap = link.snapshot
        undo_left = self._undo_left_ns(now)
        return ViewContext(
            snap=snap,
            core_state=state,
            t=self.t,
            sequence_name=self.t.pick(link.sequence_names(snap.sequence_id)) if snap else "",
            now_core_ns=now + offset,
            offset_ns=offset,
            rtt_ns=link.estimator.rtt_ns,
            synced=link.estimator.synced,
            wall_text=time.strftime("%H:%M:%S", time.localtime(wall)),
            wall_frac_ns=int((wall % 1) * NS_PER_S),
            tenths=self.display.tenths,
            hover=self.hover,
            show_operator=self.show_operator,
            screen=self.screens[-1] if self.screens else None,
            idle_style=self.prefs_data.idle_style,
            undo=undo_left > 0,
            undo_left_ns=undo_left,
            wall_s=int(wall),
            roster=getattr(link, "roster", None),
            follower=getattr(link, "follower", None),
            leader_rtt_ms=getattr(link, "leader_rtt_ms", None),
        )

    # ------------------------------------------------------------------ drawing

    def step(self, force: bool = False) -> bool:
        """Redraw dirty sections and present if anything changed. True if it presented."""
        self._update_idle()
        if not self.sections:
            self.build()
        ctx = self.make_context()
        dirty = force
        t0 = self.clock.now_ns()
        drawn: list[str] = []
        parts: list[str] = []
        for name, section in self.sections.items():
            key = section.key(ctx)
            if self._last_keys.get(name, _UNSET) != key:
                ts = self.clock.now_ns()
                section.draw(self.surfaces[name], ctx)
                tu = self.clock.now_ns()
                self.renderer.set_section(name, self.surfaces[name], self.rects[name])
                tw = self.clock.now_ns()
                parts.append(
                    f"{name} {self.surfaces[name].get_width()}x{self.surfaces[name].get_height()}"
                    f" paint {(tu - ts) / 1e6:.1f} upload {(tw - tu) / 1e6:.1f}"
                )
                self._last_keys[name] = key
                self.redraws.append(name)
                drawn.append(name)
                dirty = True
        for name, section in self.sections.items():
            okey = section.overlay_key(ctx)
            if okey is None and name not in self._last_overlay_keys:
                continue
            if self._last_overlay_keys.get(name, _UNSET) != okey:
                x, y, w, h = self.rects[name]
                self.renderer.set_overlay(name, section.overlay((w, h), ctx), (x, y))
                self._last_overlay_keys[name] = okey
                self.redraws.append(name)
                drawn.append(name)
                dirty = True
        t1 = self.clock.now_ns()
        if dirty or self.display.idle_render == "constant":
            self.renderer.present()
            self.presents += 1
            self._last_present_ns = self.clock.now_ns()
            self._log_slow_frame(parts, t1 - t0, self._last_present_ns - t1)
        return dirty

    def _log_slow_frame(self, parts: list[str], draw_ns: int, present_ns: int) -> None:
        """Pi tuning aid: a frame over 25 ms (draw + present) is logged, at most 5 per second."""
        if draw_ns + present_ns < SLOW_FRAME_NS:
            return
        now = self.clock.now_ns()
        if now - self._slow_log_ns < NS_PER_S // 5:
            return
        self._slow_log_ns = now
        log.warning(
            "slow frame: draw %.1f ms [%s], present %.1f ms",
            draw_ns / 1e6,
            "; ".join(parts) or "-",
            present_ns / 1e6,
        )

    def next_wake_ms(self) -> int:
        """How long the loop may sleep: until a section's picture changes by itself."""
        if self.display.idle_render == "constant":
            return max(1, int(1000 / self.display.fps_cap)) if self.display.fps_cap else 1
        ctx = self.make_context()
        waits = [IDLE_POLL_MS * 1_000_000]
        for section in self.sections.values():
            ns = section.next_change_ns(ctx)
            if ns is not None:
                waits.append(ns)
        left = self._idle_in_ns()
        if left is not None:
            waits.append(left)
        link = self.link
        if not link.connected and link.ever_connected and link.lost_since_ns is not None:
            left = LOST_GRACE_NS - (self.clock.now_ns() - link.lost_since_ns)
            if left > 0:
                waits.append(left)
        wait_ms = min(waits) // 1_000_000 + 1  # +1 ms: wake just after the change
        if self.display.fps_cap:
            wait_ms = max(wait_ms, 1)
        return max(1, int(wait_ms))

    # ------------------------------------------------------------------ input

    def handle_event(self, ev: pygame.event.Event) -> None:
        if ev.type in _ACTIVITY_EVENTS:
            was_idle = self.idle_active
            self._touch()
            if was_idle:
                # The press that wakes the screen does nothing else, so a stray key never starts
                # an end. Emergency is the exception: it must always act.
                if (ev.type == pygame.KEYDOWN and self.keymap.action_for(ev) == "emergency") or (
                    ev.type == pygame.JOYBUTTONDOWN and self.joymap.action_for(ev) == "emergency"
                ):
                    self.dispatch("emergency")
                self.step(force=True)
                return
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.KEYDOWN:
            action = self.keymap.action_for(ev)
            if action:
                self.dispatch(action)
        elif ev.type == pygame.JOYBUTTONDOWN:
            action = self.joymap.action_for(ev)
            if action:
                self.dispatch(action)
        elif ev.type == pygame.MOUSEMOTION:
            self._set_hover(self._hit(ev.pos))
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._click(ev.pos)
        elif ev.type in _RESIZE_EVENTS:
            if self.renderer.refresh_size():
                self.build()
            self.step(force=True)

    def _hit(self, pos: tuple[int, int]) -> Optional[str]:
        """The control under a window position: an operator-bar button id, or ``w:<id>`` for a
        widget of the open screen."""
        logical = self.renderer.to_logical(pos)
        if logical is None:
            return None
        ctx = self.make_context()
        for name in ("screen", "operator"):
            if name not in self.sections:
                continue
            x, y, w, h = self.rects[name]
            local = (logical[0] - x, logical[1] - y)
            if 0 <= local[0] < w and 0 <= local[1] < h:
                return self.sections[name].hit(local, (w, h), ctx)
        return None

    def _set_hover(self, button_id: Optional[str]) -> None:
        if button_id != self.hover:
            self.hover = button_id

    def _click(self, pos: tuple[int, int]) -> None:
        hit = self._hit(pos)
        if hit is None:
            return
        if hit.startswith("w:"):
            if self.screens:
                self.screens[-1].activate(hit[2:])
            return
        for b in buttons_for(self.make_context()):
            if b.id == hit and b.enabled and b.action:
                # The bar always talks to the core, even while a screen is open: its primary
                # button must mean "start end", never the screen's own default action.
                if b.action in LOCAL_ACTIONS:
                    self.dispatch(b.action)
                else:
                    self.send_action(b.action)
                return

    # ------------------------------------------------------------------ idle screen

    def _touch(self) -> None:
        self._last_activity_ns = self.clock.now_ns()
        self._wake()

    def _wake(self) -> None:
        if self.idle_active:
            self.idle_active = False
            self.build()

    def _idle_eligible(self) -> bool:
        snap = self.link.snapshot
        return (
            self.prefs_data.idle_screen
            and snap is not None
            and self.make_context().core_state == CORE_OK
            and snap.mode is not Mode.RUNNING
            and not snap.emergency
        )

    def _idle_in_ns(self) -> Optional[int]:
        """Time until the idle screen would start; None when it cannot (or already did)."""
        if self.idle_active or not self._idle_eligible():
            return None
        delay = self.prefs_data.idle_delay_min * 60 * NS_PER_S
        return max(0, delay - (self.clock.now_ns() - self._last_activity_ns))

    def _update_idle(self) -> None:
        snap = self.link.snapshot
        if snap is not None and snap.seq != self._seen_seq:
            self._seen_seq = snap.seq
            self._touch()  # the core reported something: wake and restart the timer
        if self.idle_active:
            if not self._idle_eligible():
                self._touch()
            return
        left = self._idle_in_ns()
        if left is not None and left <= 0:
            self.close_all_screens()
            self.idle_active = True
            self.hover = None
            self.build()

    # ------------------------------------------------------------------ undo

    def _undo_left_ns(self, now: int) -> int:
        snap = self.link.snapshot
        if (
            now >= self._undo_until_ns
            or snap is None
            or snap.mode is not Mode.WAITING
            or snap.round_index != self._undo_round + 1
        ):
            return 0
        return self._undo_until_ns - now

    # ------------------------------------------------------------------ screens

    def open_screen(self, screen: Screen) -> None:
        was_open = bool(self.screens)
        self.screens.append(screen)
        self.hover = None
        if not was_open:
            self.show_operator = True  # the emergency button must be on screen
            self.build()
        self._last_keys.pop("screen", None)

    def close_screen(self) -> None:
        if not self.screens:
            return
        self.screens.pop()
        self.hover = None
        if not self.screens:
            self.build()
        self._last_keys.pop("screen", None)

    def close_all_screens(self) -> None:
        if self.screens:
            self.screens.clear()
            self.hover = None
            self.build()

    # ------------------------------------------------------------------ operator actions

    def apply_setup(self, args: dict[str, Any], saved: dict[str, Any]) -> None:
        """Wizard finished: configure the core and remember the setup."""
        if self.link.send(cmd_msg("configure", args)):
            self.prefs_data.last_setup = saved
            self.prefs_store.save()
        else:
            log.warning("no connection to the core; setup not sent")
        self.close_all_screens()

    def send_settings(self, values: dict[str, Any]) -> None:
        """Settings that belong to the core (sound); the core confirms with its new state."""
        if not self.link.send(settings_msg(values)):
            log.warning("no connection to the core; settings not sent")

    def reset_session(self) -> None:
        self.send_action("reset")

    def quit_app(self) -> None:
        self.running = False

    @property
    def prefs_data(self) -> Prefs:
        return self.prefs_store.prefs

    # ------------------------------------------------------------------ display preferences

    def _apply_display_prefs(self) -> None:
        p = self.prefs_data
        self.display.fps_cap = ECO_FPS if p.eco else (p.fps_cap or self._base_fps)
        self.display.tenths = (
            False if p.eco else (self._base_tenths if p.tenths is None else p.tenths)
        )

    def _prefs_changed(self) -> None:
        self._apply_display_prefs()
        self.prefs_store.save()
        self._last_keys.clear()

    def set_timing(self, timing: Optional[dict[str, Optional[float]]]) -> None:
        """Default timer for new sessions (None = each sequence's own timing)."""
        self.prefs_data.timing = timing
        self.prefs_store.save()
        self._last_keys.pop("screen", None)

    def set_idle(self, on: bool) -> None:
        self.prefs_data.idle_screen = on
        self._prefs_changed()
        if not on:
            self._touch()

    def set_idle_delay(self, minutes: int) -> None:
        self.prefs_data.idle_delay_min = minutes
        self._prefs_changed()

    def cycle_idle_delay(self) -> None:
        i = IDLE_DELAYS_MIN.index(self.prefs_data.idle_delay_min)
        self.set_idle_delay(IDLE_DELAYS_MIN[(i + 1) % len(IDLE_DELAYS_MIN)])

    def cycle_idle_style(self) -> None:
        i = IDLE_STYLES.index(self.prefs_data.idle_style)
        self.prefs_data.idle_style = IDLE_STYLES[(i + 1) % len(IDLE_STYLES)]
        self._prefs_changed()

    def set_language(self, lang: str) -> None:
        self.t = Translator(lang)
        self.prefs_data.lang = lang
        self._prefs_changed()

    def set_tenths(self, on: bool) -> None:
        self.prefs_data.tenths = on
        self.prefs_data.eco = False
        self._prefs_changed()

    def set_fps(self, fps: int) -> None:
        self.prefs_data.fps_cap = fps
        self.prefs_data.eco = False
        self._prefs_changed()

    def set_eco(self, on: bool) -> None:
        self.prefs_data.eco = on
        self._prefs_changed()

    def dispatch(self, action: str) -> None:
        """Turn a UI action into a screen reaction, a local view change or a core command."""
        if self.profile == "audience" and action not in AUDIENCE_ACTIONS:
            return
        if action == "quit":
            if self.profile == "full":
                if not any(isinstance(sc, ConfirmScreen) for sc in self.screens):
                    confirm_quit(self)
            else:
                self.quit_app()
            return
        if action == "toggle_operator":
            if self.profile == "full" and not self.screens:
                self.show_operator = not self.show_operator
                self.hover = None
                self.build()
            return
        if action == "setup" or (action == "primary" and not self.screens and self._no_session()):
            if not self.screens:
                self.open_screen(SetupScreen(self))
            return
        if action == "menu":
            if self.screens:
                self.close_all_screens()
            else:
                self.open_screen(MenuScreen(self))
            return
        if self.screens:
            top = self.screens[-1]
            if action == "back":
                top.back()
                return
            if action == "primary":
                top.primary()
                return
            if action == "confirm":
                top.confirm()
                return
        if action == "confirm":
            return
        self.send_action(action)

    def _no_session(self) -> bool:
        snap = self.link.snapshot
        return (
            snap is not None
            and snap.mode is Mode.IDLE
            and self.make_context().core_state == CORE_OK
        )

    def send_action(self, action: str) -> None:
        """Send an operator action to the core (never handled locally)."""
        snap = self.link.snapshot
        if action in UNDOABLE and snap is not None and snap.mode in (Mode.RUNNING, Mode.WAITING):
            self._undo_round = snap.round_index
            self._undo_until_ns = self.clock.now_ns() + UNDO_WINDOW_NS
        elif action == "back":
            self._undo_until_ns = 0
        if action == "pause_toggle":
            if snap is None or snap.mode is not Mode.RUNNING:
                return
            action = "resume" if snap.paused else "pause"
        msg = self._command_message(action)
        if msg is not None and not self.link.send(msg):
            log.warning("no connection to the core; %r not sent", action)

    @staticmethod
    def _command_message(action: str) -> Optional[Message]:
        if action == "clear_emergency_continue":
            return cmd_msg("clear_emergency", {"mode": "continue"})
        if action == "clear_emergency_restart":
            return cmd_msg("clear_emergency", {"mode": "restart"})
        if action in _SIMPLE_ACTIONS:
            return cmd_msg(action)
        log.warning("unknown action %r", action)
        return None

    # ------------------------------------------------------------------ main loop

    def run(self) -> None:
        self.joymap.open_all()
        self.build()
        self.step(force=True)
        period = 1.0 / self.display.fps_cap if self.display.fps_cap else 0.0
        while self.running:
            try:
                self._frame(period)
            except Exception:
                # A UI bug must never leave the display dark (a restart takes seconds on a Pi).
                log.exception("UI frame failed; recovering")
                self._recover()

    def _frame(self, period: float) -> None:
        first = pygame.event.wait(self.next_wake_ms())
        events = [first, *pygame.event.get()]
        # A mouse reports hundreds of moves a second; only the last one in a batch matters.
        last_move = max(
            (i for i, e in enumerate(events) if e.type == pygame.MOUSEMOTION), default=-1
        )
        for i, ev in enumerate(events):
            if ev.type == pygame.MOUSEMOTION and i != last_move:
                continue
            self.handle_event(ev)
        changed = self.link.drain()
        self._maybe_autoconfigure(changed)
        snap = self.link.snapshot
        if changed and snap is not None and snap.emergency:
            self.close_all_screens()  # an emergency owns the whole display
        self.step()
        if period:  # FPS cap: never present faster than the cap
            spare = period - (self.clock.now_ns() - self._last_present_ns) / NS_PER_S
            if 0 < spare < period:
                time.sleep(spare)

    def _recover(self) -> None:
        """Drop open screens and redraw everything; if even that fails, back off briefly."""
        try:
            self.screens.clear()
            self.hover = None
            self.build()
            self.step(force=True)
        except Exception:
            log.exception("UI recovery failed")
            time.sleep(0.2)

    def _maybe_autoconfigure(self, changed: bool) -> None:
        """Development convenience until the setup wizard exists (M6)."""
        snap = self.link.snapshot
        if changed and self._autoconfigure and snap is not None and snap.mode is Mode.IDLE:
            self.link.send(cmd_msg("configure", self._autoconfigure))
            self._autoconfigure = None


_UNSET = object()
_ACTIVITY_EVENTS = (
    pygame.KEYDOWN,
    pygame.MOUSEBUTTONDOWN,
    pygame.MOUSEMOTION,
    pygame.JOYBUTTONDOWN,
)
_SIMPLE_ACTIONS = frozenset(
    {
        "primary",
        "pause",
        "resume",
        "stop_end",
        "next",
        "back",
        "emergency",
        "reset",
        "sound_test",
        "apply_network",
    }
)
_RESIZE_EVENTS = tuple(
    getattr(pygame, name)
    for name in ("WINDOWRESIZED", "WINDOWSIZECHANGED", "WINDOWEXPOSED", "WINDOWRESTORED")
    if hasattr(pygame, name)
)

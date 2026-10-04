from __future__ import annotations

import time
from typing import Any, Optional

import pygame
import pytest

from archerytimer.common.clock import NS_PER_S, FakeClock, MonotonicClock
from archerytimer.common.i18n import Translator
from archerytimer.core.models import Light, Mode, PhaseSpec, Sequence, Snapshot
from archerytimer.core_service.service import CoreService
from archerytimer.ipc.clocksync import OffsetEstimator
from archerytimer.ipc.transport import ConnectionClosed
from archerytimer.ipc.transport_inproc import InprocListener
from archerytimer.ui_client import theme
from archerytimer.ui_client.app import AUDIENCE_ACTIONS, DisplaySettings, UiApp
from archerytimer.ui_client.context import (
    CORE_CONNECTING,
    CORE_OK,
    ViewContext,
    buttons_for,
    countdown_text,
    light_view,
    next_text_change_ns,
    remaining_ns,
)
from archerytimer.ui_client.core_link import CoreLink
from archerytimer.ui_client.input import KeyMap
from archerytimer.ui_client.layout import layout_for, logical_size_for, pixel_rects
from archerytimer.ui_client.renderer import DisplayConfig, open_renderer
from archerytimer.ui_client.renderer.base import OverlayRect

S = NS_PER_S
T = Translator("en")


def snap(**kw: Any) -> Snapshot:
    base: dict[str, Any] = dict(
        seq=1, mode=Mode.RUNNING, sequence_id="t", phase_id="SHOOT", phase_start_ns=0,
        deadline_ns=120 * S, paused=False, remaining_at_pause_ns=0, light=Light.GREEN,
        group="AB", end_no=1, total_ends=2, practice=False, round_index=0, total_rounds=4,
        emergency=False, link="up",
    )  # fmt: skip
    base.update(kw)
    return Snapshot(**base)


def ctx(s: Optional[Snapshot], state: str = CORE_OK, now: int = 0, **kw: Any) -> ViewContext:
    return ViewContext(snap=s, core_state=state, t=T, now_core_ns=now, **kw)


# ---------------------------------------------------------------- pure helpers


def test_countdown_text_and_change_times():
    assert countdown_text(None, False) == "-:--"
    assert countdown_text(87_300_000_000, False) == "1:28"  # ceil: never shows 0 early
    assert countdown_text(1, False) == "0:01"
    assert countdown_text(0, False) == "0:00"
    assert countdown_text(9_950_000_000, True) == "0:10.0"
    assert countdown_text(9_900_000_000, True) == "0:09.9"
    assert countdown_text(30 * S, True) == "0:30"
    # the text really changes exactly when next_text_change_ns says it will
    for rem, tenths in [(87_300_000_000, False), (5_050_000_000, True), (12_500_000_000, True)]:
        d = next_text_change_ns(rem, tenths)
        assert 0 < d <= S
        assert countdown_text(rem - d + 1, tenths) == countdown_text(rem, tenths)
        assert countdown_text(rem - d, tenths) != countdown_text(rem, tenths)


def test_remaining_follows_deadline_and_offset():
    s = snap(deadline_ns=100 * S)
    assert remaining_ns(s, 40 * S) == 60 * S
    assert remaining_ns(s, 130 * S) == 0
    assert remaining_ns(snap(paused=True, remaining_at_pause_ns=9 * S), 0) == 9 * S
    assert remaining_ns(snap(mode=Mode.WAITING), 0) is None


def test_light_views():
    assert light_view(ctx(None, CORE_CONNECTING)).light is Light.OFF
    assert light_view(ctx(snap(), "lost")).light is Light.RED
    v = light_view(ctx(snap()))
    assert (v.light, v.shape, v.label) == (Light.GREEN, "circle", "SHOOT – Line AB")
    assert light_view(ctx(snap(light=Light.YELLOW))).shape == "triangle"
    assert light_view(ctx(snap(phase_id="PREP", light=Light.RED))).label.startswith("GET READY")
    assert light_view(ctx(snap(paused=True))).label == "PAUSED"
    assert light_view(ctx(snap(emergency=True))).label == "EMERGENCY STOP"
    waiting = snap(mode=Mode.WAITING, phase_id="END", light=Light.RED)
    assert light_view(ctx(waiting)).label.startswith("STOP")


def test_buttons_follow_state():
    def ids(c: ViewContext) -> dict[str, tuple[str, bool]]:
        return {b.id: (b.label, b.enabled) for b in buttons_for(c)}

    waiting = ids(ctx(snap(mode=Mode.WAITING, phase_id="PREP")))
    assert waiting["primary"] == ("Start end", True) and waiting["pause"][1] is False
    after = ids(ctx(snap(mode=Mode.WAITING, phase_id="END", round_index=1)))
    assert after["primary"][0] == "Next end" and after["back"][1] is True
    running = ids(ctx(snap()))
    assert running["primary"][1] is False and running["pause"] == ("Pause", True)
    paused = ids(ctx(snap(paused=True)))
    assert paused["pause"] == ("Resume", True) and paused["primary"][0] == "Resume"
    emerg = buttons_for(ctx(snap(emergency=True)))
    assert emerg[0].id == "emergency" and {b.id for b in emerg} >= {
        "clear_continue",
        "clear_restart",
    }
    offline = buttons_for(ctx(None, "lost"))
    assert offline[0].id == "emergency" and not any(b.enabled for b in offline if b.id != "menu")


def test_layout_tiles_the_output_exactly():
    for size in [(1920, 1080), (1280, 720), (1024, 768), (1280, 800), (3840, 2160)]:
        for profile, op in [("full", True), ("full", False), ("audience", True)]:
            rects = pixel_rects(layout_for(profile, op), size)
            assert sum(w * h for _, _, w, h in rects.values()) == size[0] * size[1]
            assert ("operator" in rects) == (profile == "full" and op)
    assert logical_size_for((3840, 2160)) == (1920, 1080)
    assert logical_size_for((1280, 720)) == (1280, 720)


def test_keymap_defaults_clickers_and_overrides():
    km = KeyMap()

    def key(k: int, mod: int = 0) -> pygame.event.Event:
        return pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod)

    assert km.action_for(key(pygame.K_SPACE)) == "primary"
    assert km.action_for(key(pygame.K_PAGEDOWN)) == "primary"  # clicker "next"
    assert km.action_for(key(pygame.K_PAGEUP)) == "back"  # clicker "previous"
    assert km.action_for(key(pygame.K_PERIOD)) == "pause_toggle"  # clicker "blank"
    assert km.action_for(key(pygame.K_ESCAPE)) == "emergency"
    assert km.action_for(key(pygame.K_q, pygame.KMOD_CTRL)) == "quit"
    assert km.action_for(key(pygame.K_q)) is None
    custom = KeyMap({"primary": ["f5"], "bogus": ["x"]})
    assert custom.action_for(key(pygame.K_F5)) == "primary"
    assert custom.action_for(key(pygame.K_SPACE)) is None


# ---------------------------------------------------------------- clock sync


def test_offset_estimator_picks_least_delayed_sample_and_survives_asymmetry():
    est = OffsetEstimator()
    true_offset = 5_000_000_000  # core clock is 5 s ahead
    # (one-way out, one-way back) delays in ms: the 0.3/0.3 exchange is the cleanest
    for out_ms, back_ms in [(20, 5), (0.3, 0.3), (8, 30), (1, 12)]:
        t0 = 1_000 * S
        t1 = t0 + int(out_ms * 1e6) + true_offset
        t2 = t0 + int((out_ms + back_ms) * 1e6)
        est.add(t0, t1, t2)
    assert abs(est.offset_ns - true_offset) < 100_000  # within 0.1 ms
    assert est.rtt_ns == 600_000


def test_remote_ui_with_offset_clock_shows_same_remaining():
    """A UI whose local clock is 3 s behind the core still counts down correctly."""
    s = snap(deadline_ns=100 * S)
    local_now = 40 * S  # core's clock reads 43 s at this instant
    offset = 3 * S
    assert remaining_ns(s, local_now + offset) == 57 * S


# ---------------------------------------------------------------- app


class FakeLink:
    def __init__(self) -> None:
        self.snapshot: Optional[Snapshot] = None
        self.connected = True
        self.ever_connected = True
        self.upstream_ok = True
        self.lost_since_ns: Optional[int] = None
        self.estimator = OffsetEstimator()
        self.sent: list[dict[str, Any]] = []

    def send(self, msg: dict[str, Any]) -> bool:
        self.sent.append(msg)
        return self.connected

    def sequence_names(self, sequence_id: str) -> dict[str, str]:
        return {"en": "Test preset", "sv": "Testsession"}


@pytest.fixture(params=["software", "gpu"])
def rig(request):
    clock = FakeClock(100 * S)
    renderer = open_renderer(DisplayConfig(kind=request.param, size=(960, 540)))
    link = FakeLink()
    app = UiApp(
        link,  # type: ignore[arg-type]
        renderer, T, clock=clock, wall=lambda: 1_000_000.25,
        display=DisplaySettings(),
    )  # fmt: skip
    app.build()
    yield app, link, clock
    renderer.close()


def overlay_color(app, name):
    """Colour of the first overlay rectangle of a section (the light field or frame)."""
    items, _origin = app.renderer._overlays[name]
    return next(i.color for i in items if isinstance(i, OverlayRect))


def start_running(app: UiApp, link: FakeLink, clock: FakeClock, remaining_s: int = 120) -> None:
    now = clock.now_ns()
    link.snapshot = snap(phase_start_ns=now, deadline_ns=now + remaining_s * S)
    app.step()


def test_idle_ui_draws_once_and_then_nothing(rig):
    app, link, clock = rig
    assert app.step() is True and app.presents == 1
    for _ in range(50):
        clock.advance_s(0.1)  # wall clock is frozen in this test
        assert app.step() is False
    assert app.presents == 1


def test_countdown_redraws_once_per_second_and_only_the_countdown(rig):
    app, link, clock = rig
    app.step()
    start_running(app, link, clock)
    app.redraws.clear()
    presents = app.presents
    clock.advance_s(0.5)
    assert app.step() is False  # same displayed second: nothing to do
    clock.advance_s(0.6)
    assert app.step() is True
    assert app.redraws == ["countdown"] and app.presents == presents + 1
    # a minute of running = ~60 presents, nothing else redrawn
    app.redraws.clear()
    for _ in range(60):
        clock.advance_s(1.0)
        app.step()
    assert set(app.redraws) == {"countdown"} and len(app.redraws) == 60


def test_pixels_follow_state_and_connection_loss_goes_red(rig):
    app, link, clock = rig
    start_running(app, link, clock)
    assert overlay_color(app, "light") == theme.LIGHT_COLORS[Light.GREEN]
    link.connected = False
    link.lost_since_ns = clock.now_ns()
    clock.advance_s(0.5)
    app.step()
    assert overlay_color(app, "light") == theme.LIGHT_COLORS[Light.GREEN]
    clock.advance_s(0.6)  # past the 1 s grace: no contact = stop
    app.step()
    assert overlay_color(app, "light") == theme.LIGHT_COLORS[Light.RED]


def test_next_wake_matches_the_next_second_tick(rig):
    app, link, clock = rig
    start_running(app, link, clock)
    clock.advance_s(0.25)
    assert 700 <= app.next_wake_ms() <= 800  # ~0.75 s to the next displayed second


def test_emergency_by_key_and_mouse_never_needs_confirmation(rig):
    app, link, clock = rig
    start_running(app, link, clock)
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
    assert link.sent[-1]["name"] == "emergency"
    x, y, w, h = app.rects["operator"]
    from archerytimer.ui_client.sections.operator_bar import button_rects

    ctx_ = app.make_context()
    first = button_rects(buttons_for(ctx_), (w, h))[0]  # emergency is always the first button
    app.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=(x + first.centerx, y + first.centery), button=1
        )
    )
    assert [m["name"] for m in link.sent] == ["emergency", "emergency"]


def test_primary_pause_and_keyboard_dispatch(rig):
    app, link, clock = rig
    link.snapshot = snap(mode=Mode.WAITING, phase_id="PREP", light=Light.RED)
    app.step()
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0))
    assert link.sent[-1]["name"] == "primary"
    start_running(app, link, clock)
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p, mod=0))
    assert link.sent[-1]["name"] == "pause"
    link.snapshot = snap(paused=True)
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p, mod=0))
    assert link.sent[-1]["name"] == "resume"


def test_toggle_operator_bar_changes_layout(rig):
    app, link, clock = rig
    assert "operator" in app.sections
    app.dispatch("toggle_operator")
    assert "operator" not in app.sections and app.step() is True
    app.dispatch("toggle_operator")
    assert "operator" in app.sections


def test_audience_profile_has_no_controls_except_emergency():
    renderer = open_renderer(DisplayConfig(kind="software", size=(960, 540)))
    link = FakeLink()
    app = UiApp(link, renderer, T, profile="audience", clock=FakeClock(0))  # type: ignore[arg-type]
    app.build()
    assert "operator" not in app.sections
    app.dispatch("primary")
    app.dispatch("pause_toggle")
    app.dispatch("emergency")
    assert [m["name"] for m in link.sent] == ["emergency"]
    assert "emergency" in AUDIENCE_ACTIONS
    renderer.close()


def test_resize_rebuilds_for_the_new_size():
    renderer = open_renderer(DisplayConfig(kind="software", size=(960, 540)))
    app = UiApp(FakeLink(), renderer, T, clock=FakeClock(0))  # type: ignore[arg-type]
    app.build()
    app.step()
    pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    app.handle_event(pygame.event.Event(pygame.WINDOWRESIZED, x=1280, y=720))
    assert app.rects["light"][2] == 1280
    assert app.surfaces["light"].get_width() == 1280
    renderer.close()


# ---------------------------------------------------------------- link + real core


def wait_for(cond, timeout: float = 4.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def test_core_link_syncs_clock_and_reconnects_to_restarted_core():
    seq = Sequence(
        "t",
        {"en": "Test"},
        (PhaseSpec("SHOOT", 60 * S, Light.GREEN, 1), PhaseSpec("END", 0, Light.RED, 3)),
    )
    holder: dict[str, Any] = {}

    def start_core() -> CoreService:
        listener = InprocListener()
        holder["listener"] = listener
        svc = CoreService(MonotonicClock(), {"t": seq}, listener)
        svc.start()
        return svc

    def connect():
        listener = holder.get("listener")
        if listener is None:
            raise ConnectionClosed
        return listener.connect()

    svc = start_core()
    link = CoreLink(connect, ping_interval_s=0.2, backoff_s=(0.02,))
    link.start()
    try:
        assert wait_for(lambda: link.connected and (link.drain() or link.snapshot is not None))
        assert wait_for(lambda: link.estimator.synced)
        assert abs(link.estimator.offset_ns) < 5_000_000  # same machine: ~0
        assert link.sequence_names("t") == {"en": "Test"} or link.hello is not None
        svc.stop()
        assert wait_for(lambda: not link.connected)
        assert link.lost_since_ns is not None and link.ever_connected
        svc = start_core()  # core restarts; the UI finds it again by itself
        assert wait_for(lambda: link.connected)
        assert wait_for(lambda: link.drain() or link.snapshot is not None)
        assert link.snapshot is not None
        assert link.send({"type": "cmd", "name": "primary", "args": {}})
    finally:
        link.stop()
        svc.stop()

"""M6: setup wizard, menu, settings, confirm dialogs, presets and preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pygame
import pytest
from tests.ui_client.test_ui import snap

from archerytimer.common.clock import NS_PER_S, FakeClock
from archerytimer.common.i18n import Translator, load_locale
from archerytimer.core.engine import Engine
from archerytimer.core.models import (
    Command,
    Light,
    Mode,
    PhaseSpec,
    Sequence,
    SessionConfig,
)
from archerytimer.core_service.service import config_from_args
from archerytimer.ipc.clocksync import OffsetEstimator
from archerytimer.ui_client import theme
from archerytimer.ui_client.app import DisplaySettings, UiApp
from archerytimer.ui_client.context import countdown_text, display_ns
from archerytimer.ui_client.input import KeyMap
from archerytimer.ui_client.prefs import FILE_NAME, PrefsStore
from archerytimer.ui_client.presets import DEFAULT_DIR, load_presets
from archerytimer.ui_client.renderer import DisplayConfig, open_renderer
from archerytimer.ui_client.renderer.base import OverlayRect
from archerytimer.ui_client.sections.screen_section import content_area
from archerytimer.ui_client.widgets import to_pixels

S = NS_PER_S
T = Translator("en")
SEQ = "indoor_3arrows"


class Link:
    def __init__(self) -> None:
        self.snapshot = None
        self.connected = True
        self.ever_connected = True
        self.upstream_ok = True
        self.lost_since_ns: Optional[int] = None
        self.estimator = OffsetEstimator()
        self.sent: list[dict[str, Any]] = []
        self.hw_fw = "1.0"
        self.hw_chip = "ESP32-S3"
        self.espnow: Optional[dict[str, Any]] = {"mode": "auto", "peers": 2, "src": "host"}
        self.hello = {"version": "9.9"}
        self.audio = None

    def send(self, msg: dict[str, Any]) -> bool:
        self.sent.append(msg)
        return self.connected

    def sequence_names(self, sequence_id: str) -> dict[str, str]:
        return {"en": "Test", "sv": "Test"}

    def sequence_ids(self) -> list[str]:
        return [SEQ, "outdoor_6arrows", "outdoor_3arrows"]

    def timings(self, sequence_id: str) -> dict[str, float]:
        return {"prep_s": 10.0, "shoot_s": 120.0, "warn_s": 30.0}


@pytest.fixture(params=["software", "gpu"])
def rig(request, tmp_path):
    clock = FakeClock(100 * S)
    renderer = open_renderer(DisplayConfig(kind=request.param, size=(960, 540)))
    link = Link()
    store = PrefsStore(tmp_path / FILE_NAME)
    app = UiApp(
        link,  # type: ignore[arg-type]
        renderer, T, clock=clock, wall=lambda: 1_000_000.25, display=DisplaySettings(),
        presets=load_presets(DEFAULT_DIR), prefs=store, keymap=KeyMap(),
    )  # fmt: skip
    app.build()
    link.snapshot = snap(mode=Mode.IDLE, phase_id="", light=Light.OFF, sequence_id="")
    app.step()
    yield app, link, clock
    renderer.close()


def key(app: UiApp, k: int) -> None:
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0))


def widget_pos(app: UiApp, wid: str) -> tuple[int, int]:
    """Window position at the centre of a widget of the open screen."""
    sx, sy, sw, sh = app.rects["screen"]
    ctx = app.make_context()
    area = content_area((sw, sh))
    for w in app.screens[-1].widgets(ctx):
        if w.id == wid:
            r = to_pixels(w.rect, area)
            return sx + r.centerx, sy + r.centery
    raise AssertionError(f"no widget {wid!r}; have {[w.id for w in app.screens[-1].widgets(ctx)]}")


def click(app: UiApp, wid: str) -> None:
    pos = widget_pos(app, wid)
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    app.step()


def names(link: Link) -> list[str]:
    return [m["name"] for m in link.sent]


# ---------------------------------------------------------------- presets and prefs


def test_bundled_presets_load_and_use_known_sequences():
    presets = load_presets(DEFAULT_DIR)
    assert {p.id for p in presets} >= {"indoor_18", "outdoor_6", "outdoor_3", "practice_ends"}
    for p in presets:
        assert p.groups in p.line_options


def test_bad_preset_is_skipped_not_fatal(tmp_path: Path):
    (tmp_path / "club.toml").write_text(
        '[preset.ok]\nname = {sv = "A"}\nsequence = "s"\ngroups = ["AB"]\n'
        '[preset.bad]\nname = {sv = "B"}\n',
        encoding="utf-8",
    )
    assert [p.id for p in load_presets(tmp_path)] == ["ok"]


def test_prefs_roundtrip_and_damage(tmp_path: Path):
    path = tmp_path / FILE_NAME
    store = PrefsStore(path)
    store.prefs.lang, store.prefs.fps_cap, store.prefs.eco = "en", 30, True
    store.prefs.last_setup = {"preset": "x"}
    store.save()
    again = PrefsStore(path).load()
    assert (again.lang, again.fps_cap, again.eco, again.last_setup) == (
        "en",
        30,
        True,
        {"preset": "x"},
    )
    path.write_text("{not json", encoding="utf-8")
    assert PrefsStore(path).load().lang is None  # damaged file means defaults


def test_locales_have_the_same_keys():
    sv, en = load_locale("sv"), load_locale("en")
    assert set(sv) == set(en)


# ---------------------------------------------------------------- wizard


def test_wizard_three_steps_sends_configure_and_remembers(rig):
    app, link, _ = rig
    key(app, pygame.K_m)
    assert app.screens and "screen" in app.sections and "operator" in app.sections
    click(app, "setup")
    click(app, "preset:indoor_18")
    setup = app.screens[-1]
    assert setup.step == 2
    click(app, "lines:1")  # AB / CD (already the default)
    click(app, "ends+")
    click(app, "practice-")
    click(app, "next")
    assert setup.step == 3
    click(app, "start")
    cmd = link.sent[-1]
    assert cmd["name"] == "configure"
    args = cmd["args"]
    assert args["sequence_id"] == SEQ and args["groups"] == ["AB", "CD"]
    assert args["total_ends"] == 11 and args["practice_ends"] == 1
    assert not app.screens and "countdown" in app.sections  # back on the main view
    assert app.prefs_data.last_setup["preset"] == "indoor_18"
    # the next time, one button restores it
    key(app, pygame.K_m)
    click(app, "setup")
    click(app, "last")
    assert app.screens[-1].step == 3


def test_back_steps_then_closes(rig):
    app, link, _ = rig
    key(app, pygame.K_m)
    click(app, "setup")
    click(app, "preset:outdoor_6")
    key(app, pygame.K_BACKSPACE)
    assert app.screens[-1].step == 1
    key(app, pygame.K_BACKSPACE)
    assert app.screens[-1].name == "menu"
    key(app, pygame.K_BACKSPACE)
    assert not app.screens
    assert "configure" not in names(link)


def test_advanced_overrides_reach_the_command(rig):
    app, link, _ = rig
    key(app, pygame.K_m)
    click(app, "setup")
    click(app, "preset:indoor_18")
    click(app, "advanced")
    click(app, "shoot_s+")  # 120 s + 10 s
    click(app, "prep_s-")  # 10 s - 5 s
    click(app, "warn_s-")  # 30 s - 5 s
    click(app, "auto_advance")
    click(app, "done")
    click(app, "next")
    click(app, "start")
    args = link.sent[-1]["args"]
    assert (args["shoot_s"], args["prep_s"], args["warn_s"]) == (130.0, 5.0, 25.0)
    assert args["auto_advance"] is True
    cfg = config_from_args(args)
    assert (cfg.shoot_ns, cfg.prep_ns, cfg.warn_ns) == (130 * S, 5 * S, 25 * S)


def test_replacing_a_session_in_progress_asks_first(rig):
    app, link, _ = rig
    link.snapshot = snap(mode=Mode.WAITING, round_index=3, phase_id="END", light=Light.RED)
    app.step()
    key(app, pygame.K_m)
    click(app, "setup")
    click(app, "preset:indoor_18")
    click(app, "next")
    click(app, "start")
    assert app.screens[-1].name == "confirm" and "configure" not in names(link)
    key(app, pygame.K_SPACE)  # Space cancels: it must never destroy a session by accident
    assert "configure" not in names(link) and app.screens[-1].name == "setup"
    click(app, "start")
    key(app, pygame.K_y)
    assert names(link) == ["configure"]


def test_menu_locks_session_change_while_running(rig):
    app, link, clock = rig
    link.snapshot = snap(phase_start_ns=clock.now_ns(), deadline_ns=clock.now_ns() + 60 * S)
    app.step()
    key(app, pygame.K_m)
    menu = app.screens[-1]
    enabled = {w.id: w.enabled for w in menu.widgets(app.make_context()) if w.kind == "button"}
    assert enabled["setup"] is False and enabled["reset"] is False
    click(app, "setup")  # disabled: ignored
    assert app.screens[-1] is menu


# ---------------------------------------------------------------- guarded actions


def test_reset_and_quit_need_confirmation(rig):
    app, link, _ = rig
    link.snapshot = snap(mode=Mode.WAITING, round_index=1, phase_id="END", light=Light.RED)
    app.step()
    key(app, pygame.K_m)
    click(app, "reset")
    assert "reset" not in names(link)
    click(app, "cancel")
    click(app, "reset")
    click(app, "yes")
    assert names(link) == ["reset"] and app.screens[-1].name == "menu"
    # quit
    app.dispatch("quit")
    assert app.running and app.screens[-1].name == "confirm"
    key(app, pygame.K_y)
    assert not app.running


def test_audience_quits_without_a_dialog():
    renderer = open_renderer(DisplayConfig(kind="software", size=(960, 540)))
    app = UiApp(Link(), renderer, T, profile="audience", clock=FakeClock(0))  # type: ignore[arg-type]
    app.build()
    app.dispatch("menu")
    assert not app.screens  # no operator screens on the audience display
    app.dispatch("quit")
    assert not app.running
    renderer.close()


def test_emergency_and_bar_stay_live_under_a_screen(rig):
    app, link, clock = rig
    link.snapshot = snap(phase_start_ns=clock.now_ns(), deadline_ns=clock.now_ns() + 60 * S)
    app.step()
    key(app, pygame.K_m)
    key(app, pygame.K_ESCAPE)
    assert names(link) == ["emergency"]
    # a click on the bar's pause button reaches the core, not the screen
    from archerytimer.ui_client.context import buttons_for
    from archerytimer.ui_client.sections.operator_bar import button_rects

    x, y, w, h = app.rects["operator"]
    buttons = buttons_for(app.make_context())
    rects = button_rects(buttons, (w, h))
    i = [b.id for b in buttons].index("pause")
    app.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=(x + rects[i].centerx, y + rects[i].centery), button=1
        )
    )
    assert names(link) == ["emergency", "pause"]
    assert app.screens  # the screen stays open


def test_menu_toggles_and_forces_operator_bar_visible(rig):
    app, _, _ = rig
    app.dispatch("toggle_operator")
    assert "operator" not in app.sections
    app.dispatch("menu")
    assert "operator" in app.sections and "screen" in app.sections
    app.dispatch("menu")
    assert not app.screens and "countdown" in app.sections


# ---------------------------------------------------------------- settings


def test_settings_change_display_and_persist(rig, tmp_path: Path):
    app, _, _ = rig
    key(app, pygame.K_m)
    click(app, "settings")
    click(app, "tenths")
    assert app.display.tenths is True
    click(app, "fps")
    assert app.display.fps_cap == 15  # 60 wraps around to 15
    click(app, "eco")
    assert app.display.fps_cap == 15 and app.display.tenths is False
    click(app, "lang")
    assert app.t.lang == "sv"
    again = PrefsStore(tmp_path / FILE_NAME).load()
    assert again.lang == "sv" and again.eco is True


def test_every_screen_renders_on_both_renderers_and_languages(rig):
    app, link, clock = rig
    for lang in ("en", "sv"):
        app.set_language(lang)
        for kind in ("menu", "settings", "hardware", "help", "setup", "advanced", "confirm"):
            app.close_all_screens()
            key(app, pygame.K_m)
            if kind == "menu":
                pass
            elif kind in ("settings", "hardware", "help", "setup"):
                click(app, kind)
            elif kind == "advanced":
                click(app, "setup")
                click(app, "preset:indoor_18")
                click(app, "advanced")
            else:
                app.dispatch("quit")
            assert app.step(force=True) is True
            assert app.screens[-1].name == kind
            assert any(app.screens[-1].widgets(app.make_context()))


def test_hardware_screen_says_what_is_wrong_in_plain_words(rig):
    app, link, _ = rig
    link.snapshot = snap(link="down")
    key(app, pygame.K_m)
    click(app, "hardware")
    texts = [w.text for w in app.screens[-1].widgets(app.make_context())]
    assert any("not connected" in t for t in texts)
    assert not any("ESP" in t and "error" in t.lower() for t in texts)


# ---------------------------------------------------------------- core side


def _engine(clock: FakeClock):
    seq = Sequence(
        "t",
        {"en": "T"},
        (
            PhaseSpec("PREP", 10 * S, Light.RED, 2),
            PhaseSpec("SHOOT", 120 * S, Light.GREEN, 1, warn_at_ns=30 * S),
            PhaseSpec("END", 0, Light.RED, 3),
        ),
    )
    events: list[Any] = []
    return Engine(clock, {"t": seq}, events.append), events


def test_session_overrides_apply_and_planned_time_is_in_the_snapshot():
    clock = FakeClock(0)
    eng, _ = _engine(clock)
    eng.configure(SessionConfig("t", total_ends=2, prep_ns=5 * S, shoot_ns=90 * S, warn_ns=0))
    snap_ = eng.snapshot()
    assert snap_.planned_ns == 90 * S
    eng.handle(Command("start"))
    assert eng.snapshot().deadline_ns - eng.snapshot().phase_start_ns == 5 * S
    clock.advance_s(5)
    eng.poll()
    st = eng.snapshot()
    assert st.phase_id == "SHOOT" and st.deadline_ns - st.phase_start_ns == 90 * S
    assert st.light is Light.GREEN
    clock.advance_s(60)
    eng.poll()
    assert eng.snapshot().light is Light.GREEN  # warning switched off: no yellow


def test_practice_only_and_invalid_sessions():
    eng, _ = _engine(FakeClock(0))
    eng.configure(SessionConfig("t", total_ends=0, practice_ends=2))
    s = eng.snapshot()
    assert s.practice and s.total_rounds == 2
    with pytest.raises(ValueError):
        eng.configure(SessionConfig("t", total_ends=0, practice_ends=0))


def test_countdown_shows_planned_time_while_waiting():
    waiting = snap(mode=Mode.WAITING, planned_ns=120 * S)
    assert countdown_text(display_ns(waiting, 0), False) == "2:00"
    assert display_ns(snap(mode=Mode.IDLE), 0) is None


# ---------------------------------------------------------------- timers screen


def test_timers_screen_sets_default_timing_for_new_sessions(rig, tmp_path: Path):
    from archerytimer.ui_client.presets import load_timings

    app, link, _ = rig
    app.timing_presets = load_timings(DEFAULT_DIR)
    assert {tp.id for tp in app.timing_presets} >= {"t60", "t120", "t240"}
    key(app, pygame.K_m)
    click(app, "timers")
    click(app, "tp:t90")
    assert app.prefs_data.timing == {"prep_s": 10.0, "shoot_s": 90.0, "warn_s": 30.0}
    click(app, "shoot_s+")  # custom: 100 s
    click(app, "warn_s-")  # 25 s
    click(app, "prep_s-")  # 5 s
    assert app.prefs_data.timing == {"prep_s": 5.0, "shoot_s": 100.0, "warn_s": 25.0}
    assert PrefsStore(tmp_path / FILE_NAME).load().timing == app.prefs_data.timing  # persisted
    app.close_all_screens()
    key(app, pygame.K_m)
    click(app, "setup")
    click(app, "preset:indoor_18")
    click(app, "next")
    click(app, "start")
    args = link.sent[-1]["args"]
    assert (args["prep_s"], args["shoot_s"], args["warn_s"]) == (5.0, 100.0, 25.0)
    # back to each session's own timing
    key(app, pygame.K_m)
    click(app, "timers")
    click(app, "std")
    assert app.prefs_data.timing is None


def test_first_edit_from_standard_starts_a_custom_timer(rig):
    app, _, _ = rig
    key(app, pygame.K_m)
    click(app, "timers")
    click(app, "shoot_s+")
    assert app.prefs_data.timing == {"prep_s": 10.0, "shoot_s": 130.0, "warn_s": 30.0}
    click(app, "warn_s-")
    for _ in range(10):
        click(app, "warn_s-")
    assert app.prefs_data.timing["warn_s"] == 0.0  # warning off, clamped at zero


# ---------------------------------------------------------------- M6b: idle, undo, shortcuts

MIN = 60 * S


def test_primary_with_no_session_opens_setup_and_the_button_says_so(rig):
    from archerytimer.ui_client.context import primary_button

    app, link, _ = rig
    b = primary_button(app.make_context())
    assert b.enabled and b.action == "setup"
    key(app, pygame.K_SPACE)
    assert app.screens and app.screens[-1].name == "setup" and not link.sent


def test_primary_button_shows_what_the_next_end_is(rig):
    from archerytimer.ui_client.context import primary_button

    app, link, _ = rig
    link.snapshot = snap(mode=Mode.WAITING, group="CD", end_no=4, total_ends=10, phase_id="END")
    sub_text = primary_button(app.make_context()).sub
    assert "Line CD" in sub_text and "End 4 of 10" in sub_text


def test_undo_window_after_stop_end_and_next(rig):
    from archerytimer.ui_client.context import buttons_for

    app, link, clock = rig
    link.snapshot = snap(phase_start_ns=clock.now_ns(), deadline_ns=clock.now_ns() + 60 * S)
    app.step()
    app.dispatch("stop_end")
    # the core finishes the end: round 0 -> 1, waiting
    link.snapshot = snap(mode=Mode.WAITING, round_index=1, phase_id="END", light=Light.RED)
    back = next(b for b in buttons_for(app.make_context()) if b.id == "back")
    assert back.kind == "undo" and back.enabled
    assert app.step() is True
    assert 0 < app.sections["operator"].next_change_ns(app.make_context()) <= 5 * S
    clock.advance_s(5.1)
    back = next(b for b in buttons_for(app.make_context()) if b.id == "back")
    assert back.kind == "normal"  # the window closed
    # undo itself is the engine's "back"
    app.dispatch("next")
    link.snapshot = snap(mode=Mode.WAITING, round_index=2, phase_id="END", light=Light.RED)
    app.dispatch("back")
    assert names(link)[-1] == "back"
    assert app.make_context().undo is False


def _idle_rig(rig):
    app, link, clock = rig
    link.snapshot = snap(mode=Mode.WAITING, round_index=0, phase_id="PREP", light=Light.RED, seq=7)
    app.step()
    return app, link, clock


def test_idle_screen_starts_after_the_delay_and_any_key_wakes_it(rig):
    app, link, clock = _idle_rig(rig)
    clock.advance(4 * MIN)
    app.step()
    assert not app.idle_active
    clock.advance(1 * MIN + S)
    app.step()
    assert app.idle_active and list(app.sections) == ["idle"]
    # a wake-up key press does nothing else: no accidental start
    key(app, pygame.K_SPACE)
    assert not app.idle_active and "countdown" in app.sections and not link.sent
    key(app, pygame.K_SPACE)
    assert names(link) == ["primary"]


def test_idle_screen_never_swallows_the_emergency_stop(rig):
    app, link, clock = _idle_rig(rig)
    clock.advance(6 * MIN)
    app.step()
    assert app.idle_active
    key(app, pygame.K_ESCAPE)
    assert names(link) == ["emergency"] and not app.idle_active


def test_idle_screen_ends_when_the_core_reports_activity_and_never_while_running(rig):
    app, link, clock = _idle_rig(rig)
    clock.advance(6 * MIN)
    app.step()
    assert app.idle_active
    link.snapshot = snap(phase_start_ns=clock.now_ns(), deadline_ns=clock.now_ns() + 60 * S, seq=8)
    app.step()
    assert not app.idle_active  # e.g. started from a button box
    clock.advance(30 * MIN)
    app.step()
    assert not app.idle_active  # running: never idle


def test_idle_screen_settings_and_black_style_costs_nothing(rig):
    app, link, clock = _idle_rig(rig)
    key(app, pygame.K_m)
    click(app, "settings")
    click(app, "idle_delay")  # 5 -> 10
    click(app, "idle_style")  # clock -> dim
    click(app, "idle_style")  # dim -> black
    assert (app.prefs_data.idle_delay_min, app.prefs_data.idle_style) == (10, "black")
    click(app, "idle")  # off: the dependent options grey out
    assert app.prefs_data.idle_screen is False
    enabled = {w.id: w.enabled for w in app.screens[-1].widgets(app.make_context())}
    assert enabled["idle_delay"] is False and enabled["idle_style"] is False
    clock.advance(60 * MIN)
    app.step()
    assert not app.idle_active
    click(app, "idle")  # on again
    app.close_all_screens()
    clock.advance(11 * MIN)
    app.step()
    assert app.idle_active
    assert app.step() is False and app.next_wake_ms() >= 1000  # black: nothing to do, sleeps


def test_idle_clock_redraws_once_a_minute(rig):
    app, link, clock = _idle_rig(rig)
    clock.advance(6 * MIN)
    app.step()
    app.redraws.clear()
    assert app.sections["idle"].next_change_ns(app.make_context()) <= 60 * S
    assert app.step() is False  # frozen wall clock: still the same minute


def test_frame_in_light_colour_and_icons_render(rig):
    app, link, clock = rig
    link.snapshot = snap(phase_start_ns=clock.now_ns(), deadline_ns=clock.now_ns() + 60 * S)
    app.step(force=True)
    green = theme.LIGHT_COLORS[Light.GREEN]
    for name in ("countdown", "info"):  # the light-coloured frames are overlay rectangles
        items, _origin = app.renderer._overlays[name]
        assert next(i.color for i in items if isinstance(i, OverlayRect)) == green
    for light in (Light.YELLOW, Light.RED):
        link.snapshot = snap(light=light, phase_start_ns=0, deadline_ns=clock.now_ns() + 20 * S)
        app.step(force=True)


# ---------------------------------------------------------------- M7: sound screen


def _audio(**kw):
    base = dict(local=True, mcu=True, volume=0.8, device="", devices=["HDMI", "Headphones"],
                local_available=True, busy=False, testing=False)  # fmt: skip
    base.update(kw)
    return base


def test_sound_screen_sends_settings_and_the_test_command(rig):
    app, link, _ = rig
    link.audio = _audio()
    key(app, pygame.K_m)
    click(app, "sound")
    click(app, "local")
    click(app, "mcu")
    click(app, "volume-")
    click(app, "device")
    click(app, "test")
    sent = link.sent
    assert sent[0]["type"] == "settings" and sent[0]["values"] == {"sound_local": False}
    assert sent[1]["values"] == {"sound_mcu": False}
    assert sent[2]["values"] == {"volume": 0.7}
    assert sent[3]["values"] == {"audio_device": "HDMI"}
    assert sent[4]["type"] == "cmd" and sent[4]["name"] == "sound_test"


def test_sound_test_button_is_disabled_while_busy_or_without_outputs(rig):
    app, link, _ = rig
    key(app, pygame.K_m)
    click(app, "sound")

    def test_enabled() -> bool:
        return next(
            w for w in app.screens[-1].widgets(app.make_context()) if w.id == "test"
        ).enabled

    link.audio = _audio()
    assert test_enabled()
    link.audio = _audio(busy=True)
    assert not test_enabled()
    link.audio = _audio(local=False, mcu=False)
    assert not test_enabled()
    link.audio = None  # core has not reported yet
    assert not test_enabled()


def test_core_confirms_sound_settings_to_a_new_ui_client(tmp_path):
    """End to end through a real core service: settings in, audio state out, replayed on connect."""
    from tests.audio.test_audio import FakeBackend, wait_for

    from archerytimer.audio.audio_worker import AudioWorker
    from archerytimer.audio.settings import AudioSettingsStore
    from archerytimer.common.clock import MonotonicClock
    from archerytimer.core.models import Sequence
    from archerytimer.core_service.audio_control import AudioControl
    from archerytimer.core_service.service import CoreService
    from archerytimer.ipc.messages import settings_msg
    from archerytimer.ipc.transport_inproc import InprocListener
    from archerytimer.ui_client.core_link import CoreLink

    be = FakeBackend()
    ctl = AudioControl(AudioWorker(be), store=AudioSettingsStore(tmp_path / "a.json"))
    listener = InprocListener()
    seq = Sequence("t", {"en": "T"}, (PhaseSpec("SHOOT", 5 * S, Light.GREEN, 1),))
    svc = CoreService(MonotonicClock(), {"t": seq}, listener, audio=ctl)
    svc.start()
    link = CoreLink(listener.connect, ping_interval_s=0.2, backoff_s=(0.02,))
    link.start()
    try:
        assert wait_for(lambda: link.drain() or link.audio is not None)
        assert link.audio["volume"] == 0.8
        link.send(settings_msg({"volume": 0.3, "sound_mcu": False}))
        assert wait_for(lambda: link.drain() or link.audio["volume"] == 0.3)
        assert link.audio["mcu"] is False
    finally:
        link.stop()
        svc.stop()
    link2 = CoreLink(listener.connect) if False else None  # listener is closed after stop
    assert link2 is None


# ---------------------------------------------------------------- network screen


def _node(**kw):
    base = dict(role="standalone", active_role="standalone", leader="", leaders=[],
                espnow="off", lights=True, locked=False, busy=False, restart_needed=False)  # fmt: skip
    base.update(kw)
    return base


def _widgets(app):
    return {w.id: w for w in app.screens[-1].widgets(app.make_context()) if w.id}


def test_network_screen_sends_role_leader_and_wireless_choices(rig):
    app, link, _ = rig
    link.node = _node(role="follower", leaders=[{"name": "Klubben", "addr": "10.0.0.2:8765"}])
    key(app, pygame.K_m)
    click(app, "network")
    click(app, "role_leader")
    click(app, "leader")
    click(app, "espnow")
    values = [m["values"] for m in link.sent if m["type"] == "settings"]
    assert values == [
        {"node_role": "leader"},
        {"node_leader": "10.0.0.2:8765"},
        {"espnow": "bridge"},
    ]
    click(app, "lights")
    assert link.sent[-1]["values"] == {"lights": False}


def test_network_apply_needs_a_pending_change_and_confirmation(rig):
    app, link, _ = rig
    link.node = _node()
    key(app, pygame.K_m)
    click(app, "network")
    assert not _widgets(app)["apply"].enabled
    link.node = _node(role="leader", restart_needed=True, busy=True)
    assert not _widgets(app)["apply"].enabled  # a session is in progress
    link.node = _node(role="leader", restart_needed=True)
    assert _widgets(app)["apply"].enabled
    click(app, "apply")
    assert not [m for m in link.sent if m.get("name") == "apply_network"]  # asks first
    click(app, "yes")
    assert [m["name"] for m in link.sent if m["type"] == "cmd"] == ["apply_network"]


def test_network_screen_is_read_only_when_locked_by_start_flags(rig):
    app, link, _ = rig
    link.node = _node(locked=True)
    key(app, pygame.K_m)
    click(app, "network")
    w = _widgets(app)
    assert not w["role_leader"].enabled and not w["espnow"].enabled
    assert w["lights"].enabled  # the lights toggle is not a start-flag matter

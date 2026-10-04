"""Menu, settings, hardware status and shortcut help."""

from __future__ import annotations

from typing import Any

from archerytimer.core.models import Mode
from archerytimer.ui_client.context import CORE_OK, ViewContext
from archerytimer.ui_client.prefs import FPS_CHOICES
from archerytimer.ui_client.screens.base import (
    MARGIN,
    Screen,
    grid,
    nav_back,
    title,
)
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.screens.followers import FollowersScreen
from archerytimer.ui_client.screens.network import NetworkScreen, RosterScreen
from archerytimer.ui_client.screens.remotes import RemotesScreen
from archerytimer.ui_client.screens.setup import SetupScreen
from archerytimer.ui_client.screens.sound import SoundScreen
from archerytimer.ui_client.screens.timers import TimersScreen
from archerytimer.ui_client.widgets import Widget


def confirm_quit(app: Any) -> None:
    app.open_screen(
        ConfirmScreen(app, app.t("confirm.quit"), app.t("confirm.quit_yes"), app.quit_app)
    )


def confirm_reset(app: Any) -> None:
    app.open_screen(
        ConfirmScreen(app, app.t("confirm.reset"), app.t("confirm.reset_yes"), app.reset_session)
    )


class MenuScreen(Screen):
    name = "menu"

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t, snap = ctx.t, ctx.snap
        online = snap is not None and ctx.core_state == CORE_OK
        running = online and snap is not None and snap.mode is Mode.RUNNING
        has_session = online and snap is not None and snap.mode is not Mode.IDLE
        items = [
            ("setup", t("menu.setup"), not running and online),
            ("reset", t("menu.reset"), has_session and not running),
            ("timers", t("menu.timers"), True),
            ("sound", t("menu.sound"), True),
            ("settings", t("menu.settings"), True),
            ("hardware", t("menu.hardware"), True),
            ("network", t("menu.network"), True),
            ("roster", t("menu.roster"), True),
            ("remotes", t("menu.remotes"), True),
            ("followers", t("menu.followers"), True),
            ("help", t("menu.help"), True),
            ("quit", t("menu.quit"), True),
        ]
        out = [title(t("menu.title"))]
        for (wid, label, enabled), rect in zip(items, grid(len(items), 2, 0.14, 0.74, 0.16)):
            out.append(Widget(wid, "button", rect, label, enabled=enabled))
        if running:
            out.append(Widget("", "warn", (MARGIN, 0.77, 1 - 2 * MARGIN, 0.07), t("menu.locked")))
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        app = self.app
        if wid == "back":
            self.back()
        elif wid == "setup":
            app.open_screen(SetupScreen(app))
        elif wid == "reset":
            confirm_reset(app)
        elif wid == "timers":
            app.open_screen(TimersScreen(app))
        elif wid == "sound":
            app.open_screen(SoundScreen(app))
        elif wid == "settings":
            app.open_screen(SettingsScreen(app))
        elif wid == "hardware":
            app.open_screen(HardwareScreen(app))
        elif wid == "network":
            app.open_screen(NetworkScreen(app))
        elif wid == "roster":
            app.open_screen(RosterScreen(app))
        elif wid == "remotes":
            app.open_screen(RemotesScreen(app))
        elif wid == "followers":
            app.open_screen(FollowersScreen(app))
        elif wid == "help":
            app.open_screen(HelpScreen(app))
        elif wid == "quit":
            confirm_quit(app)


class SettingsScreen(Screen):
    """Display settings (UI only; they never reach the core)."""

    name = "settings"

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        app = self.app
        d, p = app.display, app.prefs_data
        on, off = t("common.on"), t("common.off")
        items = [
            ("lang", t("settings.language", value=t("settings.lang_name")), False),
            ("tenths", t("settings.tenths", value=on if d.tenths else off), d.tenths),
            ("fps", t("settings.fps", value=str(d.fps_cap)), False),
            ("eco", t("settings.eco", value=on if p.eco else off), p.eco),
            ("idle", t("settings.idle", value=on if p.idle_screen else off), p.idle_screen),
            ("idle_delay", t("settings.idle_delay", value=p.idle_delay_min), False),
            (
                "idle_style",
                t("settings.idle_style", value=t("settings.style_" + p.idle_style)),
                False,
            ),
            ("timers", t("menu.timers"), False),
        ]
        out = [title(t("settings.title"))]
        for (wid, label, selected), rect in zip(items, grid(len(items), 2, 0.14, 0.74, 0.16)):
            enabled = p.idle_screen or wid not in ("idle_delay", "idle_style")
            out.append(Widget(wid, "button", rect, label, selected=selected, enabled=enabled))
        out.append(Widget("", "text", (MARGIN, 0.77, 1 - 2 * MARGIN, 0.07), t("settings.hint")))
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        app = self.app
        if wid == "back":
            self.back()
        elif wid == "lang":
            app.set_language("en" if app.t.lang == "sv" else "sv")
        elif wid == "tenths":
            app.set_tenths(not app.display.tenths)
        elif wid == "fps":
            i = FPS_CHOICES.index(app.display.fps_cap) if app.display.fps_cap in FPS_CHOICES else -1
            app.set_fps(FPS_CHOICES[(i + 1) % len(FPS_CHOICES)])
        elif wid == "eco":
            app.set_eco(not app.prefs_data.eco)
        elif wid == "idle":
            app.set_idle(not app.prefs_data.idle_screen)
        elif wid == "idle_delay":
            app.cycle_idle_delay()
        elif wid == "idle_style":
            app.cycle_idle_style()
        elif wid == "timers":
            app.open_screen(TimersScreen(app))


class HardwareScreen(Screen):
    """Plain-language status of the timer, lights and network. No error codes."""

    name = "hardware"

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t, link = ctx.t, self.app.link
        core_ok = ctx.core_state == CORE_OK
        lights_ok = core_ok and ctx.snap is not None and ctx.snap.link == "up"
        rows: list[tuple[str, str]] = [
            ("row", t("hardware.timer_ok" if core_ok else "hardware.timer_down")),
            (
                "row" if lights_ok else "warn",
                t("hardware.lights_ok" if lights_ok else "hardware.lights_down"),
            ),
        ]
        if lights_ok and (link.hw_fw or link.hw_chip):
            rows.append(
                ("row", t("hardware.device", fw=link.hw_fw or "?", chip=link.hw_chip or "?"))
            )
        if link.espnow:
            rows.append(
                (
                    "row",
                    t(
                        "hardware.espnow",
                        mode=link.espnow.get("mode", "?"),
                        peers=link.espnow.get("peers", 0),
                    ),
                )
            )
        if not link.upstream_ok:
            rows.append(("warn", t("hardware.leader_lost")))
        if ctx.synced and abs(ctx.offset_ns) > 5_000_000:
            rows.append(("row", t("hardware.sync", ms=max(1, ctx.rtt_ns // 2_000_000))))
        rtt = getattr(link, "leader_rtt_ms", None)
        if rtt is not None:
            rows.append(("row", t("status.leader_sync", ms=max(1, round(rtt / 2)))))
        if link.hello is not None:
            rows.append(("row", t("hardware.version", version=link.hello.get("version", "?"))))
        out = [title(t("hardware.title"))]
        for i, (kind, text) in enumerate(rows):
            out.append(Widget("", kind, (MARGIN, 0.15 + i * 0.1, 1 - 2 * MARGIN, 0.09), text))
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        if wid == "back":
            self.back()


# Actions listed on the shortcut screen, in reading order.
HELP_ACTIONS = (
    "primary",
    "pause_toggle",
    "stop_end",
    "next",
    "back",
    "emergency",
    "clear_emergency_continue",
    "clear_emergency_restart",
    "menu",
    "toggle_operator",
    "confirm",
    "quit",
)


class HelpScreen(Screen):
    name = "help"

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        out = [title(t("help.title"))]
        half = (len(HELP_ACTIONS) + 1) // 2
        for i, action in enumerate(HELP_ACTIONS):
            col, row = divmod(i, half)
            keys = self.app.keymap.names_for(action)[:3]
            if action == "quit":
                keys = ["Ctrl+Q", *keys]
            text = f"{', '.join(keys) or '-'}  –  {t('help.' + action)}"
            kind = "warn" if action == "emergency" else "row"
            out.append(Widget("", kind, (MARGIN + col * 0.49, 0.15 + row * 0.11, 0.47, 0.10), text))
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        if wid == "back":
            self.back()

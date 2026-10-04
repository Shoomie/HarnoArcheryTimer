"""Sound: which outputs are on, volume, output device, and the sound test.

The settings live in the core (they belong to the machine with the speakers and the horn), so
this screen only sends them; the core answers with its new state. Nothing changes here until
the core confirms, which keeps every attached screen showing the truth.
"""

from __future__ import annotations

from typing import Any

from archerytimer.ui_client.context import CORE_OK, ViewContext
from archerytimer.ui_client.screens.base import MARGIN, Screen, grid, nav_back, stepper, title
from archerytimer.ui_client.widgets import Widget

VOLUME_STEP = 0.1


class SoundScreen(Screen):
    name = "sound"

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    def _state(self) -> dict[str, Any]:
        return self.app.link.audio or {}

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        a = self._state()
        online = ctx.core_state == CORE_OK and bool(a)
        on, off = t("common.on"), t("common.off")
        local, mcu = bool(a.get("local")), bool(a.get("mcu"))
        out = [title(t("sound.title"))]
        grid_items = [
            ("local", t("sound.local", value=on if local else off), local, online),
            ("mcu", t("sound.mcu", value=on if mcu else off), mcu, online),
        ]
        for (wid, label, selected, enabled), rect in zip(grid_items, grid(2, 2, 0.14, 0.27, 0.13)):
            out.append(Widget(wid, "button", rect, label, selected=selected, enabled=enabled))
        pct = f"{round(float(a.get('volume', 0)) * 100)} %"
        out += stepper("volume", t("sound.volume"), pct, 0.31)
        if not a.get("local_available", True) and online:
            out.append(
                Widget("", "warn", (MARGIN, 0.43, 1 - 2 * MARGIN, 0.07), t("sound.no_local"))
            )
        else:
            device = a.get("device") or t("sound.default_device")
            out.append(
                Widget(
                    "device",
                    "button",
                    (MARGIN, 0.43, 1 - 2 * MARGIN, 0.11),
                    t("sound.device", value=device),
                    enabled=online and len(a.get("devices", [])) > 0,
                )
            )
        busy = bool(a.get("busy"))
        testing = bool(a.get("testing"))
        can_test = online and not busy and not testing and (local or mcu)
        label = t("sound.testing") if testing else t("sound.test")
        out.append(
            Widget("test", "primary", (MARGIN, 0.58, 1 - 2 * MARGIN, 0.14), label, enabled=can_test)
        )
        hint = t("sound.busy") if busy else t("sound.test_hint")
        out.append(
            Widget("", "warn" if busy else "text", (MARGIN, 0.75, 1 - 2 * MARGIN, 0.07), hint)
        )
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        a = self._state()
        send = self.app.send_settings
        if wid == "back":
            self.back()
        elif wid == "local":
            send({"sound_local": not a.get("local")})
        elif wid == "mcu":
            send({"sound_mcu": not a.get("mcu")})
        elif wid in ("volume-", "volume+"):
            v = float(a.get("volume", 0.8)) + (VOLUME_STEP if wid[-1] == "+" else -VOLUME_STEP)
            send({"volume": round(max(0.0, min(1.0, v)), 2)})
        elif wid == "device":
            names = ["", *a.get("devices", [])]
            cur = a.get("device", "")
            i = names.index(cur) if cur in names else 0
            send({"audio_device": names[(i + 1) % len(names)]})
        elif wid == "test":
            self.app.send_action("sound_test")

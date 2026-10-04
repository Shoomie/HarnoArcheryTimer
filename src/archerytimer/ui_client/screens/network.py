"""Network and sync: how this device works together with others.

Three roles: works alone, is the main timer (leader), or follows a main timer. Every device
can have its own screen, lights and sound; only the main timer runs the session. The wireless
(ESP-NOW) mode lets light boxes with no screen join in. Like the sound screen, the settings
live in the core: this screen only sends them and shows what the core answers. A change of
role is saved at once but only takes effect after "Apply" (the core restarts its service,
refused while a session is in progress).
"""

from __future__ import annotations

from typing import Any

from archerytimer.ipc.messages import cmd_msg
from archerytimer.ui_client.context import CORE_OK, ViewContext
from archerytimer.ui_client.screens.base import MARGIN, Screen, grid, nav_back, title
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.widgets import Widget

ROLES = ("standalone", "leader", "follower")
ESPNOW_MODES = ("off", "bridge", "follow", "auto")
RADIO = "radio"  # node_leader sentinel: take the timer from the ESP32 radio only (no WiFi)


def next_leader(current: str, found: list[dict[str, str]]) -> str:
    """Cycle: automatic ("") then each leader found on the network."""
    choices = ["", *[d["addr"] for d in found]]
    if current and current not in choices:
        choices.append(current)  # a stored address that is not heard right now
    i = choices.index(current) if current in choices else 0
    return choices[(i + 1) % len(choices)]


class NetworkScreen(Screen):
    name = "network"

    def _state(self) -> dict[str, Any]:
        return self.app.link.node or {}

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        n = self._state()
        online = ctx.local_ok and bool(
            n
        )  # node settings belong to this device, not to the timer feed
        role = str(n.get("role", "standalone"))
        locked = bool(n.get("locked"))
        can_edit = online and not locked
        out = [title(t("network.title"))]
        for rid, rect in zip(ROLES, grid(3, 3, 0.14, 0.27, 0.13)):
            out.append(
                Widget(
                    "role_" + rid,
                    "button",
                    rect,
                    t("network.role_" + rid),
                    selected=role == rid,
                    enabled=can_edit,
                )
            )
        found = list(n.get("leaders", []))
        leader = str(n.get("leader", ""))
        radio = leader == RADIO
        if radio:
            value = t("network.leader_radio_value")
        elif not leader:
            value = (
                t("network.leader_auto", count=len(found)) if found else t("network.leader_none")
            )
        else:
            name = next((d["name"] for d in found if d["addr"] == leader), "")
            value = f"{name} ({leader})" if name else leader
        out.append(
            Widget(
                "leader",
                "button",
                (MARGIN, 0.29, 0.56, 0.11),
                t("network.leader", value=value),
                enabled=can_edit and role == "follower",
            )
        )
        out.append(
            Widget(
                "leader_radio",
                "button",
                (MARGIN + 0.58, 0.29, 1 - 2 * MARGIN - 0.58, 0.11),
                t("network.radio_only"),
                selected=radio and role == "follower",
                enabled=can_edit,
            )
        )
        lights = bool(n.get("lights", True))
        out.append(
            Widget(
                "lights",
                "button",
                (MARGIN, 0.42, 1 - 2 * MARGIN, 0.11),
                t("network.lights", value=t("common.on") if lights else t("common.off")),
                selected=lights,
                enabled=online,
            )
        )
        mode = str(n.get("espnow", "off"))
        out.append(
            Widget(
                "espnow",
                "button",
                (MARGIN, 0.55, 1 - 2 * MARGIN, 0.11),
                t("network.espnow", value=t("network.espnow_" + mode)),
                enabled=can_edit,
            )
        )
        pending = bool(n.get("restart_needed"))
        busy = bool(n.get("busy"))
        if locked:
            note, kind = t("network.locked"), "warn"
        elif pending and busy:
            note, kind = t("network.busy"), "warn"
        elif pending:
            note, kind = t("network.pending"), "text"
        elif radio and role == "follower":
            note, kind = t("network.hint_radio"), "text"
            feed = getattr(self.app.link, "espnow", None)
            if feed:
                note += " " + t("network.radio_feed", peers=int(feed.get("peers", 0)))
        else:
            note, kind = t("network.hint_" + role), "text"
        out.append(Widget("", kind, (MARGIN, 0.67, 1 - 2 * MARGIN, 0.07), note))
        out.append(
            Widget(
                "apply",
                "primary",
                (MARGIN, 0.75, 1 - 2 * MARGIN, 0.09),
                t("network.apply"),
                enabled=online and pending and not busy and not locked,
            )
        )
        out.append(nav_back(t("common.close")))
        return out

    def activate(self, wid: str) -> None:
        n = self._state()
        send = self.app.send_settings
        if wid == "back":
            self.back()
        elif wid.startswith("role_"):
            send({"node_role": wid[5:]})
        elif wid == "leader":
            send({"node_leader": next_leader(str(n.get("leader", "")), list(n.get("leaders", [])))})
        elif wid == "leader_radio":
            if n.get("leader") == RADIO and n.get("role") == "follower":
                send({"node_leader": ""})
            else:
                send({"node_role": "follower", "node_leader": RADIO})
        elif wid == "lights":
            send({"lights": not n.get("lights", True)})
        elif wid == "espnow":
            cur = str(n.get("espnow", "off"))
            i = ESPNOW_MODES.index(cur) if cur in ESPNOW_MODES else 0
            send({"espnow": ESPNOW_MODES[(i + 1) % len(ESPNOW_MODES)]})
        elif wid == "apply":
            t = self.app.t
            self.app.open_screen(
                ConfirmScreen(
                    self.app,
                    t("network.confirm"),
                    t("network.confirm_yes"),
                    lambda: self.app.send_action("apply_network"),
                )
            )


MAX_DEVICE_ROWS = 6


def roster_of(app: Any) -> dict[str, Any]:
    """The last ``roster`` message the link stored (empty until the core has sent one)."""
    return getattr(app.link, "roster", None) or {}


def device_line(t: Any, d: dict[str, Any], master: str) -> str:
    """One device in plain words: name, role, how it is connected, signal, firmware, last seen."""
    role = str(d.get("role", ""))
    name = str(d.get("name", "?"))
    if role == "leader":
        role_text = t("roster.role_leader")
    elif role in ("follower", "mirror"):
        follows = str(d.get("follows") or master)
        role_text = t("roster.role_follower", name=follows) if follows else t("roster.role_mirror")
    elif role == "alone":
        role_text = t("roster.role_alone")
    elif role in ("node", "radio"):
        role_text = t("roster.role_radio")
    elif role == "remote":
        role_text = t("roster.role_remote")
    else:
        role_text = t("roster.role_unknown")
    parts = [f"{name}: {role_text}"]
    via = str(d.get("via", ""))
    if via in ("lan", "radio", "usb"):
        parts.append(t("roster.via_" + via))
    signal = str(d.get("signal", ""))
    if signal in ("good", "weak"):
        parts.append(t("roster.signal_" + signal))
    if d.get("fw"):
        parts.append(t("roster.fw", fw=d["fw"]))
    if not d.get("this"):
        parts.append(t("roster.seen", s=int(float(d.get("last_seen_s", 0.0)))))
    text = " · ".join(parts)
    if d.get("this"):
        text = t("roster.this", text=text)
    if role == "leader":
        text = t("roster.master_mark", text=text)
    return text


class RosterScreen(Screen):
    """Timer network: every device the core knows, who the main timer is, and take-over."""

    name = "roster"

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        roster = roster_of(self.app)
        online = ctx.core_state == CORE_OK
        devices = [d for d in roster.get("devices", []) if isinstance(d, dict)]
        master = str(roster.get("master", ""))
        conflict = [str(c) for c in roster.get("conflict", [])]
        out = [title(t("roster.title"))]
        y = 0.14
        wide = 1 - 2 * MARGIN
        if conflict:
            names = t("roster.and").join(conflict)
            out.append(
                Widget("", "warn", (MARGIN, y, wide, 0.10), t("roster.conflict", names=names))
            )
            y += 0.12
        if not devices:
            out.append(Widget("", "text", (MARGIN, y, wide, 0.09), t("roster.none")))
        shown = devices[:MAX_DEVICE_ROWS]
        for d in shown:
            out.append(Widget("", "row", (MARGIN, y, wide, 0.085), device_line(t, d, master)))
            y += 0.095
        if len(devices) > len(shown):
            more = t("roster.more", n=len(devices) - len(shown))
            out.append(Widget("", "text", (MARGIN, y, wide, 0.06), more))
        me = next((d for d in devices if d.get("this")), None)
        already = me is not None and me.get("role") == "leader"
        out.append(nav_back(t("common.close")))
        out.append(
            Widget(
                "take_over",
                "button",
                (0.32, 0.85, 1 - 0.32 - MARGIN, 0.13),
                t("roster.take_over"),
                enabled=online and not already,
            )
        )
        return out

    def _take_over(self) -> None:
        self.app.link.send(cmd_msg("take_over"))

    def activate(self, wid: str) -> None:
        if wid == "back":
            self.back()
        elif wid == "take_over":
            t = self.app.t
            self.app.open_screen(
                ConfirmScreen(
                    self.app,
                    t("roster.confirm"),
                    t("roster.confirm_yes"),
                    self._take_over,
                )
            )

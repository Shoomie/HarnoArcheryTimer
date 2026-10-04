"""Wireless remotes: pair, choose what each remote may do, remove, reset the radio network.

Everything comes from the core's ``remotes`` message and goes back as commands; the screen
holds no state beyond which remote is open. Emergency stop is always allowed for a paired
remote and reset/quit are never offered. Reject is the default answer to a pairing request.
"""

from __future__ import annotations

from typing import Any, Optional

from archerytimer.ipc.messages import cmd_msg
from archerytimer.ui_client.context import CORE_OK, ViewContext
from archerytimer.ui_client.screens.base import MARGIN, Screen, grid, nav_back, title
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.widgets import Widget

# Permissions the operator can switch (action names of the contract). Emergency is not here:
# it is always on. A new remote starts with the first four; next/back are an explicit choice.
PERMS = ("primary", "pause", "resume", "stop_end", "next", "back")
DEFAULT_PERMS = ("primary", "pause", "resume", "stop_end")
PAIR_SECONDS = 60  # how long "Add remote" keeps the pairing window open
MAX_REMOTES = 6


def remotes_of(app: Any) -> dict[str, Any]:
    return getattr(app.link, "remotes", None) or {}


def _dicts(items: Any) -> list[dict[str, Any]]:
    return [x for x in items or [] if isinstance(x, dict)]


class RemotesScreen(Screen):
    name = "remotes"

    def _data(self) -> dict[str, Any]:
        return remotes_of(self.app)

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        d = self._data()
        online = ctx.core_state == CORE_OK
        opened = bool(d.get("pairing_open"))
        wide = 1 - 2 * MARGIN
        out = [title(t("remotes.title"))]
        half = (wide - 0.02) / 2
        label = (
            t("remotes.pair_open", s=int(d.get("seconds_left", 0))) if opened else t("remotes.add")
        )
        out.append(
            Widget(
                "pair", "button", (MARGIN, 0.14, half, 0.09), label, selected=opened, enabled=online
            )
        )
        out.append(
            Widget(
                "reset_radio",
                "button",
                (MARGIN + half + 0.02, 0.14, half, 0.09),
                t("remotes.reset_radio"),
                enabled=online,
            )
        )
        y = 0.25
        pending = _dicts(d.get("pending"))
        for i, p in enumerate(pending[:2]):
            who = t("remotes.wants", name=p.get("name", "?"))
            out.append(Widget("", "warn", (MARGIN, y, 0.50, 0.085), who))
            out.append(Widget(f"accept{i}", "button", (0.54, y, 0.20, 0.085), t("remotes.accept")))
            out.append(Widget(f"reject{i}", "primary", (0.76, y, 0.21, 0.085), t("remotes.reject")))
            y += 0.095
        if len(pending) > 2:
            more = t("remotes.more", n=len(pending) - 2)
            out.append(Widget("", "text", (MARGIN, y, wide, 0.05), more))
            y += 0.055
        remotes = _dicts(d.get("remotes"))[:MAX_REMOTES]
        if not remotes:
            out.append(Widget("", "text", (MARGIN, y + 0.02, wide, 0.08), t("remotes.none")))
        else:
            for i, (r, rect) in enumerate(
                zip(remotes, grid(len(remotes), 2, y + 0.01, 0.82, 0.11))
            ):
                seen = int(float(r.get("last_seen_s", 0)))
                text = t("remotes.item", name=r.get("name", "?"), s=seen)
                out.append(Widget(f"remote{i}", "button", rect, text))
        out.append(nav_back(t("common.close")))
        return out

    def _nth(self, key: str, i: int) -> Optional[dict[str, Any]]:
        items = _dicts(self._data().get(key))
        return items[i] if 0 <= i < len(items) else None

    def _send(self, name: str, args: Optional[dict[str, Any]] = None) -> None:
        self.app.link.send(cmd_msg(name, args))

    def activate(self, wid: str) -> None:
        app, t = self.app, self.app.t
        if wid == "back":
            self.back()
        elif wid == "pair":
            if self._data().get("pairing_open"):
                self._send("pair_close")
            else:
                self._send("pair_open", {"seconds": PAIR_SECONDS})
        elif wid == "reset_radio":
            app.open_screen(
                ConfirmScreen(
                    app,
                    t("remotes.confirm_reset"),
                    t("remotes.confirm_reset_yes"),
                    lambda: self._send("radio_reset_key"),
                )
            )
        elif wid.startswith(("accept", "reject")):
            p = self._nth("pending", int(wid[6:]))
            if p is not None:
                if wid.startswith("accept"):
                    self._send("pair_accept", {"id": p["id"], "perms": list(DEFAULT_PERMS)})
                else:
                    self._send("pair_reject", {"id": p["id"]})
        elif wid.startswith("remote"):
            r = self._nth("remotes", int(wid[6:]))
            if r is not None:
                app.open_screen(RemotePermsScreen(app, str(r["id"])))

    def primary(self) -> None:
        """Space/Enter answers the first waiting request with the safe choice: Reject."""
        p = self._nth("pending", 0)
        if p is not None:
            self._send("pair_reject", {"id": p["id"]})

    def back(self) -> None:
        if self._data().get("pairing_open"):
            self._send("pair_close")  # leaving the screen never leaves pairing open
        super().back()


class RemotePermsScreen(Screen):
    """What one paired remote may do, plus removing it."""

    name = "remote_perms"

    def __init__(self, app: Any, remote_id: str) -> None:
        super().__init__(app)
        self.remote_id = remote_id

    def _remote(self) -> Optional[dict[str, Any]]:
        for r in _dicts(remotes_of(self.app).get("remotes")):
            if str(r.get("id")) == self.remote_id:
                return r
        return None

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        r = self._remote()
        online = ctx.core_state == CORE_OK
        if r is None:
            return [title(t("remotes.gone")), nav_back(t("common.close"))]
        perms = set(r.get("perms", []))
        wide = 1 - 2 * MARGIN
        out = [title(t("remotes.perms_title", name=r.get("name", "?")))]
        for p, rect in zip(PERMS, grid(len(PERMS), 2, 0.14, 0.58, 0.12)):
            on = p in perms
            value = t("common.on") if on else t("common.off")
            label = t("remotes.perm", what=t("remotes.p_" + p), value=value)
            out.append(Widget("perm_" + p, "button", rect, label, selected=on, enabled=online))
        out.append(Widget("", "row", (MARGIN, 0.62, wide, 0.09), t("remotes.emergency_always")))
        out.append(Widget("", "text", (MARGIN, 0.72, wide, 0.07), t("remotes.no_reset")))
        out.append(nav_back(t("common.close")))
        out.append(
            Widget(
                "remove",
                "danger",
                (0.60, 0.85, 1 - 0.60 - MARGIN, 0.13),
                t("remotes.remove"),
                enabled=online,
            )
        )
        return out

    def activate(self, wid: str) -> None:
        app, t = self.app, self.app.t
        r = self._remote()
        if wid == "back":
            self.back()
        elif r is None:
            return
        elif wid.startswith("perm_"):
            now = set(r.get("perms", []))
            now.symmetric_difference_update({wid[5:]})
            perms = [x for x in PERMS if x in now]
            app.link.send(cmd_msg("remote_perms", {"id": self.remote_id, "perms": perms}))
        elif wid == "remove":
            app.open_screen(
                ConfirmScreen(
                    app,
                    t("remotes.confirm_remove", name=r.get("name", "?")),
                    t("remotes.confirm_remove_yes"),
                    self._remove,
                )
            )

    def _remove(self) -> None:
        self.app.link.send(cmd_msg("remote_remove", {"id": self.remote_id}))
        if self.app.screens and self.app.screens[-1] is self:
            self.app.close_screen()

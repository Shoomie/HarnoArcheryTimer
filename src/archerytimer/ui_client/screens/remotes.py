"""Wireless remotes: pair, choose what each remote may do, remove, reset the radio network.

Everything comes from the core's ``remotes`` message and goes back as commands. Opening the screen
starts a search: radio devices that power on nearby appear in the list at once (name and hardware
ID, no button needed on them), and the operator picks their rights before accepting. The screen
holds no state beyond the rights chosen for a device that is still waiting.
Emergency stop is always allowed for a paired remote and reset/quit are never offered.
Reject is the default answer to a pairing request.
"""

from __future__ import annotations

from typing import Any, Optional

from archerytimer.ipc.messages import cmd_msg
from archerytimer.ui_client.context import CORE_OK, ViewContext
from archerytimer.ui_client.screens.base import (
    MARGIN,
    NAV_H,
    NAV_Y,
    Screen,
    grid,
    nav_back,
    title,
)
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.widgets import Widget

# Permissions the operator can switch (action names of the contract). Emergency is not here:
# it is always on. A new remote starts with the first four; next/back are an explicit choice.
PERMS = ("primary", "pause", "resume", "stop_end", "next", "back")
DEFAULT_PERMS = ("primary", "pause", "resume", "stop_end")
PAIR_SECONDS = 120  # one pairing window; the core renews it while the search runs
MAX_REMOTES = 6
MAX_PENDING_ROWS = 3


def remotes_of(app: Any) -> dict[str, Any]:
    return getattr(app.link, "remotes", None) or {}


def _dicts(items: Any) -> list[dict[str, Any]]:
    return [x for x in items or [] if isinstance(x, dict)]


class RemotesScreen(Screen):
    name = "remotes"

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.chosen: dict[str, list[str]] = {}  # rights picked before accepting, by device id
        if not self._data().get("pairing_open"):
            self._send_search()

    def _send_search(self) -> None:
        self._send("pair_open", {"seconds": PAIR_SECONDS, "discover": True})

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
        label = t("remotes.searching") if opened else t("remotes.add")
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
        if opened and not pending:
            out.append(Widget("", "text", (MARGIN, y, wide, 0.05), t("remotes.looking")))
            y += 0.055
        for i, p in enumerate(pending[:MAX_PENDING_ROWS]):
            who = t("remotes.wants", name=p.get("name", "?"), mac=p.get("mac") or p.get("id", "?"))
            out.append(Widget(f"open{i}", "button", (MARGIN, y, 0.50, 0.085), who, enabled=online))
            out.append(Widget(f"accept{i}", "button", (0.54, y, 0.20, 0.085), t("remotes.accept")))
            out.append(Widget(f"reject{i}", "primary", (0.76, y, 0.21, 0.085), t("remotes.reject")))
            y += 0.095
        if len(pending) > MAX_PENDING_ROWS:
            more = t("remotes.more", n=len(pending) - MAX_PENDING_ROWS)
            out.append(Widget("", "text", (MARGIN, y, wide, 0.05), more))
            y += 0.055
        remotes = _dicts(d.get("remotes"))[:MAX_REMOTES]
        if not remotes:
            out.append(Widget("", "text", (MARGIN, y + 0.02, wide, 0.08), t("remotes.none")))
        else:
            for i, (r, rect) in enumerate(
                zip(remotes, grid(len(remotes), 2, y + 0.01, 0.83, 0.11, 0.01))
            ):
                seen = int(float(r.get("last_seen_s", 0)))
                if seen < 0:  # accepted, but the device has not been heard on the radio since
                    text = t("remotes.item_unheard", name=r.get("name", "?"))
                else:
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
                self._send_search()
        elif wid == "reset_radio":
            app.open_screen(
                ConfirmScreen(
                    app,
                    t("remotes.confirm_reset"),
                    t("remotes.confirm_reset_yes"),
                    lambda: self._send("radio_reset_key"),
                )
            )
        elif wid.startswith(("open", "accept", "reject")):
            digits = "".join(c for c in wid if c.isdigit())
            p = self._nth("pending", int(digits)) if digits else None
            if p is not None:
                pid = str(p["id"])
                if wid.startswith("open"):
                    app.open_screen(PendingRemoteScreen(app, pid, self.chosen))
                elif wid.startswith("accept"):
                    perms = self.chosen.pop(pid, list(DEFAULT_PERMS))
                    self._send("pair_accept", {"id": pid, "perms": perms})
                else:
                    self.chosen.pop(pid, None)
                    self._send("pair_reject", {"id": pid})
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


class PendingRemoteScreen(Screen):
    """A device waiting for approval: name, hardware ID, its rights, accept or reject."""

    name = "pending_remote"

    def __init__(self, app: Any, remote_id: str, chosen: dict[str, list[str]]) -> None:
        super().__init__(app)
        self.remote_id = remote_id
        self.chosen = chosen

    def _pending(self) -> Optional[dict[str, Any]]:
        for p in _dicts(remotes_of(self.app).get("pending")):
            if str(p.get("id")) == self.remote_id:
                return p
        return None

    def _perms(self) -> list[str]:
        return self.chosen.get(self.remote_id, list(DEFAULT_PERMS))

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        p = self._pending()
        online = ctx.core_state == CORE_OK
        if p is None:
            return [title(t("remotes.pending_gone")), nav_back(t("common.close"))]
        perms = set(self._perms())
        wide = 1 - 2 * MARGIN
        out = [title(t("remotes.pending_title", name=p.get("name", "?")))]
        mac = p.get("mac") or p.get("id", "?")
        out.append(Widget("", "row", (MARGIN, 0.13, wide, 0.08), t("remotes.hw_id", mac=mac)))
        for k, rect in zip(PERMS, grid(len(PERMS), 2, 0.23, 0.62, 0.11)):
            on = k in perms
            value = t("common.on" if on else "common.off")
            label = t("remotes.perm", what=t("remotes.p_" + k), value=value)
            out.append(Widget("perm_" + k, "button", rect, label, selected=on, enabled=online))
        out.append(Widget("", "row", (MARGIN, 0.66, wide, 0.08), t("remotes.emergency_always")))
        out.append(nav_back(t("common.close")))
        left = (0.31, NAV_Y, 0.25, NAV_H)
        out.append(Widget("reject", "button", left, t("remotes.reject"), enabled=online))
        right = (0.60, NAV_Y, 1 - 0.60 - MARGIN, NAV_H)
        out.append(Widget("accept", "primary", right, t("remotes.accept"), enabled=online))
        return out

    def activate(self, wid: str) -> None:
        app = self.app
        if wid == "back":
            self.back()
        elif self._pending() is None:
            return
        elif wid.startswith("perm_"):
            now = set(self._perms())
            now.symmetric_difference_update({wid[5:]})
            self.chosen[self.remote_id] = [x for x in PERMS if x in now]
        elif wid == "accept":
            perms = self.chosen.pop(self.remote_id, list(DEFAULT_PERMS))
            app.link.send(cmd_msg("pair_accept", {"id": self.remote_id, "perms": perms}))
            self.back()
        elif wid == "reject":
            self.chosen.pop(self.remote_id, None)
            app.link.send(cmd_msg("pair_reject", {"id": self.remote_id}))
            self.back()


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

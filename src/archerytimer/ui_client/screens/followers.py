"""Followers: other timers that watch this one, and what each may do (leader side).

Everything comes from the core's ``followers`` message (``link.followers``) and goes back as
commands (``follower_approve``, ``follower_perms``, ``follower_block``, ``follower_remove``). The
screen keeps only the rights the operator picked for a follower that is still waiting for approval.
Emergency stop is always allowed and never listed. Reject is the default answer to a request.
"""

from __future__ import annotations

from typing import Any, Optional

from archerytimer.ipc.access import PERMS, PRESETS, preset_of
from archerytimer.ipc.messages import cmd_msg
from archerytimer.ui_client.context import CORE_OK, ViewContext
from archerytimer.ui_client.screens.base import MARGIN, Screen, grid, nav_back, title
from archerytimer.ui_client.screens.confirm import ConfirmScreen
from archerytimer.ui_client.widgets import Widget

DEFAULT_PRESET = "operator"  # what Approve grants unless the operator picked something else first
PRESET_ORDER = ("view", "operator", "full")
MAX_PENDING_ROWS = 3
MAX_LISTED = 6


def followers_of(app: Any) -> list[dict[str, Any]]:
    """Known followers, waiting ones first (stable otherwise)."""
    data = getattr(app.link, "followers", None) or {}
    items = [x for x in data.get("followers", []) or [] if isinstance(x, dict)]
    return sorted(items, key=lambda f: f.get("status") != "pending")


def _line(t: Any, f: dict[str, Any]) -> str:
    status = str(f.get("status", ""))
    link = t("followers.connected" if f.get("connected") else "followers.offline")
    if status == "approved":
        what = t("followers.preset_" + str(f.get("preset") or preset_of(list(f.get("perms", [])))))
    else:
        what = t("followers.status_" + status) if status in ("pending", "blocked") else status
    return str(t("followers.item", name=f.get("name", "?"), link=link, what=what))


class FollowersScreen(Screen):
    name = "followers"

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.chosen: dict[str, list[str]] = {}  # rights picked before approving, by follower id

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        online = ctx.core_state == CORE_OK
        wide = 1 - 2 * MARGIN
        out = [title(t("followers.title"))]
        items = followers_of(self.app)
        pending = [f for f in items if f.get("status") == "pending"]
        shown = min(len(pending), MAX_PENDING_ROWS)
        y = 0.15
        for i in range(shown):
            out.append(
                Widget(
                    f"open{i}",
                    "button",
                    (MARGIN, y, 0.50, 0.085),
                    _line(t, items[i]),
                    enabled=online,
                )
            )
            out.append(
                Widget(
                    f"approve{i}",
                    "button",
                    (0.54, y, 0.20, 0.085),
                    t("followers.approve"),
                    enabled=online,
                )
            )
            out.append(
                Widget(
                    f"reject{i}",
                    "primary",
                    (0.76, y, 0.21, 0.085),
                    t("followers.reject"),
                    enabled=online,
                )
            )
            y += 0.095
        rest = items[shown:]
        if not items:
            out.append(Widget("", "text", (MARGIN, y + 0.02, wide, 0.12), t("followers.none")))
        else:
            listed = rest[:MAX_LISTED]
            for k, (f, rect) in enumerate(zip(listed, grid(len(listed), 2, y + 0.01, 0.80, 0.11))):
                out.append(Widget(f"open{shown + k}", "button", rect, _line(t, f), enabled=online))
            if len(rest) > MAX_LISTED:
                out.append(
                    Widget(
                        "",
                        "text",
                        (MARGIN, 0.80, wide, 0.05),
                        t("followers.more", n=len(rest) - MAX_LISTED),
                    )
                )
        out.append(nav_back(t("common.close")))
        return out

    def _nth(self, i: int) -> Optional[dict[str, Any]]:
        items = followers_of(self.app)
        return items[i] if 0 <= i < len(items) else None

    def _send(self, name: str, args: dict[str, Any]) -> None:
        self.app.link.send(cmd_msg(name, args))

    def activate(self, wid: str) -> None:
        if wid == "back":
            self.back()
        elif wid.startswith(("open", "approve", "reject")):
            digits = "".join(c for c in wid if c.isdigit())
            f = self._nth(int(digits)) if digits else None
            if f is None:
                return
            fid = str(f["id"])
            if wid.startswith("open"):
                self.app.open_screen(FollowerScreen(self.app, fid, self.chosen))
            elif wid.startswith("approve"):
                perms = self.chosen.pop(fid, list(PRESETS[DEFAULT_PRESET]))
                self._send("follower_approve", {"id": fid, "perms": perms})
            else:
                self._send("follower_remove", {"id": fid})

    def primary(self) -> None:
        """Space/Enter answers the first waiting request with the safe choice: Reject."""
        f = self._nth(0)
        if f is not None and f.get("status") == "pending":
            self._send("follower_remove", {"id": f["id"]})


class FollowerScreen(Screen):
    """One follower: preset, a toggle per permission, block, remove (or approve while waiting)."""

    name = "follower"

    def __init__(self, app: Any, follower_id: str, chosen: Optional[dict[str, list[str]]] = None):
        super().__init__(app)
        self.follower_id = follower_id
        self.chosen = chosen if chosen is not None else {}

    def _follower(self) -> Optional[dict[str, Any]]:
        for f in followers_of(self.app):
            if str(f.get("id")) == self.follower_id:
                return f
        return None

    def _perms(self, f: dict[str, Any]) -> list[str]:
        if f.get("status") == "pending":
            return self.chosen.get(self.follower_id, list(PRESETS[DEFAULT_PRESET]))
        return [p for p in PERMS if p in f.get("perms", [])]

    def widgets(self, ctx: ViewContext) -> list[Widget]:
        t = ctx.t
        f = self._follower()
        online = ctx.core_state == CORE_OK
        if f is None:
            return [title(t("followers.gone")), nav_back(t("common.close"))]
        status = f.get("status")
        pending = status == "pending"
        editable = online and status != "blocked"
        perms = set(self._perms(f))
        current = preset_of(list(perms))
        wide = 1 - 2 * MARGIN
        out = [title(t("followers.detail_title", name=f.get("name", "?")))]
        third = (wide - 0.04) / 3
        for k, name in enumerate(PRESET_ORDER):
            out.append(
                Widget(
                    "preset_" + name,
                    "button",
                    (MARGIN + k * (third + 0.02), 0.13, third, 0.09),
                    t("followers.preset_" + name),
                    selected=current == name,
                    enabled=editable,
                )
            )
        for p, rect in zip(PERMS, grid(len(PERMS), 2, 0.24, 0.71, 0.09, 0.015)):
            on = p in perms
            label = t(
                "followers.perm",
                what=t("followers.p_" + p),
                value=t("common.on" if on else "common.off"),
            )
            out.append(Widget("perm_" + p, "button", rect, label, selected=on, enabled=editable))
        out.append(Widget("", "row", (MARGIN, 0.73, wide, 0.08), t("followers.emergency_always")))
        out.append(nav_back(t("common.close")))
        out.append(
            Widget(
                "block",
                "button",
                (0.31, 0.85, 0.25, 0.13),
                t("followers.block"),
                enabled=online and status != "blocked",
            )
        )
        right = (0.60, 0.85, 1 - 0.60 - MARGIN, 0.13)
        if pending:
            out.append(Widget("approve", "primary", right, t("followers.approve"), enabled=online))
        else:
            out.append(Widget("remove", "danger", right, t("followers.remove"), enabled=online))
        return out

    def _set_perms(self, f: dict[str, Any], perms: list[str]) -> None:
        if f.get("status") == "pending":
            self.chosen[self.follower_id] = perms  # only sent with Approve
        else:
            self.app.link.send(cmd_msg("follower_perms", {"id": self.follower_id, "perms": perms}))

    def activate(self, wid: str) -> None:
        app, t = self.app, self.app.t
        f = self._follower()
        if wid == "back":
            self.back()
        elif f is None:
            return
        elif wid.startswith("preset_") and wid[7:] in PRESETS:
            self._set_perms(f, list(PRESETS[wid[7:]]))
        elif wid.startswith("perm_"):
            now = set(self._perms(f))
            now.symmetric_difference_update({wid[5:]})
            self._set_perms(f, [p for p in PERMS if p in now])
        elif wid == "approve":
            perms = self._perms(f)
            self.chosen.pop(self.follower_id, None)
            app.link.send(cmd_msg("follower_approve", {"id": self.follower_id, "perms": perms}))
            self.back()
        elif wid == "block":
            app.link.send(cmd_msg("follower_block", {"id": self.follower_id}))
        elif wid == "remove":
            app.open_screen(
                ConfirmScreen(
                    app,
                    t("followers.confirm_remove", name=f.get("name", "?")),
                    t("followers.confirm_remove_yes"),
                    self._remove,
                )
            )

    def _remove(self) -> None:
        self.app.link.send(cmd_msg("follower_remove", {"id": self.follower_id}))
        if self.app.screens and self.app.screens[-1] is self:
            self.app.close_screen()

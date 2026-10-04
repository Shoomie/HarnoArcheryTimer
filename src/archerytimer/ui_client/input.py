"""UI input: keyboard (also covers presentation clickers and foot pedals, which are
keyboards), joystick/gamepad buttons, and mouse hit-tests. Everything maps to *actions*;
the app turns actions into core commands. Mappings come from the ``[keys]`` and
``[joystick]`` tables in the settings TOML, so new devices need no code.

Actions: primary, pause_toggle, stop_end, next, back, emergency, clear_emergency_continue,
clear_emergency_restart, toggle_operator, menu, confirm, quit.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import pygame

log = logging.getLogger("archerytimer.ui.input")

# Presentation clickers send PageDown/PageUp (or Right/Left), B or "." (blank screen) and
# F5/Esc. Esc is the emergency stop: safe if a clicker sends it by accident.
DEFAULT_KEYS: dict[str, list[str]] = {
    "primary": ["space", "return", "enter", "page down", "right"],
    "back": ["backspace", "page up", "left"],
    "pause_toggle": ["p", "b", "."],
    "stop_end": ["s"],
    "next": ["n"],
    "emergency": ["escape"],
    "clear_emergency_continue": ["c"],
    "clear_emergency_restart": ["r"],
    "toggle_operator": ["h"],
    "menu": ["m", "f1"],
    "confirm": ["y"],
    "quit": [],  # Ctrl+Q is built in; both ask for confirmation
}

DEFAULT_JOYSTICK: dict[str, str] = {}  # e.g. "button0" = "primary"; empty until configured


class KeyMap:
    def __init__(self, overrides: Mapping[str, Any] | None = None) -> None:
        if not pygame.display.get_init():
            pygame.display.init()  # key_code() needs the video subsystem for correct names
        table = {action: list(names) for action, names in DEFAULT_KEYS.items()}
        for action, names in (overrides or {}).items():
            if action not in DEFAULT_KEYS:
                log.warning("unknown action in [keys]: %r", action)
                continue
            table[action] = [names] if isinstance(names, str) else [str(n) for n in names]
        self.table = table
        self._by_key: dict[int, str] = {}
        for action, names in table.items():
            for name in names:
                try:
                    self._by_key[pygame.key.key_code(name)] = action
                except ValueError:
                    log.warning("unknown key %r for action %s", name, action)

    def names_for(self, action: str) -> list[str]:
        """Key names bound to ``action``, for the shortcut screen."""
        return [n.capitalize() if len(n) > 1 else n.upper() for n in self.table.get(action, [])]

    def action_for(self, event: pygame.event.Event) -> str | None:
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
            return "quit"
        return self._by_key.get(event.key)


class JoystickMap:
    """Gamepad / custom HID buttons. Not verified on hardware."""

    def __init__(self, table: Mapping[str, str] | None = None) -> None:
        self._by_button: dict[int, str] = {}
        for name, action in (table or DEFAULT_JOYSTICK).items():
            if name.startswith("button") and name[6:].isdigit() and action in DEFAULT_KEYS:
                self._by_button[int(name[6:])] = action
            else:
                log.warning("ignoring [joystick] entry %r = %r", name, action)
        self._open: list[Any] = []

    def open_all(self) -> None:
        if not self._by_button:
            return
        try:
            pygame.joystick.init()
            self._open = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        except pygame.error as exc:
            log.warning("joystick init failed: %s", exc)

    def action_for(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.JOYBUTTONDOWN:
            return self._by_button.get(event.button)
        return None

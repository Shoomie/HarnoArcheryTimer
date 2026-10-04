"""Physical inputs on the core machine: MCU buttons (``$K``) and Raspberry Pi GPIO.

Both feed ``ButtonMap.on_event(source, id, down)``, which turns presses into engine
commands. A binding fires on press, or, if it has a ``hold`` action, on release (a short
press runs ``press``, a press longer than ``hold_s`` runs ``hold``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Optional

from archerytimer.common.clock import NS_PER_S, Clock
from archerytimer.core.models import Command

log = logging.getLogger("archerytimer.inputs")

ACTIONS = frozenset(
    {
        "primary",
        "pause",
        "resume",
        "stop_end",
        "next",
        "back",
        "emergency",
        "reset",
        "clear_emergency",
        "clear_emergency_restart",
    }
)


def action_to_command(action: str) -> Optional[Command]:
    if action == "clear_emergency_restart":
        return Command("clear_emergency", {"mode": "restart"})
    if action == "clear_emergency":
        return Command("clear_emergency", {"mode": "continue"})
    if action in ACTIONS:
        return Command(action)
    return None


@dataclass(frozen=True)
class Binding:
    press: str
    hold: Optional[str] = None
    hold_ns: int = 2 * NS_PER_S


def parse_bindings(table: Mapping[str, Any]) -> dict[str, Binding]:
    """From the ``[buttons]`` TOML table. Invalid entries are logged and skipped."""
    result: dict[str, Binding] = {}
    for key, spec in table.items():
        try:
            source, ident = key.split(":", 1)
            press = str(spec["press"])
            hold = spec.get("hold")
            if press not in ACTIONS or (hold is not None and hold not in ACTIONS):
                raise ValueError("unknown action")
            if hold is not None and press == "emergency":
                raise ValueError("emergency must not use hold")
            hold_ns = round(float(spec.get("hold_s", 2)) * NS_PER_S)
            result[f"{source}:{int(ident)}"] = Binding(
                press, None if hold is None else str(hold), hold_ns
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            log.warning("ignoring button binding %r: %s", key, exc)
    return result


class ButtonMap:
    def __init__(
        self, bindings: Mapping[str, Binding], send: Callable[[Command], None], clock: Clock
    ) -> None:
        self._bindings = dict(bindings)
        self._send = send
        self._clock = clock
        self._down_at: dict[str, int] = {}

    def on_event(self, source: str, ident: int, down: bool) -> None:
        """Called from reader / GPIO threads; only queue puts go out."""
        key = f"{source}:{ident}"
        b = self._bindings.get(key)
        if b is None:
            return
        now = self._clock.now_ns()
        if b.hold is None:
            if down:
                self._fire(b.press, key)
            return
        if down:
            self._down_at[key] = now
        elif key in self._down_at:
            held = now - self._down_at.pop(key)
            self._fire(b.hold if held >= b.hold_ns else b.press, key)

    def _fire(self, action: str, key: str) -> None:
        cmd = action_to_command(action)
        if cmd is not None:
            log.info("input %s -> %s", key, action)
            self._send(cmd)


class GpioUnavailable(RuntimeError):
    pass


class GpioInput:
    """Raspberry Pi GPIO buttons via gpiozero (apt: python3-gpiozero). Optional.

    Buttons are wired between the BCM pin and ground (internal pull-up, active low).
    Not verified on hardware yet.
    """

    def __init__(self, pins: list[int], on_event: Callable[[str, int, bool], None]) -> None:
        try:
            from gpiozero import Button
        except Exception as exc:  # ImportError, or no pin factory on a PC
            raise GpioUnavailable(str(exc)) from exc
        self._buttons: list[Any] = []
        try:
            for pin in pins:
                btn = Button(pin, pull_up=True, bounce_time=0.02)
                btn.when_pressed = lambda p=pin: on_event("gpio", p, True)
                btn.when_released = lambda p=pin: on_event("gpio", p, False)
                self._buttons.append(btn)
        except Exception as exc:
            self.close()
            raise GpioUnavailable(str(exc)) from exc

    def close(self) -> None:
        for btn in self._buttons:
            try:
                btn.close()
            except Exception:
                log.exception("closing gpio button")
        self._buttons.clear()

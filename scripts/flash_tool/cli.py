"""Argument parsing and the interactive menu."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from . import actions as ac
from .runner import Runner, SubprocessRunner
from .strings import t
from .toolenv import Ctx
from .ui import Console

ACTIONS = ("flash", "build", "release", "monitor", "erase", "check", "installed", "remove", "ports")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flash.py",
        description="Flash the ESP32 modules. Without options an interactive menu opens.",
    )
    p.add_argument(
        "--action", choices=ACTIONS, help="what to do (default: flash if --env/--port is given)"
    )
    p.add_argument(
        "--env",
        action="append",
        help="firmware variant, e.g. esp32c3-supermini (repeat for --action release)",
    )
    p.add_argument("--port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    p.add_argument("--yes", action="store_true", help="answer yes to every question (no prompts)")
    p.add_argument(
        "--install-pio",
        action="store_true",
        help="with --yes: also allow the 1 GB PlatformIO download",
    )
    return p


def run_menu(ctx: Ctx) -> int:
    entries: list[tuple[str, Callable[[], int]]] = [
        ("menu.flash", lambda: ac.flash_module(ctx)),
        ("menu.build", lambda: ac.build_and_flash(ctx)),
        ("menu.release", lambda: ac.create_release(ctx)),
        ("menu.monitor", lambda: ac.open_monitor(ctx)),
        ("menu.erase", lambda: ac.erase_module(ctx)),
        ("menu.check", lambda: ac.check_computer(ctx)),
        ("menu.installed", lambda: ac.show_installed(ctx)),
        ("menu.remove", lambda: ac.remove_env(ctx)),
    ]
    while True:
        ctx.console.say("")
        ctx.console.say(t("title"))
        ctx.console.say(t("menu.header"))
        for n, (key, _) in enumerate(entries, 1):
            ctx.console.say(f"  {n}. {t(key)}")
        ctx.console.say(f"  0. {t('menu.quit')}")
        try:
            answer = ctx.console.ask(t("menu.prompt"))
        except (EOFError, KeyboardInterrupt):
            return 0
        if answer is None or answer in ("0", "q", "Q"):
            return 0
        if answer.isdigit() and 1 <= int(answer) <= len(entries):
            entries[int(answer) - 1][1]()
        else:
            ctx.console.say(t("menu.invalid"))


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    runner: Optional[Runner] = None,
    console: Optional[Console] = None,
    environ: Optional[Mapping[str, str]] = None,
    root: Optional[Path] = None,
    platform: Optional[str] = None,
) -> int:
    if sys.version_info < (3, 9):  # noqa: UP036
        print(t("err.python"))
        return 1
    args = build_parser().parse_args(argv)
    action = args.action or ("flash" if (args.env or args.port) else None)
    con = console or Console(assume_yes=args.yes, interactive=action is None or not args.yes)
    if console is not None and args.yes:
        con.assume_yes = True
    ctx = Ctx(
        root=root or project_root(),
        runner=runner or SubprocessRunner(),
        console=con,
        environ=environ if environ is not None else dict(os.environ),
        platform=platform or sys.platform,
        install_pio=args.install_pio,
    )
    env1 = args.env[0] if args.env else None
    if action is None:
        return run_menu(ctx)
    table: dict[str, Callable[[], int]] = {
        "flash": lambda: ac.flash_module(ctx, env1, args.port),
        "build": lambda: ac.build_and_flash(ctx, env1, args.port),
        "release": lambda: ac.create_release(ctx, args.env),
        "monitor": lambda: ac.open_monitor(ctx, args.port),
        "erase": lambda: ac.erase_module(ctx, args.port),
        "check": lambda: ac.check_computer(ctx),
        "installed": lambda: ac.show_installed(ctx),
        "remove": lambda: ac.remove_env(ctx),
        "ports": lambda: _ports(ctx),
    }
    return table[action]()


def _ports(ctx: Ctx) -> int:
    from . import toolenv as te
    from .ports import describe, guess_board, list_ports

    if not te.ensure_esptool(ctx):
        return 1
    for p in list_ports(ctx):
        ctx.console.say(f"{describe(p)}  -> {guess_board(p)}")
    return 0

"""UI client entry point: ``python -m archerytimer.ui_client``.

One UI process drives one display. For several monitors or several machines, start one
UI client per display, each with its own ``--display`` / ``--profile`` and ``--host``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from archerytimer.common.i18n import Translator
from archerytimer.common.paths import data_dir, setup_logging
from archerytimer.ipc.transport_socket import DEFAULT_HOST, DEFAULT_PORT, connect_socket
from archerytimer.ui_client.app import DisplaySettings, UiApp, post_wake
from archerytimer.ui_client.core_link import CoreLink
from archerytimer.ui_client.input import JoystickMap, KeyMap
from archerytimer.ui_client.layout import PROFILES
from archerytimer.ui_client.prefs import FILE_NAME, PrefsStore
from archerytimer.ui_client.presets import DEFAULT_DIR as PRESETS_DIR
from archerytimer.ui_client.presets import load_presets, load_timings
from archerytimer.ui_client.renderer import DisplayConfig, open_renderer

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib  # type: ignore[no-redef]

log = logging.getLogger("archerytimer.ui")
DEFAULT_SETTINGS = Path(__file__).resolve().parents[3] / "config" / "default_settings.toml"


def parse_size(text: str) -> tuple[int, int]:
    w, _, h = text.lower().partition("x")
    return int(w), int(h)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=DEFAULT_HOST, help="core service address (LAN: its IP)")
    ap.add_argument("--tcp-port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--renderer", choices=["auto", "gpu", "software"], default="auto")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--display", type=int, default=0, help="monitor index")
    ap.add_argument("--size", type=parse_size, default=(1280, 720), help="windowed size WxH")
    ap.add_argument("--profile", choices=PROFILES, default="full")
    ap.add_argument("--lang", choices=["sv", "en"], help="default: saved choice, else sv")
    ap.add_argument(
        "--fps", type=int, help="FPS cap (0 = uncapped; default: saved choice, else 60)"
    )
    ap.add_argument("--vsync", action="store_true")
    ap.add_argument("--tenths", action="store_true", help="tenths of a second in the last 10 s")
    ap.add_argument("--constant", action="store_true", help="render every frame, not on change")
    ap.add_argument(
        "--show-cursor", action="store_true", help="keep the mouse cursor in fullscreen"
    )
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument("--sequence", help="dev: configure this sequence when the core is idle")
    ap.add_argument("--groups", default="AB,CD")
    ap.add_argument("--ends", type=int, default=2)
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    setup_logging("ui")
    settings: dict[str, Any] = {}
    if args.settings.exists():
        with args.settings.open("rb") as fh:
            settings = tomllib.load(fh)

    # Saved display choices apply unless the command line says otherwise.
    store = PrefsStore(data_dir() / FILE_NAME)
    prefs = store.load()
    if args.lang:
        prefs.lang = args.lang
    if args.fps is not None:
        prefs.fps_cap, prefs.eco = None, False
    if args.tenths:
        prefs.tenths = None
    presets = load_presets(PRESETS_DIR, data_dir() / "presets")
    timings = load_timings(PRESETS_DIR, data_dir() / "presets")

    link = CoreLink(lambda: connect_socket(args.host, args.tcp_port), wake=post_wake)
    renderer = open_renderer(
        DisplayConfig(
            kind=args.renderer,
            fullscreen=args.fullscreen,
            display=args.display,
            size=args.size,
            vsync=args.vsync,
            hide_cursor=args.fullscreen and args.profile == "audience" and not args.show_cursor,
        )
    )
    log.info("renderer %s, logical size %s", renderer.name, renderer.logical_size)
    autoconfigure = None
    if args.sequence:
        autoconfigure = {
            "sequence_id": args.sequence,
            "groups": args.groups.split(","),
            "total_ends": args.ends,
        }
    app = UiApp(
        link,
        renderer,
        Translator(prefs.lang or "sv"),
        profile=args.profile,
        display=DisplaySettings(
            fps_cap=60 if args.fps is None else args.fps,
            tenths=args.tenths,
            idle_render="constant" if args.constant else "change",
        ),
        keymap=KeyMap(settings.get("keys")),
        joymap=JoystickMap(settings.get("joystick")),
        autoconfigure=autoconfigure,
        presets=presets,
        timings=timings,
        prefs=store,
    )
    link.start()
    try:
        app.run()
    finally:
        link.stop()
        renderer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

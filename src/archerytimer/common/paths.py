"""Per-user paths. Never depends on the working directory."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

APP_NAME = "archerytimer"


def data_dir() -> Path:
    try:
        from platformdirs import user_data_dir

        path = Path(user_data_dir(APP_NAME, appauthor=False))
    except ImportError:
        path = Path.home() / f".{APP_NAME}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(name: str, level: int = logging.INFO, *, console: bool = True) -> Path:
    """Rotating file log (ms timestamps) in the per-user data dir, plus optional console."""
    log_dir = data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{name}.log"
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s", "%H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(level)
    fh = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return path

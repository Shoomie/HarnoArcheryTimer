"""Static checks of the Pi deployment files (cannot run systemd here)."""

from __future__ import annotations

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / "scripts" / "systemd"


def load(name: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # type: ignore[assignment,method-assign]
    cp.read(UNITS / name, encoding="utf-8")
    return cp


@pytest.mark.parametrize("name", ["archerytimer-core.service", "archerytimer-ui.service"])
def test_unit_restarts_and_installs(name: str) -> None:
    cp = load(name)
    assert cp["Service"]["Restart"] == "always"
    assert cp["Service"]["User"] == "archery"
    assert "multi-user.target" in cp["Install"]["WantedBy"]


def test_core_is_headless_and_stops_safely() -> None:
    svc = load("archerytimer-core.service")["Service"]
    assert "archerytimer.core_service" in svc["ExecStart"]
    assert svc["KillSignal"] == "SIGTERM"
    assert int(svc["TimeoutStopSec"]) <= 10


def test_ui_is_kmsdrm_kiosk_that_follows_core() -> None:
    cp = load("archerytimer-ui.service")
    svc = cp["Service"]
    assert "Environment=SDL_VIDEODRIVER=kmsdrm" in (UNITS / "archerytimer-ui.service").read_text()
    assert "--fullscreen" in svc["ExecStart"]
    assert "archerytimer-core.service" in cp["Unit"]["Wants"]
    assert "archerytimer-core.service" not in cp["Unit"].get("Requires", "")


def test_install_script_paths_match_units() -> None:
    script = (ROOT / "scripts" / "install_pi.sh").read_text(encoding="utf-8")
    for name in ("archerytimer-core.service", "archerytimer-ui.service"):
        assert (UNITS / name).exists()
        assert name in script
    for f in ("core.env.example", "ui.env.example", "journald-archerytimer.conf"):
        assert (UNITS / f).exists()
    assert "/opt/archerytimer" in load("archerytimer-core.service")["Service"]["ExecStart"]


def _bash_works() -> bool:
    if shutil.which("bash") is None:
        return False
    return subprocess.run(["bash", "-c", "true"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _bash_works(), reason="bash not available")
@pytest.mark.parametrize("name", ["install_pi.sh", "uninstall_pi.sh"])
def test_shell_scripts_parse(name: str) -> None:
    text = (ROOT / "scripts" / name).read_bytes()
    subprocess.run(["bash", "-n"], input=text, check=True)

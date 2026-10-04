"""The project-local tool environment `.flash-env/`: paths, command lines, bootstrap decisions."""

from __future__ import annotations

import shutil
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from .manifest import (
    APP_OFFSET,
    BOOT_APP0_OFFSET,
    BOOTLOADER_OFFSET,
    FLASH_OFFSET,
    PARTITIONS_OFFSET,
)
from .runner import Runner
from .strings import t
from .ui import Console

ENV_DIR_NAME = ".flash-env"
ESPTOOL_SPEC = "esptool>=5,<6"
PIO_SPEC = "platformio"
WINDOWS_SHORT_CORE = "C:\\pio"
LONG_PATH_LIMIT = 60  # characters of the default PlatformIO core dir before a short one is used


@dataclass
class Ctx:
    root: Path  # project folder
    runner: Runner
    console: Console
    environ: Mapping[str, str] = field(default_factory=dict)
    platform: str = sys.platform
    python: str = sys.executable  # python that creates the venv
    install_pio: bool = False  # --install-pio: lets --yes also approve the 1 GB download

    @property
    def is_windows(self) -> bool:
        return self.platform.startswith("win")

    @property
    def env_dir(self) -> Path:
        return self.root / ENV_DIR_NAME

    @property
    def venv_python(self) -> Path:
        return self.env_dir / ("Scripts/python.exe" if self.is_windows else "bin/python")

    @property
    def venv_pio(self) -> Path:
        return self.env_dir / ("Scripts/pio.exe" if self.is_windows else "bin/pio")

    @property
    def release_dir(self) -> Path:
        return self.root / "firmware" / "release"

    @property
    def tools_dir(self) -> Path:
        return Path(__file__).resolve().parent


# ---------------------------------------------------------------- command lines


def esptool_cmd(ctx: Ctx, *args: str) -> list[str]:
    return [str(ctx.venv_python), "-m", "esptool", *args]


def chip_id_cmd(ctx: Ctx, port: str) -> list[str]:
    return esptool_cmd(ctx, "--port", port, "chip-id")


def write_cmd(ctx: Ctx, chip: str, port: str, image: Path, baud: int = 460800) -> list[str]:
    return esptool_cmd(
        ctx,
        "--chip",
        chip,
        "--port",
        port,
        "--baud",
        str(baud),
        "write-flash",
        hex(FLASH_OFFSET),
        str(image),
    )


def verify_cmd(ctx: Ctx, chip: str, port: str, image: Path, baud: int = 460800) -> list[str]:
    return esptool_cmd(
        ctx,
        "--chip",
        chip,
        "--port",
        port,
        "--baud",
        str(baud),
        "verify-flash",
        hex(FLASH_OFFSET),
        str(image),
    )


def erase_cmd(ctx: Ctx, port: str) -> list[str]:
    return esptool_cmd(ctx, "--port", port, "erase-flash")


def merge_cmd(ctx: Ctx, chip: str, out: Path, build_dir: Path, boot_app0: Path) -> list[str]:
    parts = [
        (BOOTLOADER_OFFSET[chip], build_dir / "bootloader.bin"),
        (PARTITIONS_OFFSET, build_dir / "partitions.bin"),
        (BOOT_APP0_OFFSET, boot_app0),
        (APP_OFFSET, build_dir / "firmware.bin"),
    ]
    cmd = esptool_cmd(ctx, "--chip", chip, "merge-bin", "-o", str(out))
    for off, path in parts:
        cmd += [hex(off), str(path)]
    return cmd


def pio_build_cmd(pio: Path, env: str) -> list[str]:
    return [str(pio), "run", "-e", env]


def pio_upload_cmd(pio: Path, env: str, port: str) -> list[str]:
    return [str(pio), "run", "-e", env, "-t", "upload", "--upload-port", port]


# ---------------------------------------------------------------- locations


def pio_path(ctx: Ctx) -> Optional[Path]:
    """FLASH_PIO overrides; otherwise the pio program inside .flash-env if it exists."""
    override = ctx.environ.get("FLASH_PIO")
    if override and Path(override).exists():
        return Path(override)
    return ctx.venv_pio if ctx.venv_pio.exists() else None


def core_dir(ctx: Ctx) -> tuple[Path, bool]:
    """Where PlatformIO keeps its toolchains; the bool says a short Windows folder was chosen."""
    given = ctx.environ.get("PLATFORMIO_CORE_DIR")
    if given:
        return Path(given), False
    default = ctx.env_dir / "pio-core"
    if ctx.is_windows and len(str(default)) > LONG_PATH_LIMIT:
        return Path(WINDOWS_SHORT_CORE), True
    return default, False


def pio_env(ctx: Ctx) -> dict[str, str]:
    env = dict(ctx.environ)
    env["PLATFORMIO_CORE_DIR"] = str(core_dir(ctx)[0])
    return env


def boot_app0_path(ctx: Ctx) -> Optional[Path]:
    packages = core_dir(ctx)[0] / "packages"
    for pkg in sorted(packages.glob("framework-arduinoespressif32*")):
        cand = pkg / "tools" / "partitions" / "boot_app0.bin"
        if cand.exists():
            return cand
    return None


# ---------------------------------------------------------------- bootstrap


def has_esptool(ctx: Ctx) -> bool:
    if not ctx.venv_python.exists():
        return False
    rc, _ = ctx.runner.capture([str(ctx.venv_python), "-c", "import esptool, serial"])
    return rc == 0


def _create_venv(ctx: Ctx) -> bool:
    if ctx.venv_python.exists():
        return True
    ctx.console.say(t("boot.creating"))
    return ctx.runner.run([ctx.python, "-m", "venv", str(ctx.env_dir)]) == 0


def _pip(ctx: Ctx, spec: str, what: str) -> bool:
    ctx.console.say(t("boot.installing", what=what))
    cmd = [str(ctx.venv_python), "-m", "pip", "install", "--disable-pip-version-check", spec]
    return ctx.runner.run(cmd) == 0


def ensure_esptool(ctx: Ctx) -> bool:
    """Make sure esptool exists in .flash-env; asks before downloading anything."""
    if has_esptool(ctx):
        return True
    ctx.console.say(t("boot.esptool", dir=ctx.env_dir))
    if not ctx.console.confirm(t("boot.esptool.ask"), default=False):
        ctx.console.say(t("boot.declined"))
        return False
    if not (_create_venv(ctx) and _pip(ctx, ESPTOOL_SPEC, "esptool")):
        ctx.console.say(t("boot.failed"))
        return False
    return True


def ensure_pio(ctx: Ctx) -> Optional[Path]:
    """Return the pio program, installing PlatformIO on demand (after asking)."""
    existing = pio_path(ctx)
    if existing:
        if ctx.environ.get("FLASH_PIO"):
            ctx.console.say(t("boot.pio.override", path=existing))
        return existing
    core, short = core_dir(ctx)
    ctx.console.say(t("boot.pio", dir=ctx.env_dir))
    ctx.console.say(t("boot.pio.coredir", core=core))
    if short:
        ctx.console.say(t("boot.pio.short"))
    if ctx.console.assume_yes and not ctx.install_pio:
        ctx.console.say(t("boot.pio.need_flag"))
        return None
    if not ctx.console.confirm(t("boot.pio.ask"), default=False):
        ctx.console.say(t("boot.declined"))
        return None
    if not (_create_venv(ctx) and _pip(ctx, PIO_SPEC, "PlatformIO")):
        ctx.console.say(t("boot.failed"))
        return None
    return pio_path(ctx)


def remove_tree(path: Path) -> None:
    def _fix(func, p, _exc):  # type: ignore[no-untyped-def]
        Path(p).chmod(stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=_fix)

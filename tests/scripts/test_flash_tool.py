"""Flashing menu tests: no hardware, no network, no real esptool/pio (the runner is a fake)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from flash_tool import actions as ac
from flash_tool import cli
from flash_tool import manifest as mf
from flash_tool import toolenv as te
from flash_tool.ports import PortInfo, guess_board, parse_ports
from flash_tool.ui import Console

PORTS_JSON = json.dumps(
    [
        {"device": "COM5", "description": "USB JTAG", "vid": 0x303A, "pid": 0x1001},
        {"device": "COM7", "description": "CP210x", "vid": 0x10C4, "pid": 0xEA60},
    ]
)


class FakeRunner:
    """Records commands; answers capture() from a rule list (substring of the command -> output)."""

    def __init__(self, chip_out: str = "Chip is ESP32-C3 (revision v0.4)", venv_ready: bool = True):
        self.runs: list[list[str]] = []
        self.captures: list[list[str]] = []
        self.chip_out = chip_out
        self.run_rc: dict[str, int] = {}
        self.venv_ready = venv_ready
        self.root: Optional[Path] = None

    def run(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> int:
        self.runs.append(list(cmd))
        joined = " ".join(cmd)
        if cmd[1:3] == ["-m", "venv"]:
            _make_venv(Path(cmd[3]))
        for key, rc in self.run_rc.items():
            if key in joined:
                return rc
        return 0

    def capture(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> tuple[int, str]:
        self.captures.append(list(cmd))
        joined = " ".join(cmd)
        if "listports.py" in joined:
            return 0, PORTS_JSON + "\n"
        if "chip-id" in joined:
            return 0, self.chip_out
        return 0, ""


def _make_venv(env_dir: Path) -> None:
    for rel in ("Scripts/python.exe", "bin/python"):
        py = env_dir / rel
        py.parent.mkdir(parents=True, exist_ok=True)
        py.write_text("")


def _ctx(
    tmp_path: Path,
    answers: Sequence[str] = (),
    runner: Optional[FakeRunner] = None,
    platform: str = "linux",
    yes: bool = False,
    environ: Optional[dict] = None,
    ready: bool = True,
) -> tuple[te.Ctx, FakeRunner, list[str]]:
    said: list[str] = []
    it = iter(answers)

    def fake_input(prompt: str) -> str:
        said.append("PROMPT " + prompt)
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    r = runner or FakeRunner()
    con = Console(input_fn=fake_input, print_fn=said.append, assume_yes=yes, interactive=not yes)
    ctx = te.Ctx(root=tmp_path, runner=r, console=con, environ=environ or {}, platform=platform)
    if ready:
        _make_venv(ctx.env_dir)
        (tmp_path / "firmware" / "release").mkdir(parents=True, exist_ok=True)
    return ctx, r, said


def _image(ctx: te.Ctx, env: str, data: bytes = b"firmware") -> Path:
    path = ctx.release_dir / f"{env}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- manifest / chips


def test_variants_and_offsets() -> None:
    assert [v.env for v in mf.variants_for_chip("esp32c3")] == [
        "esp32c3-supermini",
        "esp32c3-standalone",
    ]
    assert len(mf.VARIANTS) == 6
    assert mf.variants_for_chip("esp32")[0].env == "esp32-wroom-32d"
    assert mf.FLASH_OFFSET == 0
    assert mf.BOOTLOADER_OFFSET == {"esp32": 0x1000, "esp32s3": 0, "esp32c3": 0}


@pytest.mark.parametrize(
    ("out", "chip"),
    [
        ("Chip is ESP32-S3 (revision v0.1)", "esp32s3"),
        ("Chip type:          ESP32-C3 (QFN32) (revision v0.4)", "esp32c3"),
        ("Detecting chip type... ESP32-S3", "esp32s3"),
        ("Chip is ESP32-D0WD-V3 (revision v3.1)", "esp32"),
        ("Chip is ESP32-S2", None),
        ("A fatal error occurred", None),
    ],
)
def test_parse_chip(out: str, chip: Optional[str]) -> None:
    got = mf.parse_chip(out)
    assert got == chip


def test_parse_version() -> None:
    assert mf.parse_version('#define FW_VERSION_STR "esp-0.4.0"') == "esp-0.4.0"
    assert mf.parse_version("nothing") == "unknown"


def test_manifest_roundtrip_and_errors() -> None:
    info = mf.ImageInfo(
        "esp32c3-supermini", "esp32c3", "esp-0.4.0", 100, "ab", "2026-10-04", "x.bin"
    )
    back = mf.parse_manifest(mf.dump_manifest({info.env: info}))
    assert back == {info.env: info}
    with pytest.raises(ValueError):
        mf.parse_manifest("{not json")
    with pytest.raises(ValueError):
        mf.parse_manifest('{"images": [{"env": "x"}]}')


# ---------------------------------------------------------------- ports


def test_parse_ports_and_guess() -> None:
    ports = parse_ports("noise\n" + PORTS_JSON)
    assert [p.device for p in ports] == ["COM5", "COM7"]
    assert ports[0].usb_id == "303A:1001"
    assert "ESP32-S3" in guess_board(ports[0])
    assert "CP210x" in guess_board(ports[1])
    assert "unknown" in guess_board(PortInfo("X", "", None, None))
    assert parse_ports("garbage") == []


# ---------------------------------------------------------------- command lines


def test_command_lines(tmp_path: Path) -> None:
    ctx, _, _ = _ctx(tmp_path)
    img = tmp_path / "a.bin"
    w = te.write_cmd(ctx, "esp32c3", "COM5", img)
    assert w[1:3] == ["-m", "esptool"]
    assert w[w.index("--chip") + 1] == "esp32c3"
    assert w[w.index("--port") + 1] == "COM5"
    assert w[w.index("write-flash") + 1] == "0x0"
    assert w[-1] == str(img)
    assert "verify-flash" in te.verify_cmd(ctx, "esp32c3", "COM5", img)
    assert te.erase_cmd(ctx, "COM5")[-1] == "erase-flash"
    pio = Path("pio")
    assert te.pio_build_cmd(pio, "e1") == ["pio", "run", "-e", "e1"]
    assert te.pio_upload_cmd(pio, "e1", "COM5")[-2:] == ["--upload-port", "COM5"]


@pytest.mark.parametrize(
    ("chip", "boot"), [("esp32", "0x1000"), ("esp32s3", "0x0"), ("esp32c3", "0x0")]
)
def test_merge_cmd_offsets(tmp_path: Path, chip: str, boot: str) -> None:
    ctx, _, _ = _ctx(tmp_path)
    cmd = te.merge_cmd(ctx, chip, Path("o.bin"), Path("b"), Path("app0.bin"))
    i = cmd.index("merge-bin")
    assert cmd[i + 3 :: 2] == [boot, "0x8000", "0xe000", "0x10000"]
    assert cmd[i + 4 :: 2][-1].endswith("firmware.bin")


def test_venv_paths_per_platform(tmp_path: Path) -> None:
    win, _, _ = _ctx(tmp_path, platform="win32", ready=False)
    lin, _, _ = _ctx(tmp_path, platform="linux", ready=False)
    assert win.venv_python.name == "python.exe" and win.venv_python.parent.name == "Scripts"
    assert lin.venv_python.name == "python" and lin.venv_python.parent.name == "bin"
    assert win.venv_pio.name == "pio.exe"


def test_windows_short_core_dir(tmp_path: Path) -> None:
    long_root = tmp_path / ("x" * 70)
    ctx, _, _ = _ctx(long_root, platform="win32", ready=False)
    core, short = te.core_dir(ctx)
    assert short and str(core) == "C:\\pio"
    ctx2, _, _ = _ctx(tmp_path / "a", platform="win32", ready=False)
    ctx2.environ = {"PLATFORMIO_CORE_DIR": "D:/pc"}
    assert te.core_dir(ctx2) == (Path("D:/pc"), False)
    ctx3, _, _ = _ctx(long_root, platform="linux", ready=False)
    assert not te.core_dir(ctx3)[1]  # the short folder is Windows only
    assert te.pio_env(ctx2)["PLATFORMIO_CORE_DIR"] == str(Path("D:/pc"))


# ---------------------------------------------------------------- bootstrap decision


def test_bootstrap_asks_before_downloading_and_declines(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, answers=["n"], ready=False)
    assert te.ensure_esptool(ctx) is False
    assert r.runs == []  # nothing created or downloaded
    assert not ctx.env_dir.exists()
    assert any("Download and install" in s for s in said)


def test_bootstrap_accepted_creates_venv_and_installs_only_esptool(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, answers=["y"], ready=False)
    assert te.ensure_esptool(ctx) is True
    assert r.runs[0][1:3] == ["-m", "venv"]
    pip = r.runs[1]
    assert pip[1:4] == ["-m", "pip", "install"]
    assert pip[-1].startswith("esptool")
    assert all("platformio" not in " ".join(c) for c in r.runs)


def test_no_bootstrap_when_ready(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path)
    assert te.ensure_esptool(ctx)
    assert r.runs == []


def test_pio_asks_and_mentions_size(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, answers=["n"])
    assert te.ensure_pio(ctx) is None
    assert any("1 GB" in s for s in said)
    assert r.runs == []


def test_flash_pio_override(tmp_path: Path) -> None:
    fake = tmp_path / "pio.exe"
    fake.write_text("")
    ctx, r, _ = _ctx(tmp_path, environ={"FLASH_PIO": str(fake)})
    assert te.ensure_pio(ctx) == fake
    assert r.runs == []


# ---------------------------------------------------------------- the flash flow


def test_flash_flow_writes_after_confirm(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, answers=["1", "1", "y"])  # port 1, variant 1, confirm
    img = _image(ctx, "esp32c3-supermini")
    assert ac.flash_module(ctx) == 0
    cmds = [" ".join(c) for c in r.runs]
    assert any("write-flash 0x0" in c and "COM5" in c and str(img) in c for c in cmds)
    assert any("verify-flash" in c for c in cmds)
    assert any("COM5" in s and "esp32c3-supermini.bin" in s for s in said)  # confirm names both


def test_flash_flow_cancel_default_writes_nothing(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, answers=["1", "1", ""])  # empty answer = No
    _image(ctx, "esp32c3-supermini")
    assert ac.flash_module(ctx) == 1
    assert r.runs == []


def test_flash_eof_means_no(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, answers=["1", "2"])
    _image(ctx, "esp32c3-standalone")
    assert ac.flash_module(ctx) == 1
    assert r.runs == []


def test_flash_missing_image_explains(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, answers=["1", "1"])
    assert ac.flash_module(ctx) == 1
    assert any("Create release images" in s for s in said)
    assert r.runs == []


def test_flash_refuses_chip_mismatch(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, yes=True)
    _image(ctx, "esp32-s3-devkitc-1")
    assert ac.flash_module(ctx, "esp32-s3-devkitc-1", "COM5") == 1  # module is a C3
    assert r.runs == []
    assert any("Not writing" in s for s in said)


def test_flash_refuses_sha_mismatch(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, yes=True)
    _image(ctx, "esp32c3-supermini")
    info = mf.ImageInfo("esp32c3-supermini", "esp32c3", "v", 1, "0" * 64, "d", "f")
    (ctx.release_dir / "manifest.json").write_text(mf.dump_manifest({info.env: info}))
    assert ac.flash_module(ctx, "esp32c3-supermini", "COM5") == 1
    assert r.runs == []


def test_non_interactive_flags_flash(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, yes=True)
    _image(ctx, "esp32c3-supermini")
    assert ac.flash_module(ctx, "esp32c3-supermini", "COM5") == 0
    assert any("write-flash" in " ".join(c) for c in r.runs)


def test_never_touches_unlisted_port(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, yes=True)
    _image(ctx, "esp32c3-supermini")
    assert ac.flash_module(ctx, "esp32c3-supermini", "COM99") == 1
    assert r.runs == []
    assert all("COM99" not in " ".join(c) for c in r.captures)


def test_write_failure_reported(tmp_path: Path) -> None:
    r = FakeRunner()
    r.run_rc["write-flash"] = 2
    ctx, _, said = _ctx(tmp_path, yes=True, runner=r)
    _image(ctx, "esp32c3-supermini")
    assert ac.flash_module(ctx, "esp32c3-supermini", "COM5") == 1
    assert not any("verify-flash" in " ".join(c) for c in r.runs)
    assert any("failed" in s.lower() for s in said)


def test_erase_confirm_default_is_cancel(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, answers=["1", ""])
    assert ac.erase_module(ctx) == 1
    assert r.runs == []
    ctx, r, _ = _ctx(tmp_path, answers=["2", "y"])
    assert ac.erase_module(ctx) == 0
    assert "erase-flash" in r.runs[-1]
    assert "COM7" in r.runs[-1]


# ---------------------------------------------------------------- release images


def test_release_builds_and_merges(tmp_path: Path) -> None:
    pio = tmp_path / "pio.exe"
    pio.write_text("")
    r = FakeRunner()
    ctx, _, _ = _ctx(
        tmp_path,
        yes=True,
        runner=r,
        environ={"FLASH_PIO": str(pio), "PLATFORMIO_CORE_DIR": str(tmp_path / "core")},
    )
    (tmp_path / "firmware" / "esp32s3" / "src").mkdir(parents=True)
    (tmp_path / "firmware" / "esp32s3" / "platformio.ini").write_text("")
    (tmp_path / "firmware" / "esp32s3" / "src" / "version.h").write_text(
        '#define FW_VERSION_STR "esp-9.9.9"\n'
    )
    build = tmp_path / "firmware" / "esp32s3" / ".pio" / "build" / "esp32-s3-devkitc-1"
    build.mkdir(parents=True)
    for n in ("bootloader.bin", "partitions.bin", "firmware.bin"):
        (build / n).write_bytes(b"x")
    app0 = tmp_path / "core" / "packages" / "framework-arduinoespressif32" / "tools" / "partitions"
    app0.mkdir(parents=True)
    (app0 / "boot_app0.bin").write_bytes(b"y")

    orig_run = r.run

    def run(cmd, cwd=None, env=None):  # type: ignore[no-untyped-def]
        rc = orig_run(cmd, cwd, env)
        if "merge-bin" in cmd:
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"merged")
        return rc

    r.run = run  # type: ignore[method-assign]
    assert ac.create_release(ctx, ["esp32-s3-devkitc-1"]) == 0
    assert any(c[1:3] == ["run", "-e"] for c in r.runs)  # pio build
    assert [c for c in r.runs if "merge-bin" in c]
    man = mf.load_manifest(tmp_path)["esp32-s3-devkitc-1"]
    assert man.version == "esp-9.9.9" and man.size == 6 and len(man.sha256) == 64


def test_release_without_pio_stops(tmp_path: Path) -> None:
    ctx, r, _ = _ctx(tmp_path, answers=["n"])
    assert ac.create_release(ctx) == 1
    assert r.runs == []


# ---------------------------------------------------------------- check / cli


def test_check_is_read_only(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, ready=False, platform="win32")
    assert ac.check_computer(ctx) == 0
    assert r.runs == [] and not ctx.env_dir.exists()
    assert any("CP210x" in s for s in said)


def test_cli_check_flag(tmp_path: Path) -> None:
    out: list[str] = []
    con = Console(print_fn=out.append, input_fn=lambda _: "", interactive=False)
    rc = cli.main(
        ["--action", "check"],
        runner=FakeRunner(),
        console=con,
        root=tmp_path,
        environ={},
        platform="linux",
    )
    assert rc == 0 and any("Python" in s for s in out)


def test_cli_env_port_implies_flash(tmp_path: Path) -> None:
    r = FakeRunner()
    ctx, _, _ = _ctx(tmp_path, yes=True)
    _image(ctx, "esp32c3-supermini")
    rc = cli.main(
        ["--env", "esp32c3-supermini", "--port", "COM5", "--yes"],
        runner=r,
        root=tmp_path,
        environ={},
        platform="linux",
    )
    assert rc == 0 and any("write-flash" in " ".join(c) for c in r.runs)


def test_menu_quit(tmp_path: Path) -> None:
    ctx, _, said = _ctx(tmp_path, answers=["6", "0"])
    assert cli.run_menu(ctx) == 0
    assert any("Check of this computer" in s for s in said)


def test_yes_does_not_approve_pio_download(tmp_path: Path) -> None:
    ctx, r, said = _ctx(tmp_path, yes=True)
    assert te.ensure_pio(ctx) is None
    assert r.runs == [] and any("--install-pio" in x for x in said)
    ctx.install_pio = True
    assert te.ensure_pio(ctx) is None or r.runs  # now it goes ahead and installs
    assert any("platformio" in " ".join(c) for c in r.runs)

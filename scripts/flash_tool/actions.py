"""The menu actions. Each returns a process exit code (0 = ok)."""

from __future__ import annotations

import datetime
import os
import shutil
import sys
from typing import Optional

from . import manifest as mf
from . import toolenv as te
from .ports import describe, guess_board, list_ports
from .strings import t
from .toolenv import Ctx


def _say(ctx: Ctx, text: str = "") -> None:
    ctx.console.say(text)


# ---------------------------------------------------------------- choosing a port / variant


def choose_port(ctx: Ctx, port: Optional[str] = None) -> Optional[str]:
    """Show the ports and return the one the user picked (never any other)."""
    ports = list_ports(ctx)
    if not ports:
        _say(ctx, t("ports.none"))
        return None
    if port:
        if any(p.device.lower() == port.lower() for p in ports):
            return next(p.device for p in ports if p.device.lower() == port.lower())
        _say(ctx, t("ports.unknown", port=port))
        return None
    if not ctx.console.interactive:
        _say(ctx, t("ports.need"))
        return None
    _say(ctx, t("ports.header"))
    for n, p in enumerate(ports, 1):
        _say(
            ctx,
            t(
                "ports.line",
                n=n,
                device=p.device,
                usb=p.usb_id,
                desc=p.description,
                guess=guess_board(p),
            ),
        )
    idx = ctx.console.choose(t("ports.choose"), [p.device for p in ports])
    return None if idx is None else ports[idx].device


def detect_chip(ctx: Ctx, port: str) -> Optional[str]:
    _say(ctx, t("detect.running", port=port))
    rc, out = ctx.runner.capture(te.chip_id_cmd(ctx, port))
    chip = mf.parse_chip(out) if rc == 0 else None
    if chip is None:
        _say(ctx, t("detect.failed", port=port))
        return None
    _say(ctx, t("detect.found", chip=chip))
    return chip


def pick_target(
    ctx: Ctx, env: Optional[str], port: Optional[str]
) -> Optional[tuple[str, str, mf.Variant]]:
    """Port, detected chip and firmware variant, or None (message already printed)."""
    chosen = None
    if env:
        chosen = mf.variant_by_env(env)
        if chosen is None:
            known = ", ".join(v.env for v in mf.VARIANTS)
            _say(ctx, t("variants.unknown_env", env=env, known=known))
            return None
    elif not ctx.console.interactive:
        _say(ctx, t("err.need_env"))
        return None
    port_ = choose_port(ctx, port)
    if port_ is None:
        return None
    chip = detect_chip(ctx, port_)
    if chip is None:
        return None
    if chosen is not None:
        if chosen.chip != chip:
            _say(
                ctx, t("variants.mismatch", env=chosen.env, want=chosen.chip, port=port_, chip=chip)
            )
            return None
        return port_, chip, chosen
    options = mf.variants_for_chip(chip)
    if not options:
        _say(ctx, t("variants.none", chip=chip))
        return None
    _say(ctx, t("variants.header"))
    for n, v in enumerate(options, 1):
        _say(ctx, t("variants.line", n=n, env=v.env, title=t(v.title_key), desc=t(v.desc_key)))
    idx = ctx.console.choose(t("variants.choose"), [v.env for v in options])
    return None if idx is None else (port_, chip, options[idx])


# ---------------------------------------------------------------- flash / build+flash


def flash_module(ctx: Ctx, env: Optional[str] = None, port: Optional[str] = None) -> int:
    if not te.ensure_esptool(ctx):
        return 1
    target = pick_target(ctx, env, port)
    if target is None:
        _say(ctx, t("cancelled"))
        return 1
    port_, chip, variant = target
    image = ctx.release_dir / f"{variant.env}.bin"
    if not image.exists():
        _say(ctx, t("image.missing", image=image))
        if te.pio_path(ctx) and ctx.console.confirm(t("image.offer_build"), default=False):
            return _build_and_upload(ctx, variant, port_, chip)
        return 1
    info = mf.load_manifest(ctx.root).get(variant.env)
    if info is not None and info.sha256 != mf.sha256_of(image):
        _say(ctx, t("image.bad_sha", image=image))
        return 1
    version = info.version if info else "unknown"
    _say(
        ctx,
        t(
            "flash.confirm",
            image=image,
            size=image.stat().st_size,
            version=version,
            port=port_,
            chip=chip,
        ),
    )
    if not ctx.console.confirm(t("flash.ask", port=port_), default=False):
        _say(ctx, t("cancelled"))
        return 1
    _say(ctx, t("flash.writing"))
    if ctx.runner.run(te.write_cmd(ctx, chip, port_, image)) != 0:
        _say(ctx, t("flash.failed"))
        return 1
    _say(ctx, t("flash.verifying"))
    # The write itself is hash-verified by esptool. This second look happens after the module has booted,
    # and the firmware stores its own settings in flash, so a difference there is a note, not a failure.
    if ctx.runner.run(te.verify_cmd(ctx, chip, port_, image)) != 0:
        _say(ctx, t("flash.verify_note"))
    _say(ctx, t("flash.ok"))
    return 0


def _build_and_upload(ctx: Ctx, variant: mf.Variant, port: str, chip: str) -> int:
    pio = te.pio_path(ctx)
    folder = ctx.root / "firmware" / variant.folder
    if pio is None:
        return 1
    if not folder.is_dir():
        _say(ctx, t("build.nofolder", folder=folder))
        return 1
    _say(ctx, t("build.confirm", env=variant.env, port=port, chip=chip))
    if not ctx.console.confirm(t("flash.ask", port=port), default=False):
        _say(ctx, t("cancelled"))
        return 1
    _say(ctx, t("build.writing", port=port))
    rc = ctx.runner.run(te.pio_upload_cmd(pio, variant.env, port), cwd=folder, env=te.pio_env(ctx))
    _say(ctx, t("flash.ok") if rc == 0 else t("flash.failed"))
    return 0 if rc == 0 else 1


def build_and_flash(ctx: Ctx, env: Optional[str] = None, port: Optional[str] = None) -> int:
    if not te.ensure_esptool(ctx):  # needed for listing ports and detecting the chip
        return 1
    if te.ensure_pio(ctx) is None:
        return 1
    target = pick_target(ctx, env, port)
    if target is None:
        _say(ctx, t("cancelled"))
        return 1
    port_, chip, variant = target
    return _build_and_upload(ctx, variant, port_, chip)


# ---------------------------------------------------------------- release images


def create_release(ctx: Ctx, envs: Optional[list[str]] = None) -> int:
    if not te.ensure_esptool(ctx):
        return 1
    pio = te.ensure_pio(ctx)
    if pio is None:
        _say(ctx, t("release.nopio"))
        return 1
    variants = list(mf.VARIANTS)
    if envs:
        variants = []
        for e in envs:
            v = mf.variant_by_env(e)
            if v is None:
                _say(
                    ctx,
                    t("variants.unknown_env", env=e, known=", ".join(x.env for x in mf.VARIANTS)),
                )
                return 1
            variants.append(v)
    ctx.release_dir.mkdir(parents=True, exist_ok=True)
    images = mf.load_manifest(ctx.root)
    version = mf.read_version(ctx.root)
    penv = te.pio_env(ctx)
    made, failed = 0, 0
    for v in variants:
        folder = ctx.root / "firmware" / v.folder
        if not (folder / "platformio.ini").exists():
            _say(ctx, t("release.skip", env=v.env, why=t("build.nofolder", folder=folder)))
            continue
        _say(ctx, t("release.building", env=v.env))
        if ctx.runner.run(te.pio_build_cmd(pio, v.env), cwd=folder, env=penv) != 0:
            _say(ctx, t("release.failed", env=v.env))
            failed += 1
            continue
        build_dir = folder / ".pio" / "build" / v.env
        boot_app0 = te.boot_app0_path(ctx)
        missing = [
            p
            for p in (
                build_dir / "bootloader.bin",
                build_dir / "partitions.bin",
                build_dir / "firmware.bin",
                boot_app0,
            )
            if p is None or not p.exists()
        ]
        if missing:
            _say(
                ctx,
                t(
                    "release.skip",
                    env=v.env,
                    why=t("release.missing_art", path=missing[0] or "boot_app0.bin"),
                ),
            )
            failed += 1
            continue
        assert boot_app0 is not None
        out = ctx.release_dir / f"{v.env}.bin"
        _say(ctx, t("release.merging", env=v.env))
        if (
            ctx.runner.run(te.merge_cmd(ctx, v.chip, out, build_dir, boot_app0)) != 0
            or not out.exists()
        ):
            _say(ctx, t("release.failed", env=v.env))
            failed += 1
            continue
        images[v.env] = mf.ImageInfo(
            env=v.env,
            chip=v.chip,
            version=version,
            size=out.stat().st_size,
            sha256=mf.sha256_of(out),
            built=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            file=out.name,
        )
        # Write after every image so a later failure keeps the good ones.
        (ctx.release_dir / "manifest.json").write_text(mf.dump_manifest(images), encoding="utf-8")
        made += 1
    _say(ctx, t("release.done", n=made, dir=ctx.release_dir))
    _say(ctx, t("release.commit"))
    return 0 if failed == 0 and made > 0 else 1


# ---------------------------------------------------------------- monitor / erase


def open_monitor(ctx: Ctx, port: Optional[str] = None) -> int:
    if not te.ensure_esptool(ctx):
        return 1
    port_ = choose_port(ctx, port)
    if port_ is None:
        _say(ctx, t("cancelled"))
        return 1
    _say(ctx, t("monitor.start", port=port_))
    return ctx.runner.run([str(ctx.venv_python), str(ctx.tools_dir / "monitor.py"), port_])


def erase_module(ctx: Ctx, port: Optional[str] = None) -> int:
    if not te.ensure_esptool(ctx):
        return 1
    port_ = choose_port(ctx, port)
    if port_ is None:
        _say(ctx, t("cancelled"))
        return 1
    _say(ctx, t("erase.confirm", port=port_))
    if not ctx.console.confirm(t("erase.ask", port=port_), default=False):
        _say(ctx, t("cancelled"))
        return 1
    if ctx.runner.run(te.erase_cmd(ctx, port_)) != 0:
        _say(ctx, t("erase.failed"))
        return 1
    _say(ctx, t("erase.ok"))
    return 0


# ---------------------------------------------------------------- check / installed / remove


def _serial_groups() -> list[str]:
    try:
        import grp

        names = {grp.getgrgid(g).gr_name for g in os.getgroups()}
    except (ImportError, KeyError, AttributeError):
        return []
    return sorted(names & {"dialout", "uucp", "plugdev"})


def check_computer(ctx: Ctx) -> int:
    """Read-only; never prompts and never downloads."""
    _say(ctx, t("check.header"))
    v = sys.version_info
    _say(ctx, t("check.python", version=f"{v[0]}.{v[1]}.{v[2]}", exe=ctx.python))
    ok = v >= (3, 9)
    if not ok:
        _say(ctx, t("check.python.old"))
    venv_ok = False
    try:
        import ensurepip  # noqa: F401
        import venv  # noqa: F401

        venv_ok = True
    except ImportError:
        pass
    _say(ctx, t("check.venv.ok") if venv_ok else t("check.venv.bad"))
    _say(ctx, t("check.os", system=ctx.platform))
    if ctx.is_windows:
        _say(ctx, t("check.hint.windows"))
    elif ctx.platform == "darwin":
        _say(ctx, t("check.hint.macos"))
    else:
        _say(ctx, t("check.hint.linux"))
        groups = _serial_groups()
        _say(ctx, t("check.group.ok", groups=", ".join(groups)) if groups else t("check.group.bad"))
    present = te.has_esptool(ctx)
    _say(ctx, t("check.tools", state=t("state.present" if present else "state.absent")))
    if present:
        _say(ctx, t("check.ports.n", n=len(list_ports(ctx))))
        for p in list_ports(ctx):
            _say(ctx, "  " + describe(p))
    else:
        _say(ctx, t("check.ports.noenv"))
    _say(ctx, t("check.images", n=len(list(ctx.release_dir.glob("*.bin")))))
    return 0 if ok and venv_ok else 1


def _pip_version(ctx: Ctx, package: str) -> Optional[str]:
    if not ctx.venv_python.exists():
        return None
    rc, out = ctx.runner.capture([str(ctx.venv_python), "-m", "pip", "show", package])
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return None


def show_installed(ctx: Ctx) -> int:
    _say(ctx, t("inst.header"))
    if not ctx.env_dir.exists():
        _say(ctx, t("inst.none"))
    else:
        _say(ctx, t("inst.dir", dir=ctx.env_dir))
        es = _pip_version(ctx, "esptool")
        if es:
            _say(ctx, t("inst.esptool", version=es))
        pio = _pip_version(ctx, "platformio")
        if pio or te.pio_path(ctx):
            _say(ctx, t("inst.pio", version=pio or "?"))
            _say(ctx, t("inst.core", core=te.core_dir(ctx)[0]))
        else:
            _say(ctx, t("inst.pio.none"))
    images = mf.load_manifest(ctx.root)
    if images:
        _say(ctx, t("inst.images"))
        for i in images.values():
            _say(
                ctx,
                t(
                    "inst.image",
                    env=i.env,
                    chip=i.chip,
                    version=i.version,
                    size=i.size,
                    built=i.built,
                ),
            )
    else:
        _say(ctx, t("inst.noimages"))
    return 0


def remove_env(ctx: Ctx) -> int:
    if not ctx.env_dir.exists():
        _say(ctx, t("remove.none"))
        return 0
    if not ctx.console.confirm(t("remove.ask", dir=ctx.env_dir), default=False):
        _say(ctx, t("cancelled"))
        return 1
    core, _ = te.core_dir(ctx)
    inside = ctx.env_dir in core.parents
    te.remove_tree(ctx.env_dir)
    if (
        not inside
        and core.exists()
        and ctx.console.confirm(t("remove.core.ask", core=core), default=False)
    ):
        shutil.rmtree(core, ignore_errors=True)
    _say(ctx, t("remove.ok"))
    return 0

"""Firmware variants, flash offsets per chip and the release manifest."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Merged images start at 0x0 on every chip.
FLASH_OFFSET = 0x0
# Offsets used when merging the build parts into one image.
BOOTLOADER_OFFSET = {"esp32": 0x1000, "esp32s3": 0x0, "esp32c3": 0x0}
PARTITIONS_OFFSET = 0x8000
BOOT_APP0_OFFSET = 0xE000
APP_OFFSET = 0x10000

# Chip name as printed by esptool -> value of esptool --chip.
CHIP_ARG = {"ESP32": "esp32", "ESP32-S3": "esp32s3", "ESP32-C3": "esp32c3"}

VERSION_FILE = Path("firmware") / "esp32s3" / "src" / "version.h"
RELEASE_DIR = Path("firmware") / "release"


@dataclass(frozen=True)
class Variant:
    env: str
    chip: str  # esptool --chip value
    folder: str  # under firmware/
    standalone: bool

    @property
    def title_key(self) -> str:
        return f"v.{self.env}.title"

    @property
    def desc_key(self) -> str:
        return "desc.standalone" if self.standalone else "desc.normal"


VARIANTS: tuple[Variant, ...] = (
    Variant("esp32-s3-devkitc-1", "esp32s3", "esp32s3", False),
    Variant("esp32-s3-standalone", "esp32s3", "esp32s3", True),
    Variant("esp32c3-supermini", "esp32c3", "esp32c3", False),
    Variant("esp32c3-standalone", "esp32c3", "esp32c3", True),
    Variant("esp32-wroom-32d", "esp32", "esp32", False),
    Variant("esp32-wroom-32d-standalone", "esp32", "esp32", True),
)


def variant_by_env(env: str) -> Optional[Variant]:
    return next((v for v in VARIANTS if v.env == env), None)


def variants_for_chip(chip: str) -> list[Variant]:
    return [v for v in VARIANTS if v.chip == chip]


_CHIP_RE = re.compile(
    r"(?:Chip is|Chip type:|Detecting chip type\.\.\.)\s*"
    r"(ESP32(?:-(?:S2|S3|C2|C3|C5|C6|H2|P4))?)(?![A-Za-z0-9])"
)


def parse_chip(output: str) -> Optional[str]:
    """Return the esptool --chip value found in esptool output, or None."""
    m = _CHIP_RE.search(output)
    return CHIP_ARG.get(m.group(1)) if m else None


def parse_version(header_text: str) -> str:
    m = re.search(r'#define\s+FW_VERSION_STR\s+"([^"]+)"', header_text)
    return m.group(1) if m else "unknown"


def read_version(root: Path) -> str:
    try:
        return parse_version((root / VERSION_FILE).read_text(encoding="utf-8"))
    except OSError:
        return "unknown"


@dataclass(frozen=True)
class ImageInfo:
    env: str
    chip: str
    version: str
    size: int
    sha256: str
    built: str
    file: str


def parse_manifest(text: str) -> dict[str, ImageInfo]:
    """Parse manifest.json; raises ValueError if it is malformed."""
    try:
        data = json.loads(text)
        out: dict[str, ImageInfo] = {}
        for item in data["images"]:
            info = ImageInfo(
                env=str(item["env"]),
                chip=str(item["chip"]),
                version=str(item["version"]),
                size=int(item["size"]),
                sha256=str(item["sha256"]),
                built=str(item["built"]),
                file=str(item["file"]),
            )
            out[info.env] = info
        return out
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"bad manifest: {exc}") from exc


def dump_manifest(images: dict[str, ImageInfo]) -> str:
    order = {v.env: i for i, v in enumerate(VARIANTS)}
    items = sorted(images.values(), key=lambda i: order.get(i.env, 99))
    doc = {
        "format": 1,
        "images": [
            {
                "env": i.env,
                "chip": i.chip,
                "version": i.version,
                "size": i.size,
                "sha256": i.sha256,
                "built": i.built,
                "file": i.file,
            }
            for i in items
        ],
    }
    return json.dumps(doc, indent=2) + "\n"


def load_manifest(root: Path) -> dict[str, ImageInfo]:
    path = root / RELEASE_DIR / "manifest.json"
    try:
        return parse_manifest(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

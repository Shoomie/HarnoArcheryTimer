"""Locale files (TOML) with English as the default and fallback."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "locales"


def _flatten(table: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in table.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, path + "."))
        else:
            out[path] = str(value)
    return out


def load_locale(lang: str, directory: Path = DEFAULT_DIR) -> dict[str, str]:
    path = directory / f"{lang}.toml"
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return _flatten(tomllib.load(fh))


class Translator:
    def __init__(self, lang: str = "en", directory: Path = DEFAULT_DIR) -> None:
        self.lang = lang
        self._primary = load_locale(lang, directory)
        self._fallback = load_locale("en", directory) if lang != "en" else {}

    def __call__(self, key: str, **fmt: object) -> str:
        text = self._primary.get(key) or self._fallback.get(key) or key
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text

    def pick(self, names: Mapping[str, str], default: str = "") -> str:
        """Choose from a localized-name table such as a sequence's ``name``."""
        return names.get(self.lang) or names.get("en") or default


def make_translator(lang: Optional[str] = None) -> Translator:
    return Translator(lang or "en")

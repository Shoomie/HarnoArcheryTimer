# Contributing

Everyone is welcome: archers, coaches, club volunteers, programmers, translators. All contributions are under the
project's MIT licence ([LICENSE](LICENSE)).

## Translating the documentation

The volunteer documents exist in 11 languages: English (the source), Swedish, Chinese, Hindi, Spanish, French,
Arabic, Bengali, Portuguese, Russian and Urdu.

| What | Files |
| --- | --- |
| Project page | `README.md` (English), `README.<code>.md` |
| Install guides | `docs/install/<system>.md`, `docs/install/<system>.<code>.md` for `windows`, `linux`, `raspberry-pi` |

Language codes: `sv` `zh` `hi` `es` `fr` `ar` `bn` `pt` `ru` `ur`.

Rules:

- Translate the meaning in plain words for volunteers, not word by word. Keep commands, file names, key names
  (**Space**, **Esc**), menu names of the operating system as shown on screen, and URLs exactly as in English.
- Keep headings in the same order so links such as `README.md#controls` map to the same section.
- When the English text changes, update the other languages or open an issue so someone can.
- Another language is welcome: copy the English files, add the code to the language bar at the top of each file,
  and mention it in `docs/README.md`.

## Translating the program interface

The interface is available in English (the default) and Swedish. All texts the program shows live in
`locales/<code>.toml`, and `sv` and `en` must keep identical keys. English is also the fallback for missing keys.
Adding another interface language needs the new `locales/<code>.toml` plus a small change to the language list in
`src/archerytimer/ui_client/` (`--lang` choices, saved preferences, the menu switch), and, for scripts that Inter
does not cover (Chinese, Arabic, Devanagari, Bengali...), an additional open-licensed font in `assets/fonts/`.
Open an issue first so the work can be shared.

## Code

See [CLAUDE.md](CLAUDE.md) for the project rules and [structure.md](structure.md) for where things are. Run the
tests with `pytest`, and `ruff check .` and `mypy` before sending changes. Timings and rules are configuration, not
code, and must be checked against the current World Archery rules before official use.

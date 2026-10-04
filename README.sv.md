# Archery Timer (Bågskyttetimer)

[English](README.md) · **Svenska**

En öppen källkod-klocka för bågskytte. Den kör skjuttiden på tävlingar och träning, visar den på en TV eller
skärm och styr lampor och signalhorn via USB. Gjord för en liten bågskyttklubb och för frivilliga som inte är
tekniker: skärmen har en tydlig knapp för det som händer härnäst och en nödstopp-knapp som alltid syns.

- Fungerar på **Windows 10/11**, **Linux**, **Raspberry Pi** (2B och nyare, som TV-kiosk) och macOS.
- Svenskt och engelskt gränssnitt (svenska är standard).
- Tid, lampor och ljud fortsätter även om skärmprogrammet kraschar.
- Valfritt ESP32-kort för lampor och horn, valfria extra skärmar och flera enheter på samma nätverk.

> **Status: tidig utveckling.** Timer, skärm, seriellt protokoll och flerenhetsfunktioner är byggda och testade i
> simulering. Det är **inte** provat med riktiga lampor/horn än, och ESP32-firmwaren har aldrig flashats.
> Tiderna i `config/` är **platshållare**, inte bekräftade regler från World Archery / SBF. Förlita dig inte på
> programmet i en officiell tävling ännu. Detaljer (på engelska): "Current status" i [CLAUDE.md](CLAUDE.md).

## Installera

Välj ditt system. Varje guide går steg för steg från ingenting till en körande timer.

| System | Guide | Kortversion |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.sv.md](docs/install/windows.sv.md) | Installera Python, ladda ner projektet, dubbelklicka `scripts\setup_windows.bat`, sedan `scripts\start_windows.bat` |
| **Linux** (och macOS) | [docs/install/linux.sv.md](docs/install/linux.sv.md) | `scripts/setup_desktop.sh`, sedan `scripts/start.sh` |
| **Raspberry Pi** (TV-kiosk) | [docs/install/raspberry-pi.sv.md](docs/install/raspberry-pi.sv.md) | Flasha Pi OS Lite, `git clone`, `sudo scripts/install_pi.sh`, starta om |

### Snabbstart (valfri dator, ingen hårdvara behövs)

1. Installera **Python 3.9 eller nyare** ([python.org](https://www.python.org/downloads/); på Linux oftast
   `sudo apt install python3 python3-venv python3-pip`).
2. Ladda ner projektet: på GitHub tryck **Code → Download ZIP** och packa upp, eller
   `git clone <repository-url>`.
3. Kör installationsskriptet en gång i projektmappen, sedan startskriptet:

   | | Installera (en gång) | Starta |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` betyder "ingen lamphårdvara ansluten". Utelämna det när ett ESP32-kort sitter i USB; programmet
   hittar det själv.

### Tangenter

| Tangent | Funktion |
| --- | --- |
| **Mellanslag** / Enter | Den stora knappen: det som händer härnäst (öppna inställningar, starta passet, ...) |
| **P** | Paus / fortsätt |
| **Esc** | **Nödstopp**: röda lampor och tystnad, alltid ett tryck |
| N / Backsteg | Nästa fas / tillbaka |

Allt går också att göra med musen. Klickers som fungerar som tangentbord går också bra. Hela listan (engelska):
[docs/ui.md](docs/ui.md).

### Användbara startval

Lägg dem efter startskriptet, skärmval efter `--`:

```text
scripts/start.sh --no-serial                      demo utan hårdvara
scripts/start.sh --serial-port COM7               välj USB-port själv (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang en        helskärm, engelska
scripts/start.sh -- --profile audience --display 1   publikskärm på skärm 2, inga knappar
```

På Windows används `scripts\start_windows.bat` i stället för `scripts/start.sh`.

## Dokumentation

Den tekniska dokumentationen är på engelska. Installationsguiderna finns på båda språken.

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | Index över all dokumentation |
| [docs/install/](docs/install/) | Installationsguider (svenska och engelska) |
| [structure.md](structure.md) | Var allt finns i källkoden |

## Utveckling

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
mypy
```

Regler och arkitektur: [CLAUDE.md](CLAUDE.md).

## Licens

Inte vald än. Tills en `LICENSE`-fil läggs till är alla rättigheter förbehållna upphovspersonen. Typsnittet Inter
följer med under SIL Open Font License (`assets/fonts/OFL.txt`).

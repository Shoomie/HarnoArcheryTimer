# Archery Timer (Bågskyttetimer)

[English](README.md) · **Svenska**

En öppen källkod-klocka för bågskytte. Den kör skjuttiden på tävlingar och träning, visar den på en TV eller
skärm och styr lampor och signalhorn via USB. Gjord för en liten bågskyttklubb och för frivilliga som inte är
tekniker: skärmen har en tydlig knapp för det som händer härnäst och en nödstopp-knapp som alltid syns.

- Fungerar på **Windows 10/11**, **Linux**, **Raspberry Pi** (2B och nyare, som TV-kiosk) och macOS.
- Svenskt och engelskt gränssnitt (svenska är standard).
- Tid, lampor och ljud fortsätter även om skärmprogrammet kraschar.
- Valfritt ESP32-kort för lampor och horn, valfria extra skärmar och flera enheter på samma nätverk.

> **Före en officiell tävling:** tiderna i `config/` är **platshållare**, inte bekräftade regler från World Archery /
> SBF. Kontrollera dem mot gällande regler och ändra TOML-filerna (klubbar kan lägga till egna förval utan kod).
> Systemet är provat från början till slut på en Windows-dator, en Linux-dator och en Raspberry Pi 2B med ESP32-C3- och
> WROOM-32D-moduler. Inte provat än: 4 timmars driftprov, ESP32-S3-kort och radiotest på lång räckvidd.

## Köra ett pass

1. Starta programmet (se Installera nedan). Tryck **Mellanslag** eller på den stora knappen: inställningarna öppnas.
2. Välj ett kort (till exempel *Inomhus 18 m*), välj linjer och antal omgångar och starta.
3. Den stora knappen säger alltid vad som händer härnäst: starta omgången, nästa omgång, fortsätt. **P** pausar.
   **Esc** är nödstopp: röda lampor och tystnad, alltid ett tryck, ingen bekräftelse.

Skärmen visar ett stort ljus (med en symbol, inte bara färg), nedräkningen, omgång och linje samt hårdvarans status i
klartext.

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
| S | Avsluta omgången |
| N / Backsteg | Nästa fas / tillbaka (Tillbaka heter *Ångra* i 5 sekunder efter Avsluta eller Nästa) |
| M / F1 | Meny: nytt pass, timers, inställningar, hårdvarustatus, nätverk, ljud, avsluta |

Allt går också att göra med musen. Klickers och fotpedaler som fungerar som tangentbord går också bra, liksom
knapparna på ESP32-modulerna. Hela listan (engelska): [docs/ui.md](docs/ui.md).

### Användbara startval

Lägg dem efter startskriptet, skärmval efter `--`:

```text
scripts/start.sh --no-serial                      demo utan hårdvara
scripts/start.sh --serial-port COM7               välj USB-port själv (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang en        helskärm, engelska
scripts/start.sh -- --profile audience --display 1   publikskärm på skärm 2, inga knappar
```

På Windows används `scripts\start_windows.bat` i stället för `scripts/start.sh`.

## Lampor, horn och fler enheter

Den tekniska dokumentationen är på engelska. Installationsguiderna finns på båda språken.

| Jag vill... | Läs |
| --- | --- |
| Koppla in trafikljus och horn (ESP32-kort, kopplingar, pinnar) | [docs/firmware.md](docs/firmware.md) |
| Flasha en ESP32-modul (Windows, Linux, macOS; ingen kompilator behövs) | [docs/flashing.md](docs/flashing.md): `scriptslash.bat` eller `sh scripts/flash.sh` |
| Ställa in horn och högtalare, ljudtest | [docs/audio.md](docs/audio.md) |
| Köra flera skärmar, datorer eller Pi som en timer (nätverk eller radio) | [docs/cluster.md](docs/cluster.md) |
| Trådlösa ljuslådor och fjärrknappar | [docs/mesh.md](docs/mesh.md) |

## Dokumentation

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

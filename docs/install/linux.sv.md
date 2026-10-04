# Installera på Linux (och macOS)

[English](linux.md) · [Windows](windows.sv.md) · [Raspberry Pi](raspberry-pi.sv.md) · [Tillbaka till README](../../README.sv.md)

För en Raspberry Pi som startar direkt in i timern, använd i stället [Raspberry Pi-guiden](raspberry-pi.sv.md).
Den här sidan gäller en vanlig Linux-dator med skrivbord (testat på Debian/Ubuntu-familjen; andra fungerar om de
har Python 3.9+).

## 1. Installera förkunskaper

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`. Arch: `sudo pacman -S git python sdl2`.

macOS: installera Python 3 från <https://www.python.org/downloads/> (eller `brew install python`).

## 2. Ladda ner projektet

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

Inget git? Ladda ner ZIP-filen från GitHub-sidan (**Code → Download ZIP**) och packa upp.

## 3. Installera (en gång)

```bash
scripts/setup_desktop.sh
```

Skriptet skapar en egen miljö i `.venv` och installerar timern i den. Om skriptet inte är körbart, kör
`bash scripts/setup_desktop.sh`.

## 4. Starta timern

```bash
scripts/start.sh
```

- Demo utan lamphårdvara: `scripts/start.sh --no-serial`
- Helskärm: `scripts/start.sh -- --fullscreen`
- Engelskt gränssnitt: `scripts/start.sh -- --lang en`
- Publikskärm på andra skärmen, utan knappar: `scripts/start.sh -- --profile audience --display 1`

Tangenter: **Mellanslag** = den stora knappen, **P** = paus, **Esc** = nödstopp. Se
[README](../../README.sv.md#tangenter).

## 5. Koppla in lampor och horn (valfritt)

1. Inget att göra för hand: `scripts/setup_desktop.sh` (steg 2) ger redan datorn åtkomst till kortet
   (seriegrupp plus en udev-regel som också håller ModemManager borta; frågar efter lösenordet en gång;
   `--no-system` hoppar över det) och `scripts/start.sh` fungerar utan utloggning. Om du hoppade över det, kör
   `sudo usermod -aG dialout $USER` och logga in igen.

2. Sätt i ESP32-kortet. Det hittas automatiskt. Vill du välja port själv: hitta den med
   `ls /dev/ttyACM* /dev/ttyUSB*` och starta med `scripts/start.sh --serial-port /dev/ttyACM0`.

Kortets firmware finns i [`firmware/`](../../firmware/); flasha ett nytt kort med [flashguiden](../flashing.md) (engelska).

## Uppdatera

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

Inställningar sparas i `~/.local/share/archerytimer` (macOS: `~/Library/Application Support/archerytimer`).

## Felsökning

| Problem | Gör så här |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` och kör setup igen |
| Inget fönster / SDL-fel | Kör i en skrivbordssession (inte över ren SSH); installera `libsdl2-2.0-0` |
| "Permission denied" på serieporten | Steg 5: gruppen `dialout`, logga ut och in |
| Inget ljud från datorns högtalare | Välj utgång i programmets ljudinställningar; ALSA/PulseAudio måste fungera i andra program först |
| Loggar | `~/.local/share/archerytimer/logs/` |

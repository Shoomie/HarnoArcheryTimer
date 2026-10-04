# Installera på Windows 10/11

[English](windows.md) · [Linux](linux.sv.md) · [Raspberry Pi](raspberry-pi.sv.md) · [Tillbaka till README](../../README.sv.md)

Tidsåtgång: cirka 10 minuter. Du behöver internet vid första installationen.

## 1. Installera Python

1. Gå till <https://www.python.org/downloads/> och ladda ner senaste Python 3 (3.9 eller nyare).
2. Kör installationsprogrammet. **Bocka i "Add python.exe to PATH"** på första sidan och tryck *Install Now*.

## 2. Ladda ner projektet

Välj ett av sätten:

- **ZIP (enklast):** på GitHub-sidan tryck **Code → Download ZIP**, högerklicka filen och välj *Extrahera alla*.
  Lägg mappen någonstans enkelt, till exempel `C:\ArcheryTimer`.
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. Installera (en gång)

Öppna projektmappen och **dubbelklicka på `scripts\setup_windows.bat`**. Den skapar en egen Python-miljö i `.venv`
och installerar det timern behöver. Vänta tills det står "Done".

Om Windows SmartScreen varnar för filen, välj *Mer information → Kör ändå* (det är ett vanligt textskript som du
kan läsa i Anteckningar).

## 4. Starta timern

Dubbelklicka på **`scripts\start_windows.bat`**. Ett fönster med timern öppnas.

- Ingen lamphårdvara ännu? Starta från en terminal med `scripts\start_windows.bat --no-serial` för en demo.
- Helskärm på en TV: `scripts\start_windows.bat -- --fullscreen`
- Engelskt gränssnitt: `scripts\start_windows.bat -- --lang en`
- Andra skärmen för publiken, utan knappar: `scripts\start_windows.bat -- --profile audience --display 1`

(För en genväg på skrivbordet: högerklicka `start_windows.bat` → *Skicka till → Skrivbord (skapa genväg)*.)

Tangenter: **Mellanslag** = den stora knappen, **P** = paus, **Esc** = nödstopp. Se
[README](../../README.sv.md#tangenter).

## 5. Koppla in lampor och horn (valfritt)

Sätt ESP32-kortet i en USB-port. Programmet hittar det automatiskt. Om inte:

1. Öppna *Enhetshanteraren → Portar (COM och LPT)* och notera porten, till exempel `COM7`.
2. Starta med `scripts\start_windows.bat --serial-port COM7`.

Vissa billiga kort behöver en USB-seriell drivrutin (CH340 eller CP210x); om ingen COM-port dyker upp, installera
drivrutinen från chiptillverkaren. Kortets firmware finns i [`firmware/`](../../firmware/); flasha ett nytt kort med [flashguiden](../flashing.md) (engelska).

## Uppdatera

Ladda ner nya ZIP-filen (eller `git pull`) och kör `scripts\setup_windows.bat` igen. Dina inställningar sparas i din
användarprofil (`%LOCALAPPDATA%\archerytimer`), inte i projektmappen.

## Felsökning

| Problem | Gör så här |
| --- | --- |
| "Python was not found" | Installera om Python och bocka i *Add python.exe to PATH*, eller kör setup igen efter omstart |
| Fönstret öppnas och stängs direkt | Kör `scripts\start_windows.bat` från en terminal (`cmd`) för att se felmeddelandet |
| Hårdvarustatus visar "inga lampor" | Kontrollera USB-kabeln (den måste klara data), porten och drivrutinen; se steg 5 |
| Loggar | `%LOCALAPPDATA%\archerytimer\logs` (klistra in sökvägen i Utforskaren) |

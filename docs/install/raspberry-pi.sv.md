# Installera på Raspberry Pi (TV-kiosk)

[English](raspberry-pi.md) · [Windows](windows.sv.md) · [Linux](linux.sv.md) · [Tillbaka till README](../../README.sv.md)

Resultat: Pi:n startar direkt in i timern på TV:n, utan inloggning med tangentbord. Timerkärnan körs som en
bakgrundstjänst och håller lampor och ljud igång även om skärmprogrammet startar om.

**Testat mål:** Raspberry Pi 2 Model B, Raspberry Pi OS Lite 32-bit (Trixie), HDMI-TV. Andra Pi-modeller bör
fungera men är inte testade. Tidsåtgång: cirka 30 minuter.

> Installationen har körts på en riktig Pi 2B en gång (skärmen fungerar). Ljud, GPIO-knappar och USB-hårdvaran är
> inte testade på en Pi än. Se [deployment.md](../deployment.md) (engelska) för vad som är verifierat.

## Det här behöver du

- Raspberry Pi med nätadapter, microSD-kort (8 GB eller mer), HDMI-kabel och en TV eller skärm
- En dator för att förbereda kortet, och nätverk till Pi:n (kabel är enklast) under installationen
- Valfritt: ESP32-kortet för lampor/horn i en USB-port, ett USB-tangentbord eller en klicker

## 1. Skriv operativsystemet till kortet

1. Installera **Raspberry Pi Imager** på din dator från <https://www.raspberrypi.com/software/>.
2. Välj din Pi-modell, sedan *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***.
3. Välj SD-kortet, tryck *Next* och sedan *Edit settings* (anpassa) och ange:
   - ett **värdnamn** (till exempel `archerytimer`) samt **användarnamn och lösenord** (kom ihåg dem; den här
     användaren blir kioskanvändaren),
   - ditt **Wi-Fi** om du inte använder kabel, och din tidszon,
   - *Services → Enable SSH*.
4. Skriv kortet, sätt det i Pi:n, anslut HDMI och nätverk och starta. Vänta ett par minuter på första
   uppstarten.

## 2. Logga in

Från din dator (Windows 10/11 och Linux har båda `ssh`):

```bash
ssh <användarnamn>@archerytimer.local
```

(Hittas inte namnet, använd Pi:ns IP-adress från din router.) Du kan också koppla ett tangentbord till Pi:n och
logga in på TV:n.

## 3. Ladda ner projektet

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. Kör installationsskriptet

```bash
sudo bash scripts/install_pi.sh
```

Det tar flera minuter. Skriptet installerar nödvändiga paket, kopierar programmet till `/opt/archerytimer`, ställer
in bakgrundstjänsten, slår på grafikdrivrutinen för GPU:n och gör att Pi:n loggar in automatiskt på första
konsolen och startar timern där. När det är klart, starta om:

```bash
sudo reboot
```

Efter omstarten dyker timern upp på TV:n av sig själv. Använd mus eller tangentbord (Mellanslag = stora knappen,
Esc = nödstopp).

Val: `--no-ui` för en låda med bara lampor/ljud utan skärm, `--user NAMN` för att välja kioskanvändare. Kör
`scripts/install_pi.sh --help` för listan.

## 5. Koppla in lampor och horn (valfritt)

Sätt ESP32-kortet i en USB-port på Pi:n. Det hittas automatiskt (kioskanvändaren ingår redan i gruppen
`dialout`). Status syns i programmets hårdvarumeny. Firmwaren i [`firmware/`](../../firmware/) är **inte provad på
riktig hårdvara än**.

## Inställningar

Extra startval finns i två små filer. Redigera dem med `sudo nano`:

| Fil | Används för | Exempel |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | bakgrundskärnan | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | skärmen | `UI_ARGS="--lang en --profile audience"` |

Aktivera efter ändring: `sudo systemctl restart archerytimer-core` och starta om (eller logga ut från konsolen)
för skärmen. Flera Pi:ar tillsammans (en ledare, flera följare): se [cluster.md](../cluster.md) (engelska).

## Uppdatera

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

Dina inställningar och filerna i `/etc/archerytimer` behålls.

**Från en Windows-dator**, utan git på Pi:n: `.\scripts\deploy_to_pi.ps1 -Pi användarnamn@archerytimer.local`
(kopierar projektet och kör installationen; lägg till `-Reboot` för att starta om efteråt).

## Få ett vanligt skal på TV:n

Kiosken tar över Pi:ns första konsol. För att arbeta på Pi:n, logga in via **SSH** från en annan dator, eller skapa
filen `~/.no-kiosk` (`touch ~/.no-kiosk`) och starta om för en vanlig prompt. Ta bort filen och starta om för att
få tillbaka timern.

## Felsökning

| Problem | Gör så här |
| --- | --- |
| Svart skärm efter omstart | Vänta 1-2 minuter efter start. Kontrollera HDMI. Fortsätter det: logga in via SSH, kör `journalctl -u archerytimer-core -n 50` och titta i `~/.local/share/archerytimer/logs/ui.log` |
| Skärmen blir svart bara om TV:n slås på efter Pi:n | Lägg till `hdmi_force_hotplug=1` i `/boot/firmware/config.txt`, starta om |
| Skärmen fungerar men "ingen kontakt med kärnan" | `systemctl status archerytimer-core`; starta om med `sudo systemctl restart archerytimer-core` |
| Inga lampor/horn | Kontrollera att USB-kabeln klarar data; `ls /dev/ttyACM* /dev/ttyUSB*` ska visa en enhet |
| Kontrollera miljön | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| Ta bort allt | `sudo bash scripts/uninstall_pi.sh` (behåller dina inställningar) |

Loggar live: `journalctl -u archerytimer-core -f`. Mer om internt: [deployment.md](../deployment.md).

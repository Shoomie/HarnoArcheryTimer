# Raspberry Pi پر انسٹال کریں (ٹی وی کیوسک)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · [हिन्दी](raspberry-pi.hi.md) · [Español](raspberry-pi.es.md) · [Français](raspberry-pi.fr.md) · [العربية](raspberry-pi.ar.md) · [বাংলা](raspberry-pi.bn.md) · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · **اردو**

[Windows](windows.ur.md) · [Linux](linux.ur.md) · [README پر واپس](../../README.ur.md)

نتیجہ: Pi کی بورڈ سے لاگ ان کیے بغیر سیدھا ٹی وی پر ٹائمر میں بوٹ ہوتا ہے۔ ٹائمر کور بیک گراؤنڈ سروس کے طور پر چلتا ہے
اور ڈسپلے پروگرام ری اسٹارٹ ہو جائے تب بھی لائٹس اور آواز چلتی رہتی ہیں۔

**آزمایا گیا ہدف:** Raspberry Pi 2 Model B، Raspberry Pi OS Lite 32-bit (Trixie)، HDMI ٹی وی۔ دوسرے Pi ماڈل چلنے چاہئیں، مگر آزمائے نہیں گئے۔
درکار وقت: تقریباً 30 منٹ۔

> انسٹالر کیا کیا ترتیب دیتا ہے، تفصیل سے: [deployment.md](../deployment.md) (انگریزی میں)۔

## آپ کو کیا چاہیے

- پاور سپلائی کے ساتھ Raspberry Pi، microSD کارڈ (8 GB یا زیادہ)، HDMI کیبل اور ٹی وی یا مانیٹر
- کارڈ تیار کرنے کے لیے ایک کمپیوٹر، اور انسٹالیشن کے دوران Pi کے لیے نیٹ ورک کنکشن (کیبل سب سے آسان ہے)
- اختیاری: USB پورٹ میں لائٹ/ہارن والا ESP32 بورڈ، USB کی بورڈ یا کلکر

## 1. کارڈ پر آپریٹنگ سسٹم لکھیں

1. اپنے کمپیوٹر پر <https://www.raspberrypi.com/software/> سے **Raspberry Pi Imager** انسٹال کریں۔
2. اپنا Pi ماڈل چنیں، پھر *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***۔
3. SD کارڈ چنیں، *Next* دبائیں، پھر *Edit settings* (OS حسب ضرورت) میں یہ طے کریں:
   - ایک **hostname** (مثلاً `archerytimer`) اور **یوزر نیم اور پاس ورڈ** (یاد رکھیں؛ یہی یوزر کیوسک یوزر بنے گا)،
   - اگر کیبل نہ ہو تو اپنا **Wi-Fi**، اور اپنا ٹائم زون،
   - *Services → Enable SSH*۔
4. کارڈ لکھیں، Pi میں لگائیں، HDMI اور نیٹ ورک جوڑیں اور پاور آن کریں۔ پہلے بوٹ کے لیے چند منٹ انتظار کریں۔

## 2. لاگ ان کریں

اپنے کمپیوٹر سے (Windows 10/11 اور Linux دونوں میں `ssh` موجود ہے):

```bash
ssh <username>@archerytimer.local
```

(اگر نام نہ ملے تو اپنے راؤٹر سے Pi کا IP پتہ استعمال کریں۔) یا Pi میں کی بورڈ لگا کر ٹی وی پر لاگ ان کریں۔

## 3. پروجیکٹ ڈاؤن لوڈ کریں

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. انسٹالر چلائیں

```bash
sudo bash scripts/install_pi.sh
```

اس میں کئی منٹ لگتے ہیں۔ یہ ضروری پیکجز انسٹال کرتا ہے، پروگرام کو `/opt/archerytimer` میں کاپی کرتا ہے، بیک گراؤنڈ سروس ترتیب دیتا ہے،
GPU ڈسپلے اوورلے فعال کرتا ہے، اور Pi کو اس طرح بناتا ہے کہ وہ پہلے کنسول پر خود لاگ ان ہو کر وہیں ٹائمر شروع کرے۔ مکمل ہونے پر ری بوٹ کریں:

```bash
sudo reboot
```

ری بوٹ کے بعد ٹائمر ٹی وی پر خود ظاہر ہو جاتا ہے۔ ماؤس یا کی بورڈ استعمال کریں (Space = بڑا بٹن، Esc = ہنگامی اسٹاپ)۔

آپشنز: بغیر ڈسپلے کے صرف لائٹ/آواز والے باکس کے لیے `--no-ui`، کیوسک یوزر چننے کے لیے `--user NAME`۔ فہرست کے لیے
`scripts/install_pi.sh --help` چلائیں۔

## 5. لائٹس اور ہارن جوڑیں (اختیاری)

ESP32 بورڈ کو Pi کے USB پورٹ میں لگائیں۔ وہ خود مل جاتا ہے (کیوسک یوزر پہلے سے `dialout` گروپ میں ہے)۔ حالت پروگرام کے ہارڈویئر مینو میں نظر آتی ہے۔
نیا بورڈ فلیش کرنے کے لیے [فلیشنگ گائیڈ](../flashing.md) (انگریزی میں) دیکھیں؛ فرم ویئر کا سورس [`firmware/`](../../firmware/) میں ہے۔

## سیٹنگز

اضافی اسٹارٹ آپشنز دو چھوٹی فائلوں میں رہتے ہیں۔ انہیں `sudo nano` سے تبدیل کریں:

| فائل | کس لیے | مثال |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | بیک گراؤنڈ کور | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | ڈسپلے | `UI_ARGS="--lang sv --profile audience"` |

تبدیلی کے بعد: `sudo systemctl restart archerytimer-core`، اور ڈسپلے کے لیے ری بوٹ کریں (یا کنسول سے لاگ آؤٹ کریں)۔ کئی Pi کو ساتھ چلانے
(ایک لیڈر، باقی فالوور) کے لیے [cluster.md](../cluster.md) (انگریزی میں) دیکھیں۔

## اپ ڈیٹ

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

آپ کی سیٹنگز اور `/etc/archerytimer` کی فائلیں برقرار رہتی ہیں۔

**Windows کمپیوٹر سے**، Pi پر git کے بغیر: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(پروجیکٹ کاپی کرتا ہے اور انسٹالر چلاتا ہے؛ بعد میں ری اسٹارٹ کے لیے `-Reboot` شامل کریں)۔

## ٹی وی پر عام شیل حاصل کرنا

کیوسک Pi کا پہلا کنسول لے لیتا ہے۔ Pi پر براہِ راست کام کرنے کے لیے دوسرے کمپیوٹر سے **SSH** کے ذریعے لاگ ان کریں، یا فائل `~/.no-kiosk` بنائیں
(`touch ~/.no-kiosk`) اور عام پرامپٹ کے لیے ری بوٹ کریں۔ ٹائمر واپس لانے کے لیے فائل حذف کر کے ری بوٹ کریں۔

## مسائل کا حل

| مسئلہ | کیا کریں |
| --- | --- |
| ری بوٹ کے بعد کالی اسکرین | پاور آن کے بعد 1-2 منٹ انتظار کریں۔ HDMI چیک کریں۔ پھر بھی نہ جائے تو SSH سے لاگ ان کریں، `journalctl -u archerytimer-core -n 50` چلائیں اور `~/.local/share/archerytimer/logs/ui.log` دیکھیں |
| اسکرین صرف تب کالی رہتی ہے جب ٹی وی Pi کے بعد آن کیا جائے | `/boot/firmware/config.txt` میں `hdmi_force_hotplug=1` شامل کریں اور ری بوٹ کریں |
| ڈسپلے چلتا ہے مگر "no connection to core" آتا ہے | `systemctl status archerytimer-core`؛ `sudo systemctl restart archerytimer-core` سے ری اسٹارٹ کریں |
| لائٹس/ہارن نہیں | چیک کریں کہ USB کیبل ڈیٹا منتقل کرتی ہے؛ `ls /dev/ttyACM* /dev/ttyUSB*` میں ایک ڈیوائس نظر آنی چاہیے |
| ماحول کی جانچ | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| سب کچھ ہٹانا | `sudo bash scripts/uninstall_pi.sh` (آپ کی سیٹنگز رکھتا ہے) |

لائیو لاگ: `journalctl -u archerytimer-core -f`۔ مزید اندرونی تفصیل: [deployment.md](../deployment.md) (انگریزی میں)۔

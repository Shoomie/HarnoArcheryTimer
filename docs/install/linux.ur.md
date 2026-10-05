# ڈیسک ٹاپ Linux (اور macOS) پر انسٹال کریں

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · [Français](linux.fr.md) · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · [Русский](linux.ru.md) · **اردو**

[Windows](windows.ur.md) · [Raspberry Pi](raspberry-pi.ur.md) · [README پر واپس](../../README.ur.md)

جو Raspberry Pi سیدھا ٹائمر میں بوٹ ہوتا ہے اس کے لیے بجائے اس کے [Raspberry Pi گائیڈ](raspberry-pi.ur.md) استعمال کریں۔
یہ صفحہ ڈیسک ٹاپ والے عام Linux پی سی یا لیپ ٹاپ کے لیے ہے (Debian/Ubuntu خاندان پر آزمایا گیا؛ دوسرے بھی چلتے ہیں اگر ان میں Python 3.9+ ہو)۔

## 1. ضروری چیزیں انسٹال کریں

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`۔ Arch: `sudo pacman -S git python sdl2`۔

macOS: <https://www.python.org/downloads/> سے Python 3 انسٹال کریں (یا `brew install python`)۔

## 2. پروجیکٹ ڈاؤن لوڈ کریں

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

git نہیں ہے؟ GitHub پیج سے ZIP ڈاؤن لوڈ کریں (**Code → Download ZIP**) اور کھولیں۔

## 3. سیٹ اپ (ایک بار)

```bash
scripts/setup_desktop.sh
```

یہ `.venv` میں ایک الگ ماحول بناتا ہے اور اس میں ٹائمر انسٹال کرتا ہے۔ اگر اسکرپٹ قابلِ عمل (executable) نہ ہو تو اسے `bash scripts/setup_desktop.sh` سے چلائیں۔

## 4. ٹائمر شروع کریں

```bash
scripts/start.sh
```

- لائٹ ہارڈویئر کے بغیر ڈیمو: `scripts/start.sh --no-serial`
- فل اسکرین: `scripts/start.sh -- --fullscreen`
- سویڈش انٹرفیس: `scripts/start.sh -- --lang sv` (زبان سیٹنگز مینو سے بھی بدلی جا سکتی ہے)
- دوسرے مانیٹر پر حاضرین کی اسکرین، بغیر کنٹرول: `scripts/start.sh -- --profile audience --display 1`

کلیدیں: **Space** = بڑا بٹن، **P** = روکنا، **Esc** = ہنگامی اسٹاپ۔ [README](../../README.ur.md) دیکھیں۔

## 5. لائٹس اور ہارن جوڑیں (اختیاری)

1. ہاتھ سے کچھ کرنے کی ضرورت نہیں: `scripts/setup_desktop.sh` (مرحلہ 3) پہلے ہی اس کمپیوٹر کو بورڈ تک رسائی دے چکا ہے
   (سیریل گروپ اور ایک udev اصول، جو ModemManager کو بھی بورڈ سے دور رکھتا ہے؛ یہ ایک بار آپ کا پاس ورڈ مانگتا ہے؛
   `--no-system` اسے چھوڑ دیتا ہے) اور `scripts/start.sh` لاگ آؤٹ کیے بغیر چلتا ہے۔ اگر آپ نے اسے چھوڑ دیا تھا تو
   `sudo usermod -aG dialout $USER` چلائیں اور دوبارہ لاگ ان کریں۔

2. ESP32 بورڈ لگائیں۔ وہ خود مل جاتا ہے۔ پورٹ خود چننا ہو تو اسے `ls /dev/ttyACM* /dev/ttyUSB*` سے ڈھونڈیں اور
   `scripts/start.sh --serial-port /dev/ttyACM0` کے ساتھ شروع کریں۔

بورڈ کا فرم ویئر [`firmware/`](../../firmware/) میں ہے؛ نیا بورڈ [فلیشنگ گائیڈ](../flashing.md) (انگریزی میں) سے فلیش کریں۔

## اپ ڈیٹ

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

سیٹنگز `~/.local/share/archerytimer` میں رہتی ہیں (macOS: `~/Library/Application Support/archerytimer`)۔

## مسائل کا حل

| مسئلہ | کیا کریں |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` چلائیں اور سیٹ اپ دوبارہ کریں |
| ونڈو نہیں کھلتی / SDL خرابی | اسے ڈیسک ٹاپ سیشن کے اندر چلائیں (سادہ SSH پر نہیں)؛ `libsdl2-2.0-0` انسٹال کریں |
| سیریل پورٹ پر "Permission denied" | مرحلہ 5: `dialout` گروپ، پھر لاگ آؤٹ کر کے دوبارہ لاگ ان کریں |
| پی سی کے اسپیکروں سے آواز نہیں | پروگرام کی ساؤنڈ سیٹنگز میں آؤٹ پٹ ڈیوائس دیکھیں؛ پہلے دوسری ایپس میں ALSA/PulseAudio کا چلنا ضروری ہے |
| لاگ | `~/.local/share/archerytimer/logs/` |

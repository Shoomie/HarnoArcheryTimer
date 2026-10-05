# Archery Timer (تیر اندازی ٹائمر)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · [Português](README.pt.md) · [Русский](README.ru.md) · **اردو**

تیر اندازی کے لیے ایک اوپن سورس شوٹنگ کلاک۔ یہ مقابلوں اور مشق میں شوٹنگ کا وقت چلاتا ہے، اسے ٹی وی یا مانیٹر پر دکھاتا ہے،
اور USB کے ذریعے ٹریفک لائٹس اور ہارن کو چلاتا ہے۔ یہ ایک چھوٹے تیر اندازی کلب کے لیے بنایا گیا ہے اور رضاکار اسے چلاتے ہیں،
اس لیے اسکرین پر "اگلا کیا ہوگا" بتانے والا ایک ہی واضح بڑا بٹن ہے اور ہمیشہ نظر آنے والا ہنگامی اسٹاپ۔

- **Windows 10/11**، **Linux**، **Raspberry Pi** (2B اور اس سے اوپر، ٹی وی کیوسک کے طور پر) اور macOS پر چلتا ہے۔
- انٹرفیس انگریزی (ڈیفالٹ) اور سویڈش میں۔
- ڈسپلے پروگرام کریش ہو جائے تب بھی ٹائمر، لائٹس اور آواز چلتی رہتی ہیں۔
- لائٹس اور ہارن کے لیے اختیاری ESP32 بورڈ، اختیاری دوسری اسکرینیں، اور ایک ہی نیٹ ورک پر کئی ڈیوائسز۔

> **سرکاری مقابلے سے پہلے:** `config/` میں دیے گئے اوقات **عارضی قدریں (placeholder)** ہیں، World Archery / SBF کے تصدیق شدہ قواعد نہیں۔
> انہیں موجودہ قواعد سے ملا کر دیکھیں اور TOML فائلیں تبدیل کریں (کلب کوڈ بدلے بغیر اپنے پری سیٹ شامل کر سکتے ہیں)۔ نظام کو ایک Windows پی سی،
> ایک Linux پی سی اور ESP32-C3 اور WROOM-32D ماڈیولز والے Raspberry Pi 2B پر شروع سے آخر تک آزمایا گیا ہے۔ ابھی نہیں آزمایا گیا:
> 4 گھنٹے کی مسلسل رن، ESP32-S3 بورڈ، اور لمبے فاصلے کے ریڈیو ٹیسٹ۔

## سیشن چلانا

1. پروگرام شروع کریں (نیچے "انسٹال" دیکھیں)۔ **Space** یا بڑا بٹن دبائیں: سیٹ اپ کھلے گا۔
2. ایک کارڈ چنیں (مثلاً *Indoor 18 m*)، لائنیں اور راؤنڈ (اینڈ) کی تعداد منتخب کریں، پھر شروع کریں۔
3. بڑا بٹن ہمیشہ بتاتا ہے کہ آگے کیا ہوگا: اینڈ شروع کریں، اگلا اینڈ، دوبارہ شروع کریں۔ **P** سے روکیں۔ **Esc** ہنگامی اسٹاپ ہے:
   سرخ لائٹس اور خاموشی، ہمیشہ ایک ہی بار دبانے سے، بغیر کسی تصدیق کے۔

اسکرین پر ایک بڑی لائٹ (صرف رنگ نہیں، علامت کے ساتھ)، الٹی گنتی، اینڈ اور لائن، اور ہارڈویئر کی حالت سادہ الفاظ میں دکھائی جاتی ہے۔

## انسٹال

اپنا سسٹم چنیں۔ ہر گائیڈ بالکل شروع سے چلتے ہوئے ٹائمر تک قدم بہ قدم لے جاتی ہے۔

| سسٹم | گائیڈ | مختصراً |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.ur.md](docs/install/windows.ur.md) | Python انسٹال کریں، پروجیکٹ ڈاؤن لوڈ کریں، `scripts\setup_windows.bat` پر ڈبل کلک کریں، پھر `scripts\start_windows.bat` |
| **Linux** (اور macOS) | [docs/install/linux.ur.md](docs/install/linux.ur.md) | `scripts/setup_desktop.sh`، پھر `scripts/start.sh` |
| **Raspberry Pi** (ٹی وی کیوسک) | [docs/install/raspberry-pi.ur.md](docs/install/raspberry-pi.ur.md) | Pi OS Lite فلیش کریں، `git clone`، `sudo scripts/install_pi.sh`، ری بوٹ |

### فوری آغاز (کوئی بھی ڈیسک ٹاپ، ہارڈویئر کی ضرورت نہیں)

1. **Python 3.9 یا نیا** انسٹال کریں ([python.org](https://www.python.org/downloads/)؛ Linux پر عموماً
   `sudo apt install python3 python3-venv python3-pip`)۔
2. پروجیکٹ ڈاؤن لوڈ کریں: GitHub پر **Code → Download ZIP** دبا کر کھولیں، یا
   `git clone <repository-url>`۔
3. پروجیکٹ فولڈر میں ایک بار سیٹ اپ اسکرپٹ چلائیں، پھر اسٹارٹ اسکرپٹ:

   | | سیٹ اپ (ایک بار) | اسٹارٹ |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` کا مطلب ہے "کوئی لائٹ ہارڈویئر جڑا ہوا نہیں"۔ ESP32 بورڈ لگا ہو تو اسے ہٹا دیں؛ پروگرام اسے خود ڈھونڈ لیتا ہے۔

### کنٹرول

| کلید | کام |
| --- | --- |
| **Space** / Enter | بڑا بٹن: جو بھی اگلا مرحلہ ہو (سیٹ اپ کھولنا، اینڈ شروع کرنا، ...) |
| **P** | روکیں / دوبارہ چلائیں |
| **Esc** | **ہنگامی اسٹاپ**: سرخ لائٹس اور خاموشی، ہمیشہ ایک ہی بار دبانے سے |
| S | اینڈ روکیں |
| N / Backspace | اگلا مرحلہ / پیچھے (Stop یا Next کے بعد 5 سیکنڈ تک "پیچھے" بٹن *Undo* دکھاتا ہے) |
| M / F1 | مینو: نیا سیشن، ٹائمر، سیٹنگز، ہارڈویئر کی حالت، نیٹ ورک، آواز، باہر نکلیں |

سب کچھ ماؤس سے بھی چلتا ہے۔ کی بورڈ کی طرح کام کرنے والے پریزنٹیشن کلکر اور فٹ پیڈل بھی چلتے ہیں، اور ESP32 ماڈیولز کے بٹن بھی۔
مکمل فہرست: [docs/ui.md](docs/ui.md) (انگریزی میں)۔

### کارآمد اسٹارٹ آپشنز

انہیں اسٹارٹ اسکرپٹ کے بعد لگائیں، ڈسپلے کے آپشنز `--` کے بعد:

```text
scripts/start.sh --no-serial                      ہارڈویئر کے بغیر ڈیمو
scripts/start.sh --serial-port COM7               USB پورٹ خود چنیں (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        فل اسکرین، سویڈش انٹرفیس
scripts/start.sh -- --profile audience --display 1   دوسرے مانیٹر پر حاضرین کی اسکرین، کوئی کنٹرول نہیں
```

Windows پر `scripts/start.sh` کی جگہ `scripts\start_windows.bat` استعمال کریں۔

## لائٹس، ہارن اور مزید ڈیوائسز

تکنیکی دستاویزات انگریزی میں ہیں۔ انسٹال گائیڈز 11 زبانوں میں موجود ہیں۔

| میں چاہتا/چاہتی ہوں... | پڑھیں |
| --- | --- |
| ٹریفک لائٹس اور ہارن جوڑنا (ESP32 بورڈ، وائرنگ، پن) | [docs/firmware.md](docs/firmware.md) |
| ESP32 ماڈیول فلیش کرنا (Windows، Linux، macOS؛ کمپائلر کی ضرورت نہیں) | [docs/flashing.md](docs/flashing.md): `scripts\flash.bat` یا `sh scripts/flash.sh` |
| ہارن اور اسپیکر ترتیب دینا، ساؤنڈ ٹیسٹ | [docs/audio.md](docs/audio.md) |
| کئی اسکرینیں، پی سی یا Pi ایک ٹائمر کے طور پر چلانا (LAN یا ریڈیو) | [docs/cluster.md](docs/cluster.md) |
| وائرلیس لائٹ باکس اور ریموٹ بٹن | [docs/mesh.md](docs/mesh.md) |

## دستاویزات

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | تمام دستاویزات کی فہرست |
| [docs/install/](docs/install/) | انسٹال گائیڈز (11 زبانیں) |
| [docs/ui.md](docs/ui.md) | اسکرینیں، کلیدیں، ڈسپلے پروفائل |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | USB سیریل پروٹوکول؛ کور سے ڈسپلے تک پروٹوکول |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Raspberry Pi کی اندرونی تفصیل؛ وقت اور رینڈرنگ کی پیمائش |
| [structure.md](structure.md) | سورس ٹری میں کون سی چیز کہاں ہے |

## ریپوزٹری کی ساخت

```text
src/archerytimer/   پروگرام (کور سروس، UI کلائنٹ، ہارڈویئر، آڈیو، IPC)
config/             وقت کی ترتیبیں اور سیٹ اپ پری سیٹ (TOML، عارضی)
locales/            انٹرفیس کی تمام تحریر، en.toml اور sv.toml
assets/             فونٹ (Inter، OFL)
firmware/           ESP32 فرم ویئر (PlatformIO)، بنی بنائی امیجز، مشترکہ ٹیسٹ ویکٹر
scripts/            انسٹال/اسٹارٹ اسکرپٹس، Raspberry Pi انسٹالر، فلیشنگ مینو، بینچ مارک
docs/               دستاویزات
tests/  tools/      ٹیسٹ سوئٹ، میش سمیولیٹر
```

## ڈیولپمنٹ

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # ٹیسٹ (کچھ Windows پر چھوڑ دیے جاتے ہیں)
ruff check . && ruff format --check .
mypy
```

دستاویزات یا انٹرفیس کا ترجمہ کرنے کے لیے [CONTRIBUTING.md](CONTRIBUTING.md) دیکھیں۔ پروجیکٹ کے قواعد اور آرکیٹیکچر: [CLAUDE.md](CLAUDE.md)۔
بینچ مارک: [docs/benchmarks.md](docs/benchmarks.md)۔

## لائسنس

MIT ([LICENSE](LICENSE) دیکھیں): کسی بھی مقصد کے لیے، کہیں بھی، استعمال، نقل، تبدیلی، شیئر اور فروخت کے لیے آزاد۔ اسی لائسنس کے تحت تعاون کا خیرمقدم ہے۔
تیسرے فریق کے حصے اپنے اپنے کھلے لائسنس برقرار رکھتے ہیں، جو [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) میں درج ہیں (مثلاً Inter فونٹ، `assets/fonts/OFL.txt`)۔

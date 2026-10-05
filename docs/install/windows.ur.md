# Windows 10/11 پر انسٹال کریں

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · [हिन्दी](windows.hi.md) · [Español](windows.es.md) · [Français](windows.fr.md) · [العربية](windows.ar.md) · [বাংলা](windows.bn.md) · [Português](windows.pt.md) · [Русский](windows.ru.md) · **اردو**

[Linux](linux.ur.md) · [Raspberry Pi](raspberry-pi.ur.md) · [README پر واپس](../../README.ur.md)

درکار وقت: تقریباً 10 منٹ۔ انٹرنیٹ صرف پہلی بار سیٹ اپ کے لیے چاہیے۔

## 1. Python انسٹال کریں

1. <https://www.python.org/downloads/> پر جائیں اور Python 3 کا تازہ ترین ورژن (3.9 یا نیا) ڈاؤن لوڈ کریں۔
2. انسٹالر چلائیں۔ پہلی اسکرین پر **"Add python.exe to PATH" پر ٹک لگائیں**، پھر *Install Now* دبائیں۔

## 2. پروجیکٹ ڈاؤن لوڈ کریں

کوئی ایک طریقہ چنیں:

- **ZIP (سب سے آسان):** GitHub پیج پر **Code → Download ZIP** دبائیں، پھر فائل پر رائٹ کلک کر کے *Extract All* چنیں۔
  فولڈر کو کسی آسان جگہ رکھیں، مثلاً `C:\ArcheryTimer`۔
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. سیٹ اپ (ایک بار)

پروجیکٹ فولڈر کھولیں اور **`scripts\setup_windows.bat` پر ڈبل کلک کریں**۔ یہ `.venv` میں ایک الگ Python ماحول بناتا ہے اور ٹائمر کے لیے ضروری چیزیں انسٹال کرتا ہے۔
"Done" نظر آنے تک انتظار کریں۔

اگر Windows SmartScreen فائل کے بارے میں خبردار کرے تو *More info → Run anyway* چنیں (یہ ایک سادہ ٹیکسٹ اسکرپٹ ہے جسے آپ Notepad میں پڑھ سکتے ہیں)۔

## 4. ٹائمر شروع کریں

**`scripts\start_windows.bat`** پر ڈبل کلک کریں۔ ٹائمر والی ایک ونڈو کھلے گی۔

- ابھی لائٹ ہارڈویئر نہیں ہے؟ ڈیمو کے لیے ٹرمینل سے `scripts\start_windows.bat --no-serial` کے ساتھ چلائیں۔
- ٹی وی پر فل اسکرین: `scripts\start_windows.bat -- --fullscreen`
- سویڈش انٹرفیس: `scripts\start_windows.bat -- --lang sv` (زبان سیٹنگز مینو سے بھی بدلی جا سکتی ہے)
- حاضرین کے لیے دوسرا مانیٹر، بغیر کنٹرول: `scripts\start_windows.bat -- --profile audience --display 1`

(ڈیسک ٹاپ شارٹ کٹ بنانے کے لیے: `start_windows.bat` پر رائٹ کلک → *Send to → Desktop (create shortcut)*۔)

کلیدیں: **Space** = بڑا بٹن، **P** = روکنا، **Esc** = ہنگامی اسٹاپ۔ [README](../../README.ur.md) دیکھیں۔

## 5. لائٹس اور ہارن جوڑیں (اختیاری)

ESP32 بورڈ کو USB پورٹ میں لگائیں۔ پروگرام اسے خود ڈھونڈ لیتا ہے۔ اگر نہ ڈھونڈے تو:

1. *Device Manager → Ports (COM & LPT)* کھولیں اور پورٹ نوٹ کریں، مثلاً `COM7`۔
2. `scripts\start_windows.bat --serial-port COM7` کے ساتھ شروع کریں۔

کچھ سستے بورڈز کو USB-سیریل ڈرائیور (CH340 یا CP210x) چاہیے ہوتا ہے؛ اگر کوئی COM پورٹ ظاہر نہ ہو تو چپ بنانے والے سے ڈرائیور انسٹال کریں۔
بورڈ کا فرم ویئر [`firmware/`](../../firmware/) میں ہے؛ نیا بورڈ [فلیشنگ گائیڈ](../flashing.md) (انگریزی میں) سے فلیش کریں۔

## اپ ڈیٹ

نیا ZIP ڈاؤن لوڈ کریں (یا `git pull`) اور دوبارہ `scripts\setup_windows.bat` چلائیں۔ آپ کی سیٹنگز آپ کے یوزر پروفائل
(`%LOCALAPPDATA%\archerytimer`) میں رہتی ہیں، پروجیکٹ فولڈر میں نہیں۔

## مسائل کا حل

| مسئلہ | کیا کریں |
| --- | --- |
| "Python was not found" | Python دوبارہ انسٹال کریں اور *Add python.exe to PATH* پر ٹک لگائیں، یا پی سی ری اسٹارٹ کر کے سیٹ اپ دوبارہ چلائیں |
| ونڈو کھل کر بند ہو جاتی ہے | خرابی کا پیغام دیکھنے کے لیے `scripts\start_windows.bat` کو ٹرمینل (`cmd`) سے چلائیں |
| ہارڈویئر کی حالت "no lights" بتاتی ہے | USB کیبل (جو ڈیٹا منتقل کرے)، پورٹ اور ڈرائیور چیک کریں؛ مرحلہ 5 دیکھیں |
| لاگ | `%LOCALAPPDATA%\archerytimer\logs` (File Explorer میں پاتھ پیسٹ کر کے کھولیں) |

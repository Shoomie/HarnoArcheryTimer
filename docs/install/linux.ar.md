# التثبيت على Linux المكتبي (وmacOS)

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · [Français](linux.fr.md) · **العربية** · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.ar.md) · [Raspberry Pi](raspberry-pi.ar.md) · [العودة إلى README](../../README.ar.md)

إذا أردت Raspberry Pi يبدأ مباشرة بالمؤقّت، فاستخدم [دليل Raspberry Pi](raspberry-pi.ar.md) بدلًا من هذه الصفحة.
هذه الصفحة لحاسوب Linux عادي أو حاسوب محمول بسطح مكتب (جُرّبت على عائلة Debian/Ubuntu؛ وغيرها يعمل إن كان فيه Python 3.9+).

## 1. ثبّت المتطلبات

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`. Arch: `sudo pacman -S git python sdl2`.

macOS: ثبّت Python 3 من <https://www.python.org/downloads/> (أو `brew install python`).

## 2. نزّل المشروع

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

لا يوجد git؟ نزّل ملف ZIP من صفحة GitHub (**Code → Download ZIP**) وفك ضغطه.

## 3. الإعداد (مرة واحدة)

```bash
scripts/setup_desktop.sh
```

ينشئ بيئة خاصة في `.venv` ويثبّت المؤقّت فيها. إذا لم يكن السكربت قابلًا للتنفيذ فشغّله بالأمر `bash scripts/setup_desktop.sh`.

## 4. شغّل المؤقّت

```bash
scripts/start.sh
```

- عرض تجريبي دون أجهزة أضواء: `scripts/start.sh --no-serial`
- ملء الشاشة: `scripts/start.sh -- --fullscreen`
- واجهة سويدية: `scripts/start.sh -- --lang sv` (ويمكن تغيير اللغة أيضًا من قائمة الإعدادات)
- شاشة الجمهور على الشاشة الثانية دون أزرار تحكم: `scripts/start.sh -- --profile audience --display 1`

المفاتيح: **Space** = الزر الكبير، **P** = إيقاف مؤقت، **Esc** = إيقاف طارئ. انظر [README](../../README.ar.md).

## 5. وصّل الأضواء والبوق (اختياري)

1. لا حاجة لأي خطوة يدوية: فقد منح `scripts/setup_desktop.sh` (الخطوة 3) هذا الحاسوب حق الوصول إلى اللوحة
   (مجموعة المنفذ التسلسلي مع قاعدة udev تُبعد ModemManager عنها أيضًا؛ ويطلب كلمة المرور مرة واحدة؛
   و`--no-system` يتخطّى ذلك) ويعمل `scripts/start.sh` دون تسجيل خروج. وإذا تخطّيته فنفّذ
   `sudo usermod -aG dialout $USER` ثم سجّل الدخول من جديد.

2. وصّل لوحة ESP32. يجدها البرنامج تلقائيًا. لاختيار المنفذ بنفسك، اعثر عليه بالأمر
   `ls /dev/ttyACM* /dev/ttyUSB*` وشغّل `scripts/start.sh --serial-port /dev/ttyACM0`.

البرنامج الثابت للوحة موجود في [`firmware/`](../../firmware/)؛ ولكتابته على لوحة جديدة استخدم [دليل الكتابة على اللوحة](../flashing.md) (بالإنجليزية).

## التحديث

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

تُحفظ الإعدادات في `~/.local/share/archerytimer` (في macOS: `~/Library/Application Support/archerytimer`).

## حل المشكلات

| المشكلة | ما العمل |
| --- | --- |
| `venv failed` | نفّذ `sudo apt install python3-venv` ثم أعد الإعداد |
| لا توجد نافذة / خطأ SDL | شغّله داخل جلسة سطح مكتب (وليس عبر SSH فقط)؛ ثبّت `libsdl2-2.0-0` |
| "Permission denied" على المنفذ التسلسلي | الخطوة 5: مجموعة `dialout`، ثم سجّل الخروج والدخول |
| لا صوت من مكبّرات الحاسوب | افحص جهاز الإخراج في إعدادات الصوت بالبرنامج؛ يجب أن يعمل ALSA/PulseAudio مع التطبيقات الأخرى أولًا |
| السجلات | `~/.local/share/archerytimer/logs/` |

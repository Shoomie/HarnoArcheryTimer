# التثبيت على Windows 10/11

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · [हिन्दी](windows.hi.md) · [Español](windows.es.md) · [Français](windows.fr.md) · **العربية** · [বাংলা](windows.bn.md) · [Português](windows.pt.md) · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.ar.md) · [Raspberry Pi](raspberry-pi.ar.md) · [العودة إلى README](../../README.ar.md)

الوقت اللازم: نحو 10 دقائق. تحتاج إلى اتصال بالإنترنت عند الإعداد الأول فقط.

## 1. ثبّت Python

1. افتح <https://www.python.org/downloads/> ونزّل أحدث إصدار من Python 3 (الإصدار 3.9 أو أحدث).
2. شغّل المثبّت. **فعّل خيار "Add python.exe to PATH"** في الشاشة الأولى، ثم اضغط *Install Now*.

## 2. نزّل المشروع

اختر طريقة واحدة:

- **ZIP (الأسهل):** في صفحة GitHub اضغط **Code → Download ZIP**، ثم انقر بزر الفأرة الأيمن على الملف واختر *Extract All*.
  ضع المجلد في مكان بسيط، مثل `C:\ArcheryTimer`.
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. الإعداد (مرة واحدة)

افتح مجلد المشروع و**انقر مرتين على `scripts\setup_windows.bat`**. ينشئ بيئة Python خاصة في `.venv` ويثبّت ما يحتاجه المؤقّت.
انتظر ظهور "Done".

إذا حذّرك Windows SmartScreen من الملف، فاختر *More info → Run anyway* (إنه سكربت نصي بسيط يمكنك قراءته في Notepad).

## 4. شغّل المؤقّت

انقر مرتين على **`scripts\start_windows.bat`**. تفتح نافذة تعرض المؤقّت.

- لا توجد أجهزة أضواء بعد؟ شغّله من سطر الأوامر بـ `scripts\start_windows.bat --no-serial` لعرض تجريبي.
- ملء الشاشة على تلفاز: `scripts\start_windows.bat -- --fullscreen`
- واجهة سويدية: `scripts\start_windows.bat -- --lang sv` (ويمكن تغيير اللغة أيضًا من قائمة الإعدادات)
- شاشة ثانية للجمهور دون أزرار تحكم: `scripts\start_windows.bat -- --profile audience --display 1`

(لإنشاء اختصار على سطح المكتب: انقر بزر الفأرة الأيمن على `start_windows.bat` ← *Send to → Desktop (create shortcut)*.)

المفاتيح: **Space** = الزر الكبير، **P** = إيقاف مؤقت، **Esc** = إيقاف طارئ. انظر [README](../../README.ar.md).

## 5. وصّل الأضواء والبوق (اختياري)

وصّل لوحة ESP32 بمنفذ USB. يجدها البرنامج تلقائيًا. وإن لم يجدها:

1. افتح *Device Manager → Ports (COM & LPT)* ودوّن المنفذ، مثل `COM7`.
2. شغّل بالأمر `scripts\start_windows.bat --serial-port COM7`.

بعض اللوحات الرخيصة تحتاج إلى تعريف USB تسلسلي (CH340 أو CP210x)؛ إذا لم يظهر أي منفذ COM فثبّت التعريف من الشركة المصنّعة للشريحة.
البرنامج الثابت للوحة موجود في [`firmware/`](../../firmware/)؛ ولكتابته على لوحة جديدة استخدم [دليل الكتابة على اللوحة](../flashing.md) (بالإنجليزية).

## التحديث

نزّل ملف ZIP الجديد (أو نفّذ `git pull`) وشغّل `scripts\setup_windows.bat` مرة أخرى. تُحفظ إعداداتك في ملف المستخدم
(`%LOCALAPPDATA%\archerytimer`) وليس في مجلد المشروع.

## حل المشكلات

| المشكلة | ما العمل |
| --- | --- |
| "Python was not found" | أعد تثبيت Python مع تفعيل *Add python.exe to PATH*، أو أعد الإعداد بعد إعادة تشغيل الحاسوب |
| تفتح النافذة ثم تُغلق | شغّل `scripts\start_windows.bat` من سطر الأوامر (`cmd`) لترى رسالة الخطأ |
| حالة الأجهزة تقول "no lights" | افحص كابل USB (يجب أن ينقل البيانات) والمنفذ والتعريف؛ انظر الخطوة 5 |
| السجلات | `%LOCALAPPDATA%\archerytimer\logs` (الصق المسار في File Explorer لفتحه) |

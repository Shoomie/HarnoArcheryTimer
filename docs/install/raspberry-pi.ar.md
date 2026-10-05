# التثبيت على Raspberry Pi (شاشة تلفاز تعمل بمفردها)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · [हिन्दी](raspberry-pi.hi.md) · [Español](raspberry-pi.es.md) · [Français](raspberry-pi.fr.md) · **العربية** · [বাংলা](raspberry-pi.bn.md) · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.ar.md) · [Linux](linux.ar.md) · [العودة إلى README](../../README.ar.md)

النتيجة: يبدأ الـ Pi مباشرة بالمؤقّت على التلفاز دون تسجيل دخول بلوحة المفاتيح. تعمل نواة المؤقّت كخدمة في الخلفية
وتُبقي الأضواء والصوت شغّالة حتى لو أُعيد تشغيل برنامج العرض.

**الهدف المُختبَر:** Raspberry Pi 2 Model B، وRaspberry Pi OS Lite بنظام 32 بت (Trixie)، وتلفاز بمنفذ HDMI. يُتوقَّع أن تعمل طُرز Pi الأخرى لكنها لم تُختبر.
الوقت اللازم: نحو 30 دقيقة.

> ما الذي يضبطه المثبّت بالتفصيل: [deployment.md](../deployment.md) (بالإنجليزية).

## ما تحتاج إليه

- Raspberry Pi مع مزوّد الطاقة، وبطاقة microSD (8 جيجابايت أو أكثر)، وكابل HDMI، وتلفاز أو شاشة
- حاسوب لتجهيز البطاقة، واتصال شبكي للـ Pi (الكابل أسهل) أثناء التثبيت
- اختياري: لوحة ESP32 للأضواء/البوق في منفذ USB، ولوحة مفاتيح USB أو جهاز تحكم في العروض

## 1. اكتب نظام التشغيل على البطاقة

1. على حاسوبك ثبّت **Raspberry Pi Imager** من <https://www.raspberrypi.com/software/>.
2. اختر طراز الـ Pi ثم *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***.
3. اختر بطاقة SD واضغط *Next* ثم *Edit settings* (تخصيص النظام) واضبط:
   - **اسم المضيف** (مثل `archerytimer`) و**اسم مستخدم وكلمة مرور** (تذكّرهما؛ يصبح هذا المستخدم مستخدم الشاشة المستقلة)،
   - **Wi-Fi** إن لم تستخدم كابلًا، والمنطقة الزمنية،
   - *Services → Enable SSH*.
4. اكتب البطاقة، وضعها في الـ Pi، ووصّل HDMI والشبكة، ثم شغّله. انتظر بضع دقائق حتى ينتهي الإقلاع الأول.

## 2. سجّل الدخول

من حاسوبك (في Windows 10/11 وLinux يوجد `ssh`):

```bash
ssh <username>@archerytimer.local
```

(إذا لم يُعثر على الاسم فاستخدم عنوان IP الخاص بالـ Pi من جهاز التوجيه.) أو وصّل لوحة مفاتيح بالـ Pi وسجّل الدخول على التلفاز.

## 3. نزّل المشروع

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. شغّل المثبّت

```bash
sudo bash scripts/install_pi.sh
```

يستغرق عدة دقائق. يثبّت الحزم اللازمة، وينسخ البرنامج إلى `/opt/archerytimer`، ويضبط الخدمة في الخلفية، ويفعّل طبقة العرض بوحدة GPU،
ويجعل الـ Pi يسجّل الدخول تلقائيًا في أول طرفية ويشغّل المؤقّت هناك. عند الانتهاء أعد التشغيل:

```bash
sudo reboot
```

بعد إعادة التشغيل يظهر المؤقّت على التلفاز من تلقاء نفسه. استخدم الفأرة أو لوحة المفاتيح (Space = الزر الكبير، Esc = إيقاف طارئ).

الخيارات: `--no-ui` لصندوق أضواء/صوت فقط دون شاشة، و`--user NAME` لاختيار مستخدم الشاشة المستقلة. نفّذ
`scripts/install_pi.sh --help` لعرض القائمة.

## 5. وصّل الأضواء والبوق (اختياري)

وصّل لوحة ESP32 بمنفذ USB في الـ Pi. يجدها البرنامج تلقائيًا (مستخدم الشاشة المستقلة موجود أصلًا في مجموعة `dialout`).
تظهر الحالة في قائمة الأجهزة بالبرنامج. ولكتابة البرنامج الثابت على لوحة جديدة انظر [دليل الكتابة على اللوحة](../flashing.md) (بالإنجليزية)؛
ومصادر البرنامج الثابت في [`firmware/`](../../firmware/).

## الإعدادات

توجد خيارات البدء الإضافية في ملفين صغيرين. عدّلهما بالأمر `sudo nano`:

| الملف | يُستخدم من أجل | مثال |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | النواة في الخلفية | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | العرض | `UI_ARGS="--lang sv --profile audience"` |

للتطبيق بعد التعديل: `sudo systemctl restart archerytimer-core` ثم أعد التشغيل (أو سجّل الخروج من الطرفية) لتحديث العرض. لتشغيل عدة أجهزة Pi معًا
(قائد وتابعون) انظر [cluster.md](../cluster.md) (بالإنجليزية).

## التحديث

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

تبقى إعداداتك والملفات الموجودة في `/etc/archerytimer` كما هي.

**من حاسوب Windows**، دون git على الـ Pi: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(ينسخ المشروع ويشغّل المثبّت؛ أضِف `-Reboot` لإعادة التشغيل بعد ذلك).

## الحصول على سطر أوامر عادي على التلفاز

تستولي الشاشة المستقلة على أول طرفية في الـ Pi. للعمل على الـ Pi نفسه سجّل الدخول عبر **SSH** من حاسوب آخر، أو أنشئ الملف `~/.no-kiosk`
(`touch ~/.no-kiosk`) وأعد التشغيل لتحصل على سطر أوامر عادي. احذف الملف وأعد التشغيل ليعود المؤقّت.

## حل المشكلات

| المشكلة | ما العمل |
| --- | --- |
| شاشة سوداء بعد إعادة التشغيل | انتظر دقيقة أو دقيقتين بعد التشغيل. افحص HDMI. إن استمرت المشكلة فسجّل الدخول عبر SSH ونفّذ `journalctl -u archerytimer-core -n 50` وانظر `~/.local/share/archerytimer/logs/ui.log` |
| الشاشة تبقى سوداء فقط إذا شُغّل التلفاز بعد الـ Pi | أضِف `hdmi_force_hotplug=1` إلى `/boot/firmware/config.txt` وأعد التشغيل |
| العرض يعمل لكن "no connection to core" | `systemctl status archerytimer-core`؛ أعد تشغيله بـ `sudo systemctl restart archerytimer-core` |
| لا أضواء/بوق | تأكد أن كابل USB ينقل البيانات؛ يجب أن يُظهر `ls /dev/ttyACM* /dev/ttyUSB*` جهازًا |
| فحص البيئة | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| إزالة كل شيء | `sudo bash scripts/uninstall_pi.sh` (يُبقي إعداداتك) |

السجلات المباشرة: `journalctl -u archerytimer-core -f`. مزيد من التفاصيل الداخلية: [deployment.md](../deployment.md) (بالإنجليزية).

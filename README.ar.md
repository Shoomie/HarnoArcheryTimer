# Archery Timer (مؤقّت الرماية بالقوس والسهم)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · **العربية** · [বাংলা](README.bn.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [اردو](README.ur.md)

ساعة رماية مفتوحة المصدر. تدير زمن الرماية في البطولات والتدريب، وتعرضه على تلفاز أو شاشة، وتشغّل إشارات المرور والبوق عبر USB.
صُمّمت لنادٍ صغير للرماية ويشغّلها متطوعون، لذلك تحتوي الشاشة على زر كبير واضح واحد لما سيحدث بعد ذلك، وزر إيقاف طارئ ظاهر دائمًا.

- تعمل على **Windows 10/11** و**Linux** و**Raspberry Pi** (من طراز 2B فما فوق، كشاشة عرض تعمل بمفردها) وmacOS.
- الواجهة بالإنجليزية (الافتراضية) والسويدية.
- يستمر المؤقّت والأضواء والصوت في العمل حتى لو تعطّل برنامج العرض.
- لوحة ESP32 اختيارية للأضواء والبوق، وشاشات إضافية اختيارية، وعدة أجهزة على شبكة واحدة.

> **قبل أي بطولة رسمية:** الأزمنة الموجودة في `config/` هي **قيم مؤقتة**، وليست قواعد مؤكَّدة من World Archery أو SBF.
> راجعها مع القواعد الحالية وعدّل ملفات TOML (يمكن للأندية إضافة إعداداتها الجاهزة الخاصة دون تغيير الكود). اختُبر النظام من البداية إلى النهاية
> على حاسوب Windows وحاسوب Linux وRaspberry Pi 2B مع وحدات ESP32-C3 وWROOM-32D. غير مغطّى بعد: تشغيل متواصل لمدة 4 ساعات،
> ولوحات ESP32-S3، واختبارات الراديو بعيدة المدى.

## إدارة جلسة

1. شغّل البرنامج (انظر «التثبيت» أدناه). اضغط **Space** أو الزر الكبير: يفتح الإعداد.
2. اختر بطاقة (مثل *Indoor 18 m*)، ثم الخطوط وعدد الجولات، ثم ابدأ.
3. يوضّح الزر الكبير دائمًا ما سيحدث بعد ذلك: بدء الجولة، الجولة التالية، الاستئناف. **P** للإيقاف المؤقت. **Esc** هو الإيقاف الطارئ:
   أضواء حمراء وصمت، بضغطة واحدة دائمًا ودون تأكيد.

تعرض الشاشة ضوءًا كبيرًا (برمز وليس باللون فقط)، والعدّ التنازلي، والجولة والخط، وحالة الأجهزة بكلمات بسيطة.

## التثبيت

اختر نظامك. يشرح كل دليل الخطوات من الصفر حتى يعمل المؤقّت.

| النظام | الدليل | باختصار |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.ar.md](docs/install/windows.ar.md) | ثبّت Python، نزّل المشروع، انقر مرتين على `scripts\setup_windows.bat`، ثم `scripts\start_windows.bat` |
| **Linux** (وmacOS) | [docs/install/linux.ar.md](docs/install/linux.ar.md) | `scripts/setup_desktop.sh` ثم `scripts/start.sh` |
| **Raspberry Pi** (شاشة تلفاز) | [docs/install/raspberry-pi.ar.md](docs/install/raspberry-pi.ar.md) | اكتب Pi OS Lite على البطاقة، `git clone`، `sudo scripts/install_pi.sh`، ثم أعد التشغيل |

### بداية سريعة (أي حاسوب مكتبي، دون أجهزة)

1. ثبّت **Python 3.9 أو أحدث** ([python.org](https://www.python.org/downloads/)؛ وفي Linux عادةً
   `sudo apt install python3 python3-venv python3-pip`).
2. نزّل المشروع: في GitHub اضغط **Code → Download ZIP** ثم فك الضغط، أو
   `git clone <repository-url>`.
3. في مجلد المشروع شغّل سكربت الإعداد مرة واحدة، ثم سكربت البدء:

   | | الإعداد (مرة واحدة) | البدء |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   يعني `--no-serial` «لا توجد أجهزة أضواء متصلة». احذفه عند توصيل لوحة ESP32؛ إذ يجدها البرنامج تلقائيًا.

### أزرار التحكم

| المفتاح | الإجراء |
| --- | --- |
| **Space** / Enter | الزر الكبير: الخطوة التالية أيًّا كانت (فتح الإعداد، بدء الجولة، ...) |
| **P** | إيقاف مؤقت / استئناف |
| **Esc** | **إيقاف طارئ**: أضواء حمراء وصمت، بضغطة واحدة دائمًا |
| S | إنهاء الجولة |
| N / Backspace | المرحلة التالية / رجوع (بعد Stop أو Next يظهر «رجوع» باسم *تراجع* لمدة 5 ثوانٍ) |
| M / F1 | القائمة: جلسة جديدة، المؤقّتات، الإعدادات، حالة الأجهزة، الشبكة، الصوت، خروج |

كل شيء يعمل أيضًا بالفأرة. وتعمل كذلك أجهزة التحكم في العروض التقديمية ودوّاسات القدم التي تتصرف كلوحة مفاتيح، وكذلك أزرار وحدات ESP32.
القائمة الكاملة: [docs/ui.md](docs/ui.md) (بالإنجليزية).

### خيارات بدء مفيدة

أضِفها بعد سكربت البدء، وخيارات العرض بعد `--`:

```text
scripts/start.sh --no-serial                      عرض تجريبي دون أجهزة
scripts/start.sh --serial-port COM7               اختيار منفذ USB بنفسك (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        ملء الشاشة، بواجهة سويدية
scripts/start.sh -- --profile audience --display 1   شاشة الجمهور على الشاشة الثانية، دون أزرار تحكم
```

في Windows استخدم `scripts\start_windows.bat` بدلًا من `scripts/start.sh`.

## الأضواء والبوق وأجهزة إضافية

الوثائق التقنية بالإنجليزية. أدلة التثبيت متوفرة بـ 11 لغة.

| أريد أن... | اقرأ |
| --- | --- |
| أوصل إشارات المرور والبوق (لوحة ESP32، التوصيلات، الأطراف) | [docs/firmware.md](docs/firmware.md) |
| أكتب البرنامج الثابت على وحدة ESP32 (Windows وLinux وmacOS؛ لا حاجة إلى مترجم) | [docs/flashing.md](docs/flashing.md): `scripts\flash.bat` أو `sh scripts/flash.sh` |
| أضبط البوق ومكبّرات الصوت وأجري اختبار الصوت | [docs/audio.md](docs/audio.md) |
| أشغّل عدة شاشات أو حواسيب أو Pi كمؤقّت واحد (شبكة محلية أو راديو) | [docs/cluster.md](docs/cluster.md) |
| صناديق أضواء لاسلكية وأزرار تحكم عن بُعد | [docs/mesh.md](docs/mesh.md) |

## الوثائق

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | فهرس كل الوثائق |
| [docs/install/](docs/install/) | أدلة التثبيت (11 لغة) |
| [docs/ui.md](docs/ui.md) | الشاشات والمفاتيح وملفات العرض |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | بروتوكول USB التسلسلي؛ بروتوكول النواة إلى العرض |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | تفاصيل Raspberry Pi الداخلية؛ قياسات التوقيت والرسم |
| [structure.md](structure.md) | مكان كل شيء في شجرة الكود المصدري |

## بنية المستودع

```text
src/archerytimer/   البرنامج (خدمة النواة، عميل الواجهة، الأجهزة، الصوت، IPC)
config/             تسلسلات الأزمنة والإعدادات الجاهزة (TOML، قيم مؤقتة)
locales/            كل نصوص الواجهة، en.toml وsv.toml
assets/             الخط (Inter، OFL)
firmware/           البرنامج الثابت لـ ESP32 (PlatformIO)، صور جاهزة، متجهات اختبار مشتركة
scripts/            سكربتات التثبيت/البدء، مثبّت Raspberry Pi، قائمة الكتابة على اللوحة، قياسات الأداء
docs/               الوثائق
tests/  tools/      مجموعة الاختبارات، محاكي الشبكة المتشابكة
```

## التطوير

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # الاختبارات (بعضها يُتخطّى في Windows)
ruff check . && ruff format --check .
mypy
```

لترجمة الوثائق أو الواجهة انظر [CONTRIBUTING.md](CONTRIBUTING.md). قواعد المشروع وبنيته: [CLAUDE.md](CLAUDE.md). القياسات: [docs/benchmarks.md](docs/benchmarks.md).

## الترخيص

MIT (انظر [LICENSE](LICENSE)): حرّ في الاستخدام والنسخ والتعديل والمشاركة والبيع، لأي غرض وفي أي مكان. المساهمات مرحَّب بها بالترخيص نفسه.
تحتفظ الأجزاء الخارجية بتراخيصها المفتوحة الخاصة، المذكورة في [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (مثل خط Inter، `assets/fonts/OFL.txt`).

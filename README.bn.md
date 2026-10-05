# Archery Timer (তীরন্দাজি টাইমার)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · **বাংলা** · [Português](README.pt.md) · [Русский](README.ru.md) · [اردو](README.ur.md)

তীরন্দাজির জন্য একটি ওপেন-সোর্স শুটিং ক্লক। এটি প্রতিযোগিতা ও অনুশীলনে শুটিংয়ের সময় চালায়, টিভি বা মনিটরে দেখায়, এবং USB-র মাধ্যমে ট্রাফিক লাইট ও হর্ন নিয়ন্ত্রণ করে।
এটি একটি ছোট তীরন্দাজি ক্লাবের জন্য তৈরি এবং স্বেচ্ছাসেবকেরা চালান, তাই পর্দায় "এরপর কী হবে" বলে দেওয়া একটিমাত্র স্পষ্ট বড় বোতাম আছে, আর আছে সবসময় দেখা যায় এমন জরুরি স্টপ।

- **Windows 10/11**, **Linux**, **Raspberry Pi** (2B ও তার উপরে, টিভি কিয়স্ক হিসেবে) এবং macOS-এ চলে।
- ইন্টারফেস ইংরেজি (ডিফল্ট) ও সুইডিশ ভাষায়।
- ডিসপ্লে প্রোগ্রাম ক্র্যাশ করলেও টাইমার, লাইট ও শব্দ চলতে থাকে।
- লাইট ও হর্নের জন্য ঐচ্ছিক ESP32 বোর্ড, ঐচ্ছিক দ্বিতীয় স্ক্রিন, এবং একই নেটওয়ার্কে একাধিক ডিভাইস।

> **অফিসিয়াল প্রতিযোগিতার আগে:** `config/`-এর সময়গুলো **অস্থায়ী মান (placeholder)**, World Archery / SBF-এর নিশ্চিত নিয়ম নয়।
> বর্তমান নিয়মের সঙ্গে মিলিয়ে দেখুন এবং TOML ফাইল সম্পাদনা করুন (ক্লাবগুলো কোড না বদলেই নিজেদের প্রিসেট যোগ করতে পারে)। সিস্টেমটি একটি Windows পিসি,
> একটি Linux পিসি এবং ESP32-C3 ও WROOM-32D মডিউলসহ একটি Raspberry Pi 2B-তে শুরু থেকে শেষ পর্যন্ত পরীক্ষা করা হয়েছে। এখনও পরীক্ষা হয়নি:
> ৪ ঘণ্টার একটানা চালানো, ESP32-S3 বোর্ড এবং দূর-পাল্লার রেডিও পরীক্ষা।

## একটি সেশন চালানো

1. প্রোগ্রাম চালু করুন (নিচে "ইনস্টল" দেখুন)। **Space** বা বড় বোতাম চাপুন: সেটআপ খুলবে।
2. একটি কার্ড বেছে নিন (যেমন *Indoor 18 m*), লাইন ও রাউন্ড (এন্ড) সংখ্যা ঠিক করুন, তারপর শুরু করুন।
3. বড় বোতাম সবসময় বলে দেয় এরপর কী হবে: এন্ড শুরু, পরের এন্ড, আবার চালু। **P** থামায়। **Esc** জরুরি স্টপ:
   লাল লাইট ও নীরবতা, সবসময় একবার চাপেই, কোনো নিশ্চিতকরণ ছাড়া।

পর্দায় একটি বড় লাইট (শুধু রঙ নয়, চিহ্নসহ), কাউন্টডাউন, এন্ড ও লাইন, এবং হার্ডওয়্যারের অবস্থা সহজ ভাষায় দেখানো হয়।

## ইনস্টল

আপনার সিস্টেম বেছে নিন। প্রতিটি গাইড একদম শুরু থেকে চালু টাইমার পর্যন্ত ধাপে ধাপে নিয়ে যায়।

| সিস্টেম | গাইড | সংক্ষেপে |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.bn.md](docs/install/windows.bn.md) | Python ইনস্টল করুন, প্রজেক্ট ডাউনলোড করুন, `scripts\setup_windows.bat`-এ ডাবল-ক্লিক করুন, তারপর `scripts\start_windows.bat` |
| **Linux** (এবং macOS) | [docs/install/linux.bn.md](docs/install/linux.bn.md) | `scripts/setup_desktop.sh`, তারপর `scripts/start.sh` |
| **Raspberry Pi** (টিভি কিয়স্ক) | [docs/install/raspberry-pi.bn.md](docs/install/raspberry-pi.bn.md) | Pi OS Lite ফ্ল্যাশ করুন, `git clone`, `sudo scripts/install_pi.sh`, রিবুট |

### দ্রুত শুরু (যেকোনো ডেস্কটপ, হার্ডওয়্যার লাগে না)

1. **Python 3.9 বা নতুন** ইনস্টল করুন ([python.org](https://www.python.org/downloads/); Linux-এ সাধারণত
   `sudo apt install python3 python3-venv python3-pip`)।
2. প্রজেক্ট ডাউনলোড করুন: GitHub-এ **Code → Download ZIP** চেপে আনজিপ করুন, অথবা
   `git clone <repository-url>`।
3. প্রজেক্ট ফোল্ডারে একবার সেটআপ স্ক্রিপ্ট চালান, তারপর স্টার্ট স্ক্রিপ্ট:

   | | সেটআপ (একবার) | স্টার্ট |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` মানে "কোনো লাইট হার্ডওয়্যার যুক্ত নেই"। ESP32 বোর্ড লাগানো থাকলে এটি বাদ দিন; প্রোগ্রাম নিজেই বোর্ড খুঁজে নেয়।

### নিয়ন্ত্রণ

| কী | কাজ |
| --- | --- |
| **Space** / Enter | বড় বোতাম: যা-ই পরের ধাপ (সেটআপ খোলা, এন্ড শুরু, ...) |
| **P** | বিরতি / আবার চালু |
| **Esc** | **জরুরি স্টপ**: লাল লাইট ও নীরবতা, সবসময় একবার চাপেই |
| S | এন্ড থামান |
| N / Backspace | পরের ধাপ / পেছনে (Stop বা Next-এর পর ৫ সেকেন্ড "পেছনে" বোতামের নাম *Undo* দেখায়) |
| M / F1 | মেনু: নতুন সেশন, টাইমার, সেটিংস, হার্ডওয়্যারের অবস্থা, নেটওয়ার্ক, শব্দ, বন্ধ করুন |

সবকিছু মাউস দিয়েও চলে। কীবোর্ডের মতো কাজ করা প্রেজেন্টেশন ক্লিকার ও ফুট প্যাডেলও চলে, আর ESP32 মডিউলের বোতামও।
পূর্ণ তালিকা: [docs/ui.md](docs/ui.md) (ইংরেজিতে)।

### কাজের স্টার্ট অপশন

এগুলো স্টার্ট স্ক্রিপ্টের পরে যোগ করুন, ডিসপ্লের অপশন `--`-এর পরে:

```text
scripts/start.sh --no-serial                      হার্ডওয়্যার ছাড়া ডেমো
scripts/start.sh --serial-port COM7               নিজে USB পোর্ট বেছে নিন (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        ফুলস্ক্রিন, সুইডিশ ইন্টারফেস
scripts/start.sh -- --profile audience --display 1   দ্বিতীয় মনিটরে দর্শকদের স্ক্রিন, কোনো নিয়ন্ত্রণ নেই
```

Windows-এ `scripts/start.sh`-এর বদলে `scripts\start_windows.bat` ব্যবহার করুন।

## লাইট, হর্ন ও আরও ডিভাইস

প্রযুক্তিগত ডকুমেন্ট ইংরেজিতে। ইনস্টল গাইড ১১টি ভাষায় আছে।

| আমি চাই... | পড়ুন |
| --- | --- |
| ট্রাফিক লাইট ও হর্ন যুক্ত করতে (ESP32 বোর্ড, ওয়্যারিং, পিন) | [docs/firmware.md](docs/firmware.md) |
| ESP32 মডিউল ফ্ল্যাশ করতে (Windows, Linux, macOS; কম্পাইলার লাগে না) | [docs/flashing.md](docs/flashing.md): `scripts\flash.bat` বা `sh scripts/flash.sh` |
| হর্ন ও স্পিকার সাজাতে, সাউন্ড টেস্ট | [docs/audio.md](docs/audio.md) |
| একাধিক স্ক্রিন, পিসি বা Pi একটি টাইমার হিসেবে চালাতে (LAN বা রেডিও) | [docs/cluster.md](docs/cluster.md) |
| বেতার লাইট বক্স ও রিমোট বোতাম | [docs/mesh.md](docs/mesh.md) |

## ডকুমেন্টেশন

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | সব ডকুমেন্টের সূচি |
| [docs/install/](docs/install/) | ইনস্টল গাইড (১১টি ভাষা) |
| [docs/ui.md](docs/ui.md) | স্ক্রিন, কী, ডিসপ্লে প্রোফাইল |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | USB সিরিয়াল প্রোটোকল; কোর থেকে ডিসপ্লে প্রোটোকল |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Raspberry Pi-র ভেতরের তথ্য; সময় ও রেন্ডারিং পরিমাপ |
| [structure.md](structure.md) | সোর্স ট্রিতে কোনটা কোথায় |

## রিপোজিটরির কাঠামো

```text
src/archerytimer/   প্রোগ্রাম (কোর সার্ভিস, UI ক্লায়েন্ট, হার্ডওয়্যার, অডিও, IPC)
config/             সময়ের ক্রম ও সেটআপ প্রিসেট (TOML, অস্থায়ী)
locales/            ইন্টারফেসের সব লেখা, en.toml ও sv.toml
assets/             ফন্ট (Inter, OFL)
firmware/           ESP32 ফার্মওয়্যার (PlatformIO), তৈরি ইমেজ, শেয়ার্ড টেস্ট ভেক্টর
scripts/            ইনস্টল/স্টার্ট স্ক্রিপ্ট, Raspberry Pi ইনস্টলার, ফ্ল্যাশিং মেনু, বেঞ্চমার্ক
docs/               ডকুমেন্টেশন
tests/  tools/      টেস্ট স্যুট, মেশ সিমুলেটর
```

## ডেভেলপমেন্ট

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # টেস্ট (কিছু Windows-এ বাদ যায়)
ruff check . && ruff format --check .
mypy
```

ডকুমেন্ট বা ইন্টারফেস অনুবাদ করতে [CONTRIBUTING.md](CONTRIBUTING.md) দেখুন। প্রজেক্টের নিয়ম ও আর্কিটেকচার: [CLAUDE.md](CLAUDE.md)।
বেঞ্চমার্ক: [docs/benchmarks.md](docs/benchmarks.md)।

## লাইসেন্স

MIT ([LICENSE](LICENSE) দেখুন): যেকোনো উদ্দেশ্যে, যেকোনো জায়গায়, ব্যবহার, কপি, পরিবর্তন, শেয়ার ও বিক্রির জন্য মুক্ত। একই লাইসেন্সে অবদান স্বাগত।
তৃতীয় পক্ষের অংশগুলো নিজ নিজ উন্মুক্ত লাইসেন্স বজায় রাখে, যা [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)-এ তালিকাভুক্ত (যেমন Inter ফন্ট, `assets/fonts/OFL.txt`)।

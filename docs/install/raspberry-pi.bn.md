# Raspberry Pi-তে ইনস্টল করুন (টিভি কিয়স্ক)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · [हिन्दी](raspberry-pi.hi.md) · [Español](raspberry-pi.es.md) · [Français](raspberry-pi.fr.md) · [العربية](raspberry-pi.ar.md) · **বাংলা** · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.bn.md) · [Linux](linux.bn.md) · [README-তে ফিরুন](../../README.bn.md)

ফলাফল: Pi কীবোর্ড দিয়ে লগ-ইন ছাড়াই টিভিতে সরাসরি টাইমারে বুট করে। টাইমার কোর ব্যাকগ্রাউন্ড সার্ভিস হিসেবে চলে
এবং ডিসপ্লে প্রোগ্রাম রিস্টার্ট হলেও লাইট ও শব্দ চলতে থাকে।

**পরীক্ষিত লক্ষ্য:** Raspberry Pi 2 Model B, Raspberry Pi OS Lite 32-bit (Trixie), HDMI টিভি। অন্য Pi মডেল চলার কথা, তবে পরীক্ষা করা হয়নি।
সময় লাগবে: প্রায় ৩০ মিনিট।

> ইনস্টলার ঠিক কী কী সেট করে, বিস্তারিত: [deployment.md](../deployment.md) (ইংরেজিতে)।

## যা যা লাগবে

- পাওয়ার সাপ্লাইসহ Raspberry Pi, microSD কার্ড (৮ GB বা বেশি), HDMI কেবল এবং টিভি বা মনিটর
- কার্ড তৈরির জন্য একটি কম্পিউটার, এবং ইনস্টলের সময় Pi-র জন্য নেটওয়ার্ক সংযোগ (কেবল সবচেয়ে সহজ)
- ঐচ্ছিক: USB পোর্টে লাইট/হর্নের ESP32 বোর্ড, USB কীবোর্ড বা ক্লিকার

## ১. কার্ডে অপারেটিং সিস্টেম লিখুন

1. আপনার কম্পিউটারে <https://www.raspberrypi.com/software/> থেকে **Raspberry Pi Imager** ইনস্টল করুন।
2. আপনার Pi মডেল বেছে নিন, তারপর *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***।
3. SD কার্ড বেছে *Next* চাপুন, তারপর *Edit settings* (OS কাস্টমাইজেশন) এ ঠিক করুন:
   - একটি **hostname** (যেমন `archerytimer`) এবং **ইউজারনেম ও পাসওয়ার্ড** (মনে রাখুন; এই ইউজারই কিয়স্ক ইউজার হবে),
   - কেবল না থাকলে আপনার **Wi-Fi**, এবং টাইম জোন,
   - *Services → Enable SSH*।
4. কার্ড লিখুন, Pi-তে লাগান, HDMI ও নেটওয়ার্ক যুক্ত করে চালু করুন। প্রথম বুটের জন্য কয়েক মিনিট অপেক্ষা করুন।

## ২. লগ-ইন করুন

আপনার কম্পিউটার থেকে (Windows 10/11 ও Linux দুটোতেই `ssh` আছে):

```bash
ssh <username>@archerytimer.local
```

(নাম না পেলে রাউটার থেকে Pi-র IP ঠিকানা ব্যবহার করুন।) অথবা Pi-তে কীবোর্ড লাগিয়ে টিভিতে লগ-ইন করুন।

## ৩. প্রজেক্ট ডাউনলোড করুন

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## ৪. ইনস্টলার চালান

```bash
sudo bash scripts/install_pi.sh
```

এতে কয়েক মিনিট লাগে। এটি দরকারি প্যাকেজ ইনস্টল করে, প্রোগ্রাম `/opt/archerytimer`-এ কপি করে, ব্যাকগ্রাউন্ড সার্ভিস সেট করে, GPU ডিসপ্লে ওভারলে চালু করে,
এবং Pi যাতে প্রথম কনসোলে নিজে লগ-ইন করে সেখানে টাইমার চালু করে তা ঠিক করে। শেষ হলে রিবুট করুন:

```bash
sudo reboot
```

রিবুটের পর টাইমার নিজেই টিভিতে দেখা যায়। মাউস বা কীবোর্ড ব্যবহার করুন (Space = বড় বোতাম, Esc = জরুরি স্টপ)।

অপশন: ডিসপ্লে ছাড়া শুধু লাইট/শব্দের বক্সের জন্য `--no-ui`, কিয়স্ক ইউজার বাছতে `--user NAME`। তালিকার জন্য
`scripts/install_pi.sh --help` চালান।

## ৫. লাইট ও হর্ন যুক্ত করুন (ঐচ্ছিক)

ESP32 বোর্ড Pi-র USB পোর্টে লাগান। এটি নিজে থেকে পাওয়া যায় (কিয়স্ক ইউজার আগে থেকেই `dialout` গ্রুপে আছে)। অবস্থা প্রোগ্রামের হার্ডওয়্যার মেনুতে দেখা যায়।
নতুন বোর্ড ফ্ল্যাশ করতে [ফ্ল্যাশিং গাইড](../flashing.md) (ইংরেজিতে) দেখুন; ফার্মওয়্যারের সোর্স [`firmware/`](../../firmware/)-এ আছে।

## সেটিংস

বাড়তি স্টার্ট অপশন দুটি ছোট ফাইলে থাকে। `sudo nano` দিয়ে সম্পাদনা করুন:

| ফাইল | কীসের জন্য | উদাহরণ |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | ব্যাকগ্রাউন্ড কোর | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | ডিসপ্লে | `UI_ARGS="--lang sv --profile audience"` |

পরিবর্তনের পর: `sudo systemctl restart archerytimer-core`, আর ডিসপ্লের জন্য রিবুট করুন (বা কনসোল থেকে লগ-আউট করুন)। একসঙ্গে একাধিক Pi চালাতে
(একটি লিডার, বাকিরা ফলোয়ার) [cluster.md](../cluster.md) (ইংরেজিতে) দেখুন।

## আপডেট

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

আপনার সেটিংস এবং `/etc/archerytimer`-এর ফাইলগুলো থেকে যায়।

**Windows কম্পিউটার থেকে**, Pi-তে git ছাড়া: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(প্রজেক্ট কপি করে ও ইনস্টলার চালায়; পরে রিস্টার্টের জন্য `-Reboot` যোগ করুন)।

## টিভিতে সাধারণ শেল পাওয়া

কিয়স্ক Pi-র প্রথম কনসোল দখল করে। Pi-তে সরাসরি কাজ করতে অন্য কম্পিউটার থেকে **SSH**-এ লগ-ইন করুন, অথবা `~/.no-kiosk` ফাইল বানান
(`touch ~/.no-kiosk`) এবং সাধারণ প্রম্পটের জন্য রিবুট করুন। টাইমার ফিরে পেতে ফাইলটি মুছে রিবুট করুন।

## সমস্যা সমাধান

| সমস্যা | কী করবেন |
| --- | --- |
| রিবুটের পর কালো স্ক্রিন | চালুর পর ১-২ মিনিট অপেক্ষা করুন। HDMI দেখুন। না মিটলে SSH-এ লগ-ইন করে `journalctl -u archerytimer-core -n 50` চালান এবং `~/.local/share/archerytimer/logs/ui.log` দেখুন |
| শুধু Pi-র পরে টিভি চালু করলে স্ক্রিন কালো থাকে | `/boot/firmware/config.txt`-এ `hdmi_force_hotplug=1` যোগ করে রিবুট করুন |
| ডিসপ্লে চলে কিন্তু "no connection to core" | `systemctl status archerytimer-core`; `sudo systemctl restart archerytimer-core` দিয়ে রিস্টার্ট করুন |
| লাইট/হর্ন নেই | USB কেবল ডেটা বহন করে কি না দেখুন; `ls /dev/ttyACM* /dev/ttyUSB*`-এ একটি ডিভাইস দেখা উচিত |
| পরিবেশ যাচাই | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| সব সরিয়ে ফেলা | `sudo bash scripts/uninstall_pi.sh` (আপনার সেটিংস রেখে দেয়) |

লাইভ লগ: `journalctl -u archerytimer-core -f`। আরও ভেতরের তথ্য: [deployment.md](../deployment.md) (ইংরেজিতে)।

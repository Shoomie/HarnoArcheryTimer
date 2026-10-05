# ডেস্কটপ Linux (এবং macOS)-এ ইনস্টল করুন

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · [Français](linux.fr.md) · [العربية](linux.ar.md) · **বাংলা** · [Português](linux.pt.md) · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.bn.md) · [Raspberry Pi](raspberry-pi.bn.md) · [README-তে ফিরুন](../../README.bn.md)

যে Raspberry Pi সরাসরি টাইমারে বুট করে তার জন্য বরং [Raspberry Pi গাইড](raspberry-pi.bn.md) ব্যবহার করুন।
এই পাতা ডেস্কটপসহ সাধারণ Linux পিসি বা ল্যাপটপের জন্য (Debian/Ubuntu পরিবারে পরীক্ষিত; অন্যগুলোও চলে যদি Python 3.9+ থাকে)।

## ১. প্রয়োজনীয় জিনিস ইনস্টল করুন

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`। Arch: `sudo pacman -S git python sdl2`।

macOS: <https://www.python.org/downloads/> থেকে Python 3 ইনস্টল করুন (বা `brew install python`)।

## ২. প্রজেক্ট ডাউনলোড করুন

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

git নেই? GitHub পেজ থেকে ZIP ডাউনলোড করুন (**Code → Download ZIP**) এবং আনজিপ করুন।

## ৩. সেটআপ (একবার)

```bash
scripts/setup_desktop.sh
```

এটি `.venv`-এ একটি আলাদা পরিবেশ তৈরি করে এবং তাতে টাইমার ইনস্টল করে। স্ক্রিপ্ট এক্সিকিউটেবল না হলে `bash scripts/setup_desktop.sh` দিয়ে চালান।

## ৪. টাইমার চালু করুন

```bash
scripts/start.sh
```

- লাইট হার্ডওয়্যার ছাড়া ডেমো: `scripts/start.sh --no-serial`
- ফুলস্ক্রিন: `scripts/start.sh -- --fullscreen`
- সুইডিশ ইন্টারফেস: `scripts/start.sh -- --lang sv` (ভাষা সেটিংস মেনু থেকেও বদলানো যায়)
- দ্বিতীয় মনিটরে দর্শকদের স্ক্রিন, কোনো নিয়ন্ত্রণ ছাড়া: `scripts/start.sh -- --profile audience --display 1`

কী: **Space** = বড় বোতাম, **P** = বিরতি, **Esc** = জরুরি স্টপ। [README](../../README.bn.md) দেখুন।

## ৫. লাইট ও হর্ন যুক্ত করুন (ঐচ্ছিক)

1. হাতে কিছু করতে হবে না: `scripts/setup_desktop.sh` (ধাপ ৩) ইতিমধ্যে এই কম্পিউটারকে বোর্ডে প্রবেশাধিকার দিয়েছে
   (সিরিয়াল গ্রুপ এবং একটি udev নিয়ম, যা ModemManager-কেও বোর্ড থেকে দূরে রাখে; একবার আপনার পাসওয়ার্ড চায়;
   `--no-system` এটি এড়িয়ে যায়) এবং `scripts/start.sh` লগ-আউট ছাড়াই চলে। এটি এড়িয়ে গেলে
   `sudo usermod -aG dialout $USER` চালান এবং আবার লগ-ইন করুন।

2. ESP32 বোর্ড লাগান। এটি নিজে থেকে পাওয়া যায়। নিজে পোর্ট বাছতে চাইলে `ls /dev/ttyACM* /dev/ttyUSB*` দিয়ে খুঁজে
   `scripts/start.sh --serial-port /dev/ttyACM0` দিয়ে চালু করুন।

বোর্ডের ফার্মওয়্যার [`firmware/`](../../firmware/)-এ আছে; নতুন বোর্ড [ফ্ল্যাশিং গাইড](../flashing.md) (ইংরেজিতে) দিয়ে ফ্ল্যাশ করুন।

## আপডেট

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

সেটিংস `~/.local/share/archerytimer`-এ থাকে (macOS: `~/Library/Application Support/archerytimer`)।

## সমস্যা সমাধান

| সমস্যা | কী করবেন |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` চালান এবং সেটআপ আবার করুন |
| উইন্ডো নেই / SDL ত্রুটি | ডেস্কটপ সেশনের ভেতরে চালান (সাধারণ SSH-এ নয়); `libsdl2-2.0-0` ইনস্টল করুন |
| সিরিয়াল পোর্টে "Permission denied" | ধাপ ৫: `dialout` গ্রুপ, তারপর লগ-আউট করে আবার লগ-ইন করুন |
| পিসির স্পিকারে শব্দ নেই | প্রোগ্রামের সাউন্ড সেটিংসে আউটপুট ডিভাইস দেখুন; অন্য অ্যাপে আগে ALSA/PulseAudio চলতে হবে |
| লগ | `~/.local/share/archerytimer/logs/` |

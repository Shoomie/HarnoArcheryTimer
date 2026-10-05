# Windows 10/11-এ ইনস্টল করুন

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · [हिन्दी](windows.hi.md) · [Español](windows.es.md) · [Français](windows.fr.md) · [العربية](windows.ar.md) · **বাংলা** · [Português](windows.pt.md) · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.bn.md) · [Raspberry Pi](raspberry-pi.bn.md) · [README-তে ফিরুন](../../README.bn.md)

সময় লাগবে: প্রায় ১০ মিনিট। ইন্টারনেট শুধু প্রথমবার সেটআপের সময় লাগে।

## ১. Python ইনস্টল করুন

1. <https://www.python.org/downloads/> এ যান এবং Python 3-এর সর্বশেষ সংস্করণ (3.9 বা নতুন) ডাউনলোড করুন।
2. ইনস্টলার চালান। প্রথম স্ক্রিনে **"Add python.exe to PATH" টিক দিন**, তারপর *Install Now* চাপুন।

## ২. প্রজেক্ট ডাউনলোড করুন

যেকোনো একটি পথ বেছে নিন:

- **ZIP (সবচেয়ে সহজ):** GitHub পেজে **Code → Download ZIP** চাপুন, তারপর ফাইলে রাইট-ক্লিক করে *Extract All* বেছে নিন।
  ফোল্ডারটি সহজ কোথাও রাখুন, যেমন `C:\ArcheryTimer`।
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## ৩. সেটআপ (একবার)

প্রজেক্ট ফোল্ডার খুলুন এবং **`scripts\setup_windows.bat`-এ ডাবল-ক্লিক করুন**। এটি `.venv`-এ একটি আলাদা Python পরিবেশ তৈরি করে এবং টাইমারের দরকারি জিনিস ইনস্টল করে।
"Done" দেখা পর্যন্ত অপেক্ষা করুন।

Windows SmartScreen ফাইলটি নিয়ে সতর্ক করলে *More info → Run anyway* বেছে নিন (এটি সাধারণ টেক্সট স্ক্রিপ্ট, Notepad-এ পড়ে দেখতে পারেন)।

## ৪. টাইমার চালু করুন

**`scripts\start_windows.bat`**-এ ডাবল-ক্লিক করুন। টাইমারসহ একটি উইন্ডো খুলবে।

- এখনও লাইট হার্ডওয়্যার নেই? ডেমোর জন্য টার্মিনাল থেকে `scripts\start_windows.bat --no-serial` দিয়ে চালান।
- টিভিতে ফুলস্ক্রিন: `scripts\start_windows.bat -- --fullscreen`
- সুইডিশ ইন্টারফেস: `scripts\start_windows.bat -- --lang sv` (ভাষা সেটিংস মেনু থেকেও বদলানো যায়)
- দর্শকদের জন্য দ্বিতীয় মনিটর, কোনো নিয়ন্ত্রণ ছাড়া: `scripts\start_windows.bat -- --profile audience --display 1`

(ডেস্কটপ শর্টকাট বানাতে: `start_windows.bat`-এ রাইট-ক্লিক → *Send to → Desktop (create shortcut)*।)

কী: **Space** = বড় বোতাম, **P** = বিরতি, **Esc** = জরুরি স্টপ। [README](../../README.bn.md) দেখুন।

## ৫. লাইট ও হর্ন যুক্ত করুন (ঐচ্ছিক)

ESP32 বোর্ড USB পোর্টে লাগান। প্রোগ্রাম নিজেই এটি খুঁজে নেয়। না পেলে:

1. *Device Manager → Ports (COM & LPT)* খুলে পোর্ট লিখে রাখুন, যেমন `COM7`।
2. `scripts\start_windows.bat --serial-port COM7` দিয়ে চালু করুন।

কিছু সস্তা বোর্ডের জন্য USB-সিরিয়াল ড্রাইভার (CH340 বা CP210x) লাগে; কোনো COM পোর্ট না এলে চিপ নির্মাতার ড্রাইভার ইনস্টল করুন।
বোর্ডের ফার্মওয়্যার [`firmware/`](../../firmware/)-এ আছে; নতুন বোর্ড [ফ্ল্যাশিং গাইড](../flashing.md) (ইংরেজিতে) দিয়ে ফ্ল্যাশ করুন।

## আপডেট

নতুন ZIP ডাউনলোড করুন (বা `git pull`) এবং আবার `scripts\setup_windows.bat` চালান। আপনার সেটিংস ইউজার প্রোফাইলে
(`%LOCALAPPDATA%\archerytimer`) থাকে, প্রজেক্ট ফোল্ডারে নয়।

## সমস্যা সমাধান

| সমস্যা | কী করবেন |
| --- | --- |
| "Python was not found" | Python আবার ইনস্টল করুন ও *Add python.exe to PATH* টিক দিন, অথবা পিসি রিস্টার্ট করে সেটআপ আবার চালান |
| উইন্ডো খুলেই বন্ধ হয়ে যায় | ত্রুটির বার্তা দেখতে `scripts\start_windows.bat` টার্মিনালে (`cmd`) চালান |
| হার্ডওয়্যারের অবস্থা "no lights" বলছে | USB কেবল (ডেটা বহনে সক্ষম হতে হবে), পোর্ট ও ড্রাইভার দেখুন; ধাপ ৫ দেখুন |
| লগ | `%LOCALAPPDATA%\archerytimer\logs` (File Explorer-এ পাথ পেস্ট করে খুলুন) |

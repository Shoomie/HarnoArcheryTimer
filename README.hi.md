# Archery Timer (तीरंदाज़ी टाइमर)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · **हिन्दी** · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [اردو](README.ur.md)

तीरंदाज़ी के लिए एक ओपन-सोर्स शूटिंग क्लॉक। यह प्रतियोगिताओं और अभ्यास में शूटिंग का समय चलाता है, उसे टीवी या मॉनिटर पर दिखाता है,
और USB के ज़रिए ट्रैफ़िक लाइटें और हॉर्न चलाता है। इसे एक छोटे तीरंदाज़ी क्लब के लिए बनाया गया है और इसे स्वयंसेवक चलाते हैं, इसलिए स्क्रीन पर
"आगे क्या होगा" बताने वाला एक ही साफ़ बटन है और एक हमेशा दिखने वाला आपातकालीन स्टॉप।

- **Windows 10/11**, **Linux**, **Raspberry Pi** (2B और उससे ऊपर, टीवी कियोस्क के रूप में) और macOS पर चलता है।
- इंटरफ़ेस अंग्रेज़ी (डिफ़ॉल्ट) और स्वीडिश में।
- डिस्प्ले प्रोग्राम क्रैश हो जाए तब भी टाइमर, लाइटें और आवाज़ चलती रहती हैं।
- लाइट और हॉर्न के लिए वैकल्पिक ESP32 बोर्ड, वैकल्पिक दूसरी स्क्रीन, और एक ही नेटवर्क पर कई डिवाइस।

> **आधिकारिक प्रतियोगिता से पहले:** `config/` में दिए गए समय **अस्थायी मान (placeholder)** हैं, World Archery / SBF के पुष्ट नियम नहीं।
> इन्हें मौजूदा नियमों से मिलाकर जाँचें और TOML फ़ाइलें बदलें (क्लब बिना कोड बदले अपने प्रीसेट जोड़ सकते हैं)। सिस्टम को एक Windows पीसी,
> एक Linux पीसी और ESP32-C3 व WROOM-32D मॉड्यूल वाले Raspberry Pi 2B पर शुरू से अंत तक परखा गया है। अभी जाँचा नहीं गया:
> 4 घंटे का लगातार परीक्षण, ESP32-S3 बोर्ड और लंबी दूरी के रेडियो परीक्षण।

## सत्र चलाना

1. प्रोग्राम शुरू करें (नीचे "इंस्टॉल" देखें)। **Space** या बड़ा बटन दबाएँ: सेटअप खुलेगा।
2. एक कार्ड चुनें (जैसे *Indoor 18 m*), लाइनें और राउंड (एंड) की संख्या चुनें, फिर शुरू करें।
3. बड़ा बटन हमेशा बताता है कि आगे क्या होगा: एंड शुरू करें, अगला एंड, फिर से शुरू करें। **P** से रोकें। **Esc** आपातकालीन स्टॉप है:
   लाल लाइटें और चुप्पी, हमेशा एक ही दबाव में, किसी पुष्टि के बिना।

स्क्रीन पर एक बड़ी लाइट (केवल रंग नहीं, चिह्न के साथ), उलटी गिनती, एंड और लाइन, और हार्डवेयर की स्थिति सरल शब्दों में दिखती है।

## इंस्टॉल

अपना सिस्टम चुनें। हर गाइड शून्य से चालू टाइमर तक कदम-दर-कदम ले जाती है।

| सिस्टम | गाइड | संक्षेप में |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.hi.md](docs/install/windows.hi.md) | Python इंस्टॉल करें, प्रोजेक्ट डाउनलोड करें, `scripts\setup_windows.bat` पर डबल-क्लिक करें, फिर `scripts\start_windows.bat` |
| **Linux** (और macOS) | [docs/install/linux.hi.md](docs/install/linux.hi.md) | `scripts/setup_desktop.sh`, फिर `scripts/start.sh` |
| **Raspberry Pi** (टीवी कियोस्क) | [docs/install/raspberry-pi.hi.md](docs/install/raspberry-pi.hi.md) | Pi OS Lite फ़्लैश करें, `git clone`, `sudo scripts/install_pi.sh`, रीबूट |

### तेज़ शुरुआत (कोई भी डेस्कटॉप, हार्डवेयर की ज़रूरत नहीं)

1. **Python 3.9 या नया** इंस्टॉल करें ([python.org](https://www.python.org/downloads/); Linux पर आमतौर पर
   `sudo apt install python3 python3-venv python3-pip`)।
2. प्रोजेक्ट डाउनलोड करें: GitHub पर **Code → Download ZIP** दबाकर खोलें, या
   `git clone <repository-url>`।
3. प्रोजेक्ट फ़ोल्डर में एक बार सेटअप स्क्रिप्ट चलाएँ, फिर स्टार्ट स्क्रिप्ट:

   | | सेटअप (एक बार) | स्टार्ट |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` का मतलब है "कोई लाइट हार्डवेयर नहीं जुड़ा है"। ESP32 बोर्ड लगा हो तो इसे हटा दें; प्रोग्राम उसे अपने आप ढूँढ लेता है।

### नियंत्रण

| कुंजी | काम |
| --- | --- |
| **Space** / Enter | बड़ा बटन: जो भी आगे होना है (सेटअप खोलना, एंड शुरू करना, ...) |
| **P** | रोकें / फिर शुरू करें |
| **Esc** | **आपातकालीन स्टॉप**: लाल लाइटें और चुप्पी, हमेशा एक ही दबाव में |
| S | एंड रोकें |
| N / Backspace | अगला चरण / पीछे (Stop या Next के बाद 5 सेकंड तक "पीछे" की जगह *Undo* दिखता है) |
| M / F1 | मेनू: नया सत्र, टाइमर, सेटिंग्स, हार्डवेयर की स्थिति, नेटवर्क, आवाज़, बाहर निकलें |

सब कुछ माउस से भी चलता है। कीबोर्ड की तरह काम करने वाले प्रेज़ेंटेशन क्लिकर और फ़ुट पैडल भी चलते हैं, और ESP32 मॉड्यूल के बटन भी।
पूरी सूची: [docs/ui.md](docs/ui.md) (अंग्रेज़ी में)।

### काम के स्टार्ट विकल्प

इन्हें स्टार्ट स्क्रिप्ट के बाद जोड़ें, डिस्प्ले के विकल्प `--` के बाद:

```text
scripts/start.sh --no-serial                      बिना हार्डवेयर के डेमो
scripts/start.sh --serial-port COM7               USB पोर्ट ख़ुद चुनें (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        फ़ुलस्क्रीन, स्वीडिश इंटरफ़ेस
scripts/start.sh -- --profile audience --display 1   दूसरे मॉनिटर पर दर्शकों की स्क्रीन, कोई नियंत्रण नहीं
```

Windows पर `scripts/start.sh` की जगह `scripts\start_windows.bat` इस्तेमाल करें।

## लाइट, हॉर्न और अधिक डिवाइस

तकनीकी दस्तावेज़ अंग्रेज़ी में हैं। इंस्टॉल गाइड 11 भाषाओं में उपलब्ध हैं।

| मैं चाहता/चाहती हूँ... | पढ़ें |
| --- | --- |
| ट्रैफ़िक लाइटें और हॉर्न जोड़ना (ESP32 बोर्ड, वायरिंग, पिन) | [docs/firmware.md](docs/firmware.md) |
| ESP32 मॉड्यूल फ़्लैश करना (Windows, Linux, macOS; कंपाइलर की ज़रूरत नहीं) | [docs/flashing.md](docs/flashing.md): `scripts\flash.bat` या `sh scripts/flash.sh` |
| हॉर्न और स्पीकर सेट करना, साउंड टेस्ट | [docs/audio.md](docs/audio.md) |
| कई स्क्रीन, पीसी या Pi को एक टाइमर की तरह चलाना (LAN या रेडियो) | [docs/cluster.md](docs/cluster.md) |
| वायरलेस लाइट बॉक्स और रिमोट बटन | [docs/mesh.md](docs/mesh.md) |

## दस्तावेज़

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | सभी दस्तावेज़ों की सूची |
| [docs/install/](docs/install/) | इंस्टॉल गाइड (11 भाषाएँ) |
| [docs/ui.md](docs/ui.md) | स्क्रीन, कुंजियाँ, डिस्प्ले प्रोफ़ाइल |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | USB सीरियल प्रोटोकॉल; कोर से डिस्प्ले तक का प्रोटोकॉल |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Raspberry Pi की भीतरी जानकारी; समय और रेंडरिंग की माप |
| [structure.md](structure.md) | सोर्स ट्री में कौन-सी चीज़ कहाँ है |

## रिपॉज़िटरी की बनावट

```text
src/archerytimer/   प्रोग्राम (कोर सर्विस, UI क्लाइंट, हार्डवेयर, ऑडियो, IPC)
config/             समय के क्रम और सेटअप प्रीसेट (TOML, अस्थायी)
locales/            इंटरफ़ेस के सभी पाठ, en.toml और sv.toml
assets/             फ़ॉन्ट (Inter, OFL)
firmware/           ESP32 फ़र्मवेयर (PlatformIO), बने-बनाए इमेज, साझा टेस्ट वेक्टर
scripts/            इंस्टॉल/स्टार्ट स्क्रिप्ट, Raspberry Pi इंस्टॉलर, फ़्लैशिंग मेनू, बेंचमार्क
docs/               दस्तावेज़
tests/  tools/      टेस्ट सूट, मेश सिमुलेटर
```

## डेवलपमेंट

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # टेस्ट (कुछ Windows पर छोड़े जाते हैं)
ruff check . && ruff format --check .
mypy
```

दस्तावेज़ या इंटरफ़ेस का अनुवाद करने के लिए [CONTRIBUTING.md](CONTRIBUTING.md) देखें। प्रोजेक्ट के नियम और आर्किटेक्चर: [CLAUDE.md](CLAUDE.md)।
बेंचमार्क: [docs/benchmarks.md](docs/benchmarks.md)।

## लाइसेंस

MIT ([LICENSE](LICENSE) देखें): किसी भी उद्देश्य से, कहीं भी, इस्तेमाल करने, कॉपी करने, बदलने, बाँटने और बेचने के लिए स्वतंत्र। योगदान उसी लाइसेंस के तहत
स्वागत योग्य हैं। तीसरे पक्ष के हिस्से अपने-अपने खुले लाइसेंस के साथ रहते हैं, जो [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) में सूचीबद्ध हैं
(जैसे Inter फ़ॉन्ट, `assets/fonts/OFL.txt`)।

# डेस्कटॉप Linux (और macOS) पर इंस्टॉल करें

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · **हिन्दी** · [Español](linux.es.md) · [Français](linux.fr.md) · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.hi.md) · [Raspberry Pi](raspberry-pi.hi.md) · [README पर वापस](../../README.hi.md)

ऐसे Raspberry Pi के लिए जो सीधे टाइमर में बूट हो, [Raspberry Pi गाइड](raspberry-pi.hi.md) इस्तेमाल करें।
यह पन्ना डेस्कटॉप वाले सामान्य Linux पीसी या लैपटॉप के लिए है (Debian/Ubuntu परिवार पर परखा गया; दूसरे भी चलते हैं अगर उनमें Python 3.9+ हो)।

## 1. ज़रूरी चीज़ें इंस्टॉल करें

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`। Arch: `sudo pacman -S git python sdl2`।

macOS: <https://www.python.org/downloads/> से Python 3 इंस्टॉल करें (या `brew install python`)।

## 2. प्रोजेक्ट डाउनलोड करें

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

git नहीं है? GitHub पेज से ZIP डाउनलोड करें (**Code → Download ZIP**) और उसे खोलें।

## 3. सेटअप (एक बार)

```bash
scripts/setup_desktop.sh
```

यह `.venv` में एक अलग वातावरण बनाता है और टाइमर उसमें इंस्टॉल करता है। अगर स्क्रिप्ट एक्ज़ीक्यूटेबल नहीं है, तो उसे `bash scripts/setup_desktop.sh` से चलाएँ।

## 4. टाइमर शुरू करें

```bash
scripts/start.sh
```

- लाइट हार्डवेयर के बिना डेमो: `scripts/start.sh --no-serial`
- फ़ुलस्क्रीन: `scripts/start.sh -- --fullscreen`
- स्वीडिश इंटरफ़ेस: `scripts/start.sh -- --lang sv` (भाषा सेटिंग्स मेनू से भी बदली जा सकती है)
- दूसरे मॉनिटर पर दर्शकों की स्क्रीन, बिना नियंत्रण: `scripts/start.sh -- --profile audience --display 1`

कुंजियाँ: **Space** = बड़ा बटन, **P** = रोकना, **Esc** = आपातकालीन स्टॉप। [README](../../README.hi.md) देखें।

## 5. लाइट और हॉर्न जोड़ें (वैकल्पिक)

1. हाथ से कुछ करने की ज़रूरत नहीं: `scripts/setup_desktop.sh` (चरण 3) पहले ही इस कंप्यूटर को बोर्ड तक पहुँच दे चुका है
   (सीरियल समूह और एक udev नियम, जो ModemManager को भी बोर्ड से दूर रखता है; यह एक बार आपका पासवर्ड माँगता है;
   `--no-system` इसे छोड़ देता है) और `scripts/start.sh` बिना लॉग-आउट किए चलता है। अगर आपने इसे छोड़ा था, तो
   `sudo usermod -aG dialout $USER` चलाएँ और दोबारा लॉग-इन करें।

2. ESP32 बोर्ड लगाएँ। वह अपने आप मिल जाता है। पोर्ट ख़ुद चुनना हो तो उसे `ls /dev/ttyACM* /dev/ttyUSB*` से ढूँढें और
   `scripts/start.sh --serial-port /dev/ttyACM0` से शुरू करें।

बोर्ड का फ़र्मवेयर [`firmware/`](../../firmware/) में है; नया बोर्ड [फ़्लैशिंग गाइड](../flashing.md) (अंग्रेज़ी में) से फ़्लैश करें।

## अपडेट

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

सेटिंग्स `~/.local/share/archerytimer` में रहती हैं (macOS: `~/Library/Application Support/archerytimer`)।

## समस्या समाधान

| समस्या | क्या करें |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` चलाएँ और सेटअप फिर से करें |
| विंडो नहीं खुलती / SDL त्रुटि | इसे डेस्कटॉप सत्र के भीतर चलाएँ (सादे SSH से नहीं); `libsdl2-2.0-0` इंस्टॉल करें |
| सीरियल पोर्ट पर "Permission denied" | चरण 5: `dialout` समूह, फिर लॉग-आउट करके दोबारा लॉग-इन करें |
| पीसी के स्पीकर से आवाज़ नहीं | प्रोग्राम की साउंड सेटिंग्स में आउटपुट डिवाइस जाँचें; पहले दूसरे ऐप में ALSA/PulseAudio चलना चाहिए |
| लॉग | `~/.local/share/archerytimer/logs/` |

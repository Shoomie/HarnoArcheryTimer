# Raspberry Pi पर इंस्टॉल करें (टीवी कियोस्क)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · **हिन्दी** · [Español](raspberry-pi.es.md) · [Français](raspberry-pi.fr.md) · [العربية](raspberry-pi.ar.md) · [বাংলা](raspberry-pi.bn.md) · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.hi.md) · [Linux](linux.hi.md) · [README पर वापस](../../README.hi.md)

नतीजा: Pi सीधे टीवी पर टाइमर में बूट होता है, कीबोर्ड से लॉग-इन किए बिना। टाइमर कोर बैकग्राउंड सर्विस के रूप में चलता है और
डिस्प्ले प्रोग्राम रीस्टार्ट हो जाए तब भी लाइट और आवाज़ चलती रहती हैं।

**परखा गया लक्ष्य:** Raspberry Pi 2 Model B, Raspberry Pi OS Lite 32-bit (Trixie), HDMI टीवी। दूसरे Pi मॉडल चलने चाहिए, पर परखे नहीं गए हैं।
लगने वाला समय: लगभग 30 मिनट।

> इंस्टॉलर क्या-क्या सेट करता है, विस्तार से: [deployment.md](../deployment.md) (अंग्रेज़ी में)।

## आपको क्या चाहिए

- पावर सप्लाई सहित Raspberry Pi, microSD कार्ड (8 GB या अधिक), HDMI केबल और टीवी या मॉनिटर
- कार्ड तैयार करने के लिए एक कंप्यूटर, और इंस्टॉलेशन के दौरान Pi के लिए नेटवर्क कनेक्शन (केबल सबसे आसान है)
- वैकल्पिक: USB पोर्ट में लाइट/हॉर्न वाला ESP32 बोर्ड, USB कीबोर्ड या क्लिकर

## 1. कार्ड पर ऑपरेटिंग सिस्टम लिखें

1. अपने कंप्यूटर पर <https://www.raspberrypi.com/software/> से **Raspberry Pi Imager** इंस्टॉल करें।
2. अपना Pi मॉडल चुनें, फिर *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***।
3. SD कार्ड चुनें, *Next* दबाएँ, फिर *Edit settings* (OS अनुकूलन) में ये तय करें:
   - एक **hostname** (जैसे `archerytimer`) और **यूज़रनेम व पासवर्ड** (याद रखें; यही यूज़र कियोस्क यूज़र बनेगा),
   - केबल न हो तो अपना **Wi-Fi**, और अपना टाइम ज़ोन,
   - *Services → Enable SSH*।
4. कार्ड लिखें, उसे Pi में लगाएँ, HDMI और नेटवर्क जोड़ें और पावर ऑन करें। पहले बूट के लिए कुछ मिनट रुकें।

## 2. लॉग-इन करें

अपने कंप्यूटर से (Windows 10/11 और Linux दोनों में `ssh` है):

```bash
ssh <username>@archerytimer.local
```

(अगर नाम नहीं मिलता, तो अपने राउटर से Pi का IP पता इस्तेमाल करें।) या Pi में कीबोर्ड लगाकर टीवी पर लॉग-इन करें।

## 3. प्रोजेक्ट डाउनलोड करें

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. इंस्टॉलर चलाएँ

```bash
sudo bash scripts/install_pi.sh
```

इसमें कुछ मिनट लगते हैं। यह ज़रूरी पैकेज इंस्टॉल करता है, प्रोग्राम को `/opt/archerytimer` में कॉपी करता है, बैकग्राउंड सर्विस सेट करता है,
GPU डिस्प्ले ओवरले चालू करता है, और Pi को पहले कंसोल पर अपने आप लॉग-इन करके वहीं टाइमर शुरू करने लायक बनाता है। पूरा होने पर रीबूट करें:

```bash
sudo reboot
```

रीबूट के बाद टाइमर टीवी पर अपने आप दिखता है। माउस या कीबोर्ड इस्तेमाल करें (Space = बड़ा बटन, Esc = आपातकालीन स्टॉप)।

विकल्प: बिना डिस्प्ले के सिर्फ़ लाइट/आवाज़ वाले बॉक्स के लिए `--no-ui`, कियोस्क यूज़र चुनने के लिए `--user NAME`। पूरी सूची के लिए
`scripts/install_pi.sh --help` चलाएँ।

## 5. लाइट और हॉर्न जोड़ें (वैकल्पिक)

ESP32 बोर्ड को Pi के USB पोर्ट में लगाएँ। वह अपने आप मिल जाता है (कियोस्क यूज़र पहले से `dialout` समूह में है)। स्थिति प्रोग्राम के हार्डवेयर मेनू में दिखती है।
नया बोर्ड फ़्लैश करने के लिए [फ़्लैशिंग गाइड](../flashing.md) (अंग्रेज़ी में) देखें; फ़र्मवेयर का सोर्स [`firmware/`](../../firmware/) में है।

## सेटिंग्स

अतिरिक्त स्टार्ट विकल्प दो छोटी फ़ाइलों में रहते हैं। इन्हें `sudo nano` से बदलें:

| फ़ाइल | किसके लिए | उदाहरण |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | बैकग्राउंड कोर | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | डिस्प्ले | `UI_ARGS="--lang sv --profile audience"` |

बदलाव के बाद: `sudo systemctl restart archerytimer-core`, और डिस्प्ले के लिए रीबूट करें (या कंसोल से लॉग-आउट करें)। कई Pi को साथ चलाने
(एक लीडर, बाकी फ़ॉलोअर) के लिए [cluster.md](../cluster.md) (अंग्रेज़ी में) देखें।

## अपडेट

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

आपकी सेटिंग्स और `/etc/archerytimer` की फ़ाइलें बनी रहती हैं।

**Windows कंप्यूटर से**, Pi पर git के बिना: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(प्रोजेक्ट कॉपी करता है और इंस्टॉलर चलाता है; बाद में रीस्टार्ट के लिए `-Reboot` जोड़ें)।

## टीवी पर सामान्य शेल पाना

कियोस्क Pi का पहला कंसोल ले लेता है। Pi पर ही काम करने के लिए दूसरे कंप्यूटर से **SSH** द्वारा लॉग-इन करें, या फ़ाइल `~/.no-kiosk` बनाएँ
(`touch ~/.no-kiosk`) और सामान्य प्रॉम्प्ट के लिए रीबूट करें। टाइमर वापस पाने के लिए फ़ाइल हटाएँ और रीबूट करें।

## समस्या समाधान

| समस्या | क्या करें |
| --- | --- |
| रीबूट के बाद काली स्क्रीन | पावर ऑन के बाद 1-2 मिनट रुकें। HDMI जाँचें। फिर भी न हो तो SSH से लॉग-इन करें, `journalctl -u archerytimer-core -n 50` चलाएँ और `~/.local/share/archerytimer/logs/ui.log` देखें |
| स्क्रीन तभी काली रहती है जब टीवी Pi के बाद चालू किया जाए | `/boot/firmware/config.txt` में `hdmi_force_hotplug=1` जोड़ें और रीबूट करें |
| डिस्प्ले चलता है पर "no connection to core" दिखता है | `systemctl status archerytimer-core`; `sudo systemctl restart archerytimer-core` से रीस्टार्ट करें |
| लाइट/हॉर्न नहीं | जाँचें कि USB केबल डेटा ले जाता है; `ls /dev/ttyACM* /dev/ttyUSB*` में एक डिवाइस दिखना चाहिए |
| वातावरण जाँचें | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| सब कुछ हटाएँ | `sudo bash scripts/uninstall_pi.sh` (आपकी सेटिंग्स रखता है) |

लाइव लॉग: `journalctl -u archerytimer-core -f`। भीतरी जानकारी: [deployment.md](../deployment.md) (अंग्रेज़ी में)।

# Windows 10/11 पर इंस्टॉल करें

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · **हिन्दी** · [Español](windows.es.md) · [Français](windows.fr.md) · [العربية](windows.ar.md) · [বাংলা](windows.bn.md) · [Português](windows.pt.md) · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.hi.md) · [Raspberry Pi](raspberry-pi.hi.md) · [README पर वापस](../../README.hi.md)

लगने वाला समय: लगभग 10 मिनट। इंटरनेट केवल पहली बार सेटअप के लिए चाहिए।

## 1. Python इंस्टॉल करें

1. <https://www.python.org/downloads/> पर जाएँ और Python 3 का नवीनतम संस्करण (3.9 या नया) डाउनलोड करें।
2. इंस्टॉलर चलाएँ। पहली स्क्रीन पर **"Add python.exe to PATH" पर टिक करें**, फिर *Install Now* दबाएँ।

## 2. प्रोजेक्ट डाउनलोड करें

कोई एक तरीका चुनें:

- **ZIP (सबसे आसान):** GitHub पेज पर **Code → Download ZIP** दबाएँ, फिर फ़ाइल पर राइट-क्लिक करके *Extract All* चुनें।
  फ़ोल्डर को किसी सरल जगह रखें, जैसे `C:\ArcheryTimer`।
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. सेटअप (एक बार)

प्रोजेक्ट फ़ोल्डर खोलें और **`scripts\setup_windows.bat` पर डबल-क्लिक करें**। यह `.venv` में एक अलग Python वातावरण बनाता है और टाइमर के लिए ज़रूरी चीज़ें इंस्टॉल करता है।
"Done" दिखने तक रुकें।

अगर Windows SmartScreen फ़ाइल के बारे में चेतावनी दे, तो *More info → Run anyway* चुनें (यह एक सादा टेक्स्ट स्क्रिप्ट है जिसे आप Notepad में पढ़ सकते हैं)।

## 4. टाइमर शुरू करें

**`scripts\start_windows.bat`** पर डबल-क्लिक करें। टाइमर वाली एक विंडो खुलेगी।

- अभी लाइट का हार्डवेयर नहीं है? डेमो के लिए इसे टर्मिनल से `scripts\start_windows.bat --no-serial` से शुरू करें।
- टीवी पर फ़ुलस्क्रीन: `scripts\start_windows.bat -- --fullscreen`
- स्वीडिश इंटरफ़ेस: `scripts\start_windows.bat -- --lang sv` (भाषा सेटिंग्स मेनू से भी बदली जा सकती है)
- दर्शकों के लिए दूसरा मॉनिटर, बिना नियंत्रण: `scripts\start_windows.bat -- --profile audience --display 1`

(डेस्कटॉप शॉर्टकट बनाने के लिए: `start_windows.bat` पर राइट-क्लिक → *Send to → Desktop (create shortcut)*।)

कुंजियाँ: **Space** = बड़ा बटन, **P** = रोकना, **Esc** = आपातकालीन स्टॉप। [README](../../README.hi.md) देखें।

## 5. लाइट और हॉर्न जोड़ें (वैकल्पिक)

ESP32 बोर्ड को USB पोर्ट में लगाएँ। प्रोग्राम उसे अपने आप ढूँढ लेता है। अगर न ढूँढे:

1. *Device Manager → Ports (COM & LPT)* खोलें और पोर्ट नोट करें, जैसे `COM7`।
2. `scripts\start_windows.bat --serial-port COM7` से शुरू करें।

कुछ सस्ते बोर्ड को USB-सीरियल ड्राइवर (CH340 या CP210x) चाहिए; अगर कोई COM पोर्ट नहीं दिखता तो चिप निर्माता से ड्राइवर इंस्टॉल करें।
बोर्ड का फ़र्मवेयर [`firmware/`](../../firmware/) में है; नया बोर्ड [फ़्लैशिंग गाइड](../flashing.md) (अंग्रेज़ी में) से फ़्लैश करें।

## अपडेट

नया ZIP डाउनलोड करें (या `git pull`) और `scripts\setup_windows.bat` फिर से चलाएँ। आपकी सेटिंग्स आपके यूज़र प्रोफ़ाइल
(`%LOCALAPPDATA%\archerytimer`) में रहती हैं, प्रोजेक्ट फ़ोल्डर में नहीं।

## समस्या समाधान

| समस्या | क्या करें |
| --- | --- |
| "Python was not found" | Python दोबारा इंस्टॉल करें और *Add python.exe to PATH* पर टिक करें, या पीसी रीस्टार्ट करके सेटअप फिर चलाएँ |
| विंडो खुलकर बंद हो जाती है | त्रुटि संदेश देखने के लिए `scripts\start_windows.bat` को टर्मिनल (`cmd`) से चलाएँ |
| हार्डवेयर की स्थिति "no lights" बताती है | USB केबल (उसे डेटा ले जाना चाहिए), पोर्ट और ड्राइवर जाँचें; चरण 5 देखें |
| लॉग | `%LOCALAPPDATA%\archerytimer\logs` (File Explorer में पाथ पेस्ट करके खोलें) |

# Установка в настольном Linux (и macOS)

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · [Français](linux.fr.md) · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · **Русский** · [اردو](linux.ur.md)

[Windows](windows.ru.md) · [Raspberry Pi](raspberry-pi.ru.md) · [Назад к README](../../README.ru.md)

Для Raspberry Pi, который сразу загружается в таймер, используйте [руководство для Raspberry Pi](raspberry-pi.ru.md).
Эта страница — для обычного ПК или ноутбука с Linux и рабочим столом (проверено на семействе Debian/Ubuntu; другие
дистрибутивы подойдут, если в них есть Python 3.9+).

## 1. Установите зависимости

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`. Arch: `sudo pacman -S git python sdl2`.

macOS: установите Python 3 с <https://www.python.org/downloads/> (или `brew install python`).

## 2. Скачайте проект

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

Нет git? Скачайте ZIP со страницы GitHub (**Code → Download ZIP**) и распакуйте.

## 3. Настройка (один раз)

```bash
scripts/setup_desktop.sh
```

Скрипт создаёт отдельную среду в `.venv` и устанавливает в неё таймер. Если скрипт не исполняемый, запустите его так:
`bash scripts/setup_desktop.sh`.

## 4. Запустите таймер

```bash
scripts/start.sh
```

- Демо без оборудования для света: `scripts/start.sh --no-serial`
- Полный экран: `scripts/start.sh -- --fullscreen`
- Шведский интерфейс: `scripts/start.sh -- --lang sv` (язык можно сменить и в меню настроек)
- Экран для зрителей на втором мониторе, без кнопок управления: `scripts/start.sh -- --profile audience --display 1`

Клавиши: **Пробел** = большая кнопка, **P** = пауза, **Esc** = аварийная остановка. См.
[README](../../README.ru.md).

## 5. Подключите свет и сирену (по желанию)

1. Вручную ничего делать не нужно: `scripts/setup_desktop.sh` (шаг 3) уже дал этому компьютеру доступ к плате
   (группа последовательных портов и правило udev, которое заодно не пускает к плате ModemManager; пароль спросят один
   раз; `--no-system` пропускает этот шаг), а `scripts/start.sh` работает без выхода из сеанса. Если вы пропустили этот
   шаг, выполните `sudo usermod -aG dialout $USER` и войдите заново.

2. Подключите плату ESP32. Она находится автоматически. Чтобы выбрать порт самостоятельно, найдите его командой
   `ls /dev/ttyACM* /dev/ttyUSB*` и запустите `scripts/start.sh --serial-port /dev/ttyACM0`.

Прошивка платы лежит в [`firmware/`](../../firmware/); новую плату прошивают по
[руководству по прошивке](../flashing.md) (на английском).

## Обновление

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

Настройки хранятся в `~/.local/share/archerytimer` (macOS: `~/Library/Application Support/archerytimer`).

## Если что-то не работает

| Проблема | Что делать |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` и повторите настройку |
| Нет окна / ошибка SDL | Запускайте внутри сеанса рабочего стола (не по обычному SSH); установите `libsdl2-2.0-0` |
| «Permission denied» на последовательном порту | Шаг 5: группа `dialout`, затем выйдите и войдите снова |
| Нет звука в колонках ПК | Проверьте устройство вывода в настройках звука программы; ALSA/PulseAudio сначала должны работать в других приложениях |
| Журналы | `~/.local/share/archerytimer/logs/` |

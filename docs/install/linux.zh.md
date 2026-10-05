# 在桌面 Linux（以及 macOS）上安装

[English](linux.md) · [Svenska](linux.sv.md) · **中文** · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · [Français](linux.fr.md) · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.zh.md) · [Raspberry Pi](raspberry-pi.zh.md) · [返回 README](../../README.zh.md)

如果要让 Raspberry Pi 开机直接进入计时器，请改看 [Raspberry Pi 指南](raspberry-pi.zh.md)。本页适用于带桌面环境的普通 Linux 电脑或笔记本
（在 Debian/Ubuntu 系列上测试过；其他发行版只要有 Python 3.9+ 也可以）。

## 1. 安装前置软件

Debian / Ubuntu / Mint：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora：`sudo dnf install git python3 python3-pip SDL2`。Arch：`sudo pacman -S git python sdl2`。

macOS：从 <https://www.python.org/downloads/> 安装 Python 3（或 `brew install python`）。

## 2. 下载项目

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

没有 git？从 GitHub 页面下载 ZIP（**Code → Download ZIP**）并解压。

## 3. 安装设置（仅一次）

```bash
scripts/setup_desktop.sh
```

它会在 `.venv` 中创建一个独立环境，并把计时器安装进去。如果脚本没有执行权限，请用 `bash scripts/setup_desktop.sh` 运行。

## 4. 启动计时器

```bash
scripts/start.sh
```

- 没有灯光硬件的演示：`scripts/start.sh --no-serial`
- 全屏：`scripts/start.sh -- --fullscreen`
- 瑞典语界面：`scripts/start.sh -- --lang sv`（也可以在设置菜单中更改语言）
- 在第二台显示器上显示观众屏幕，无控制按钮：`scripts/start.sh -- --profile audience --display 1`

按键：**空格键** = 大按钮，**P** = 暂停，**Esc** = 紧急停止。参见 [README](../../README.zh.md)。

## 5. 连接灯光和喇叭（可选）

1. 无需手动操作：`scripts/setup_desktop.sh`（第 3 步）已经让这台电脑获得了访问该板的权限
   （串口用户组，外加一条 udev 规则，同时让 ModemManager 不去占用它；会询问一次密码；`--no-system` 可跳过），
   而且 `scripts/start.sh` 无需注销即可使用。如果你跳过了这一步，请运行 `sudo usermod -aG dialout $USER` 并重新登录。

2. 插入 ESP32 板，程序会自动找到它。若想自己选择端口，用 `ls /dev/ttyACM* /dev/ttyUSB*` 找到它，
   然后用 `scripts/start.sh --serial-port /dev/ttyACM0` 启动。

板子的固件在 [`firmware/`](../../firmware/) 中；新板子请按照[刷写指南](../flashing.md)（英文）刷写。

## 更新

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

设置保存在 `~/.local/share/archerytimer`（macOS：`~/Library/Application Support/archerytimer`）。

## 故障排除

| 问题 | 解决办法 |
| --- | --- |
| `venv failed` | 运行 `sudo apt install python3-venv`，然后再次运行安装 |
| 没有窗口 / SDL 错误 | 确保在桌面会话中运行（而不是纯 SSH）；安装 `libsdl2-2.0-0` |
| 串口 "Permission denied" | 第 5 步：加入 `dialout` 组，然后注销并重新登录 |
| 电脑扬声器没有声音 | 在程序的声音设置中检查输出设备；ALSA/PulseAudio 必须先能被其他应用正常使用 |
| 日志 | `~/.local/share/archerytimer/logs/` |

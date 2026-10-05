# 在 Windows 10/11 上安装

[English](windows.md) · [Svenska](windows.sv.md) · **中文** · [हिन्दी](windows.hi.md) · [Español](windows.es.md) · [Français](windows.fr.md) · [العربية](windows.ar.md) · [বাংলা](windows.bn.md) · [Português](windows.pt.md) · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.zh.md) · [Raspberry Pi](raspberry-pi.zh.md) · [返回 README](../../README.zh.md)

所需时间：约 10 分钟。只有第一次安装时需要联网。

## 1. 安装 Python

1. 打开 <https://www.python.org/downloads/>，下载最新的 Python 3（3.9 或更高）。
2. 运行安装程序。在第一个界面**勾选 "Add python.exe to PATH"**，然后点击 *Install Now*。

## 2. 下载项目

任选一种方式：

- **ZIP（最简单）：** 在 GitHub 页面点击 **Code → Download ZIP**，然后右键点击该文件并选择*全部解压缩*。
  把文件夹放在一个简单的位置，例如 `C:\ArcheryTimer`。
- **Git：** `git clone <repository-url> C:\ArcheryTimer`

## 3. 安装设置（仅一次）

打开项目文件夹，**双击 `scripts\setup_windows.bat`**。它会在 `.venv` 中创建一个独立的 Python 环境，并安装计时器所需的内容。
等待出现 "Done"。

如果 Windows SmartScreen 对该文件发出警告，请选择*更多信息 → 仍要运行*（它只是一个纯文本脚本，你可以用记事本打开查看）。

## 4. 启动计时器

双击 **`scripts\start_windows.bat`**。会打开一个显示计时器的窗口。

- 还没有灯光硬件？在终端中运行 `scripts\start_windows.bat --no-serial` 进行演示。
- 在电视上全屏显示：`scripts\start_windows.bat -- --fullscreen`
- 瑞典语界面：`scripts\start_windows.bat -- --lang sv`（也可以在设置菜单中更改语言）
- 为观众准备的第二台显示器，无控制按钮：`scripts\start_windows.bat -- --profile audience --display 1`

（创建桌面快捷方式：右键点击 `start_windows.bat` → *发送到 → 桌面快捷方式*。）

按键：**空格键** = 大按钮，**P** = 暂停，**Esc** = 紧急停止。参见 [README](../../README.zh.md)。

## 5. 连接灯光和喇叭（可选）

把 ESP32 板插入 USB 端口，程序会自动找到它。如果没有找到：

1. 打开*设备管理器 → 端口 (COM 和 LPT)*，记下端口，例如 `COM7`。
2. 用 `scripts\start_windows.bat --serial-port COM7` 启动。

一些廉价的板子需要 USB 串口驱动（CH340 或 CP210x）；如果没有出现 COM 端口，请安装芯片厂商提供的驱动。
板子的固件在 [`firmware/`](../../firmware/) 中；新板子请按照[刷写指南](../flashing.md)（英文）刷写。

## 更新

下载新的 ZIP（或运行 `git pull`），然后再次运行 `scripts\setup_windows.bat`。你的设置保存在用户配置目录
（`%LOCALAPPDATA%\archerytimer`），不在项目文件夹中。

## 故障排除

| 问题 | 解决办法 |
| --- | --- |
| "Python was not found" | 重新安装 Python 并勾选 *Add python.exe to PATH*，或重启电脑后再次运行安装 |
| 窗口打开后立即关闭 | 在终端（`cmd`）中运行 `scripts\start_windows.bat` 查看错误信息 |
| 硬件状态显示"没有灯光" | 检查 USB 线（必须支持数据传输）、端口和驱动；见第 5 步 |
| 日志 | `%LOCALAPPDATA%\archerytimer\logs`（把路径粘贴到文件资源管理器的地址栏中打开） |

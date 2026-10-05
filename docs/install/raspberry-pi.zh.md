# 在 Raspberry Pi 上安装（电视一体机）

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · **中文** · [हिन्दी](raspberry-pi.hi.md) · [Español](raspberry-pi.es.md) · [Français](raspberry-pi.fr.md) · [العربية](raspberry-pi.ar.md) · [বাংলা](raspberry-pi.bn.md) · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.zh.md) · [Linux](linux.zh.md) · [返回 README](../../README.zh.md)

最终效果：Pi 开机后直接在电视上显示计时器，无需用键盘登录。计时核心作为后台服务运行，即使显示程序重启，灯光和声音也会继续工作。

**已测试的目标：** Raspberry Pi 2 Model B、Raspberry Pi OS Lite 32 位（Trixie）、HDMI 电视。其他型号的 Pi 应该也能运行，但尚未测试。
所需时间：约 30 分钟。

> 安装程序具体做了哪些设置：[deployment.md](../deployment.md)（英文）。

## 你需要准备

- 带电源的 Raspberry Pi、microSD 卡（8 GB 或更大）、HDMI 线，以及电视或显示器
- 一台用于准备存储卡的电脑，以及安装期间 Pi 的网络连接（网线最简单）
- 可选：接在 USB 口上的 ESP32 灯光/喇叭板、USB 键盘或翻页笔

## 1. 把操作系统写入存储卡

1. 在你的电脑上从 <https://www.raspberrypi.com/software/> 安装 **Raspberry Pi Imager**。
2. 选择你的 Pi 型号，然后选择 *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***。
3. 选择 SD 卡，点击 *Next*，再点击 *Edit settings*（系统定制），并设置：
   - **主机名**（例如 `archerytimer`）以及**用户名和密码**（请记住；该用户将成为一体机用户），
   - 如果不使用网线，设置你的 **Wi-Fi**，并设置时区，
   - *Services → Enable SSH*。
4. 写入存储卡，把它插入 Pi，连接 HDMI 和网络，然后通电。等待几分钟完成首次启动。

## 2. 登录

在你的电脑上（Windows 10/11 和 Linux 都自带 `ssh`）：

```bash
ssh <username>@archerytimer.local
```

（如果找不到这个名字，请使用路由器上显示的 Pi 的 IP 地址。）也可以把键盘接到 Pi 上，在电视上登录。

## 3. 下载项目

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. 运行安装程序

```bash
sudo bash scripts/install_pi.sh
```

这需要几分钟。它会安装所需软件包，把程序复制到 `/opt/archerytimer`，设置后台服务，启用 GPU 显示叠加层，并让 Pi
在第一个控制台自动登录并在那里启动计时器。完成后重启：

```bash
sudo reboot
```

重启后计时器会自动出现在电视上。使用鼠标或键盘操作（空格键 = 大按钮，Esc = 紧急停止）。

选项：`--no-ui` 用于没有显示器、只负责灯光/声音的盒子，`--user NAME` 用于指定一体机用户。运行 `scripts/install_pi.sh --help` 查看完整列表。

## 5. 连接灯光和喇叭（可选）

把 ESP32 板插入 Pi 的 USB 口，程序会自动找到它（一体机用户已在 `dialout` 组中）。状态显示在程序的硬件菜单里。
刷写新板子请参见[刷写指南](../flashing.md)（英文）；固件源码在 [`firmware/`](../../firmware/) 中。

## 设置

额外的启动选项保存在两个小文件中，用 `sudo nano` 编辑：

| 文件 | 用途 | 示例 |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | 后台核心 | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | 显示端 | `UI_ARGS="--lang sv --profile audience"` |

修改后生效：`sudo systemctl restart archerytimer-core`，显示端则需要重启（或退出控制台登录）。多块 Pi 联合使用（一个主机、若干从机）
请参见 [cluster.md](../cluster.md)（英文）。

## 更新

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

你的设置以及 `/etc/archerytimer` 中的文件都会保留。

**在 Windows 电脑上**（Pi 上没有 git 时）：`.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
（复制项目并运行安装程序；加上 `-Reboot` 可在完成后重启）。

## 在电视上获得普通的命令行

一体机会占用 Pi 的第一个控制台。要在 Pi 上操作，请从另一台电脑通过 **SSH** 登录，或者创建文件 `~/.no-kiosk`
（`touch ~/.no-kiosk`）并重启，得到普通命令行。删除该文件并重启即可恢复计时器。

## 故障排除

| 问题 | 解决办法 |
| --- | --- |
| 重启后黑屏 | 通电后等待 1-2 分钟。检查 HDMI。若仍然如此，通过 SSH 登录，运行 `journalctl -u archerytimer-core -n 50` 并查看 `~/.local/share/archerytimer/logs/ui.log` |
| 只有电视比 Pi 晚开机时才黑屏 | 在 `/boot/firmware/config.txt` 中加入 `hdmi_force_hotplug=1`，然后重启 |
| 显示正常但提示"未连接到核心" | `systemctl status archerytimer-core`；用 `sudo systemctl restart archerytimer-core` 重启 |
| 没有灯光/喇叭 | 检查 USB 线是否支持数据传输；`ls /dev/ttyACM* /dev/ttyUSB*` 应该能列出一个设备 |
| 检查运行环境 | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| 全部卸载 | `sudo bash scripts/uninstall_pi.sh`（保留你的设置） |

实时日志：`journalctl -u archerytimer-core -f`。更多内部细节：[deployment.md](../deployment.md)（英文）。

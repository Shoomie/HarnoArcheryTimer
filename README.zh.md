# Archery Timer（射箭计时器）

[English](README.md) · [Svenska](README.sv.md) · **中文** · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [اردو](README.ur.md)

一个开源的射箭计时系统。它在比赛和训练中负责射击计时，把时间显示在电视或显示器上，并通过 USB 控制交通灯和喇叭。
它为小型射箭俱乐部而做，由志愿者操作，因此屏幕上只有一个明确告诉你"下一步做什么"的大按钮，以及一个始终可见的紧急停止按钮。

- 可在 **Windows 10/11**、**Linux**、**Raspberry Pi**（2B 及以上，作为电视一体机）和 macOS 上运行。
- 界面支持英语（默认）和瑞典语。
- 即使显示程序崩溃，计时、灯光和声音也会继续运行。
- 可选 ESP32 板用于灯光和喇叭，可选第二块屏幕，也可在同一网络中使用多台设备。

> **正式比赛前：** `config/` 中的时间设置都是**占位值**，并不是经过确认的 World Archery / SBF 规则。请对照现行规则核对，
> 并编辑 TOML 文件（俱乐部无需改代码即可添加自己的预设）。系统已在一台 Windows 电脑、一台 Linux 电脑和一台带有
> ESP32-C3 与 WROOM-32D 模块的 Raspberry Pi 2B 上完整测试过。尚未覆盖：连续 4 小时运行测试、ESP32-S3 板，以及远距离无线电测试。

## 进行一次训练或比赛

1. 启动程序（见下面的"安装"）。按 **空格键** 或点击大按钮：打开设置。
2. 选择一张卡片（例如 *Indoor 18 m*），选择射击线和轮数，然后开始。
3. 大按钮始终显示下一步会发生什么：开始一轮、下一轮、继续。**P** 暂停。**Esc** 是紧急停止：红灯并静音，
   始终只需按一次，无需确认。

屏幕上显示一个大信号灯（带符号，而不只靠颜色）、倒计时、当前轮次和射击线，以及用通俗语言描述的设备状态。

## 安装

请选择你的系统。每份指南都从零开始，一步一步到计时器运行起来。

| 系统 | 指南 | 简要步骤 |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.zh.md](docs/install/windows.zh.md) | 安装 Python，下载项目，双击 `scripts\setup_windows.bat`，然后运行 `scripts\start_windows.bat` |
| **Linux**（以及 macOS） | [docs/install/linux.zh.md](docs/install/linux.zh.md) | `scripts/setup_desktop.sh`，然后 `scripts/start.sh` |
| **Raspberry Pi**（电视一体机） | [docs/install/raspberry-pi.zh.md](docs/install/raspberry-pi.zh.md) | 烧录 Pi OS Lite，`git clone`，`sudo scripts/install_pi.sh`，重启 |

### 快速开始（任何桌面电脑，无需硬件）

1. 安装 **Python 3.9 或更高版本**（[python.org](https://www.python.org/downloads/)；Linux 上通常用
   `sudo apt install python3 python3-venv python3-pip`）。
2. 下载项目：在 GitHub 上点击 **Code → Download ZIP** 并解压，或使用
   `git clone <repository-url>`。
3. 在项目文件夹中先运行一次安装脚本，再运行启动脚本：

   | | 安装（仅一次） | 启动 |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` 表示"没有连接灯光硬件"。插上 ESP32 板时请去掉它，程序会自动找到该板。

### 操作

| 按键 | 作用 |
| --- | --- |
| **空格键** / Enter | 大按钮：下一步要做的事（打开设置、开始一轮……） |
| **P** | 暂停 / 继续 |
| **Esc** | **紧急停止**：红灯并静音，始终只需按一次 |
| S | 结束本轮 |
| N / Backspace | 下一阶段 / 返回（在"停止"或"下一步"之后 5 秒内，"返回"显示为 *撤销*） |
| M / F1 | 菜单：新建会话、计时器、设置、硬件状态、网络、声音、退出 |

所有操作也都可以用鼠标完成。可当作键盘使用的演示翻页笔和脚踏开关同样可用，ESP32 模块上的按钮也可以。
完整列表：[docs/ui.md](docs/ui.md)（英文）。

### 常用启动选项

把它们加在启动脚本后面，显示选项放在 `--` 之后：

```text
scripts/start.sh --no-serial                      无硬件演示
scripts/start.sh --serial-port COM7               自行选择 USB 端口（Linux：/dev/ttyACM0）
scripts/start.sh -- --fullscreen --lang sv        全屏，瑞典语界面
scripts/start.sh -- --profile audience --display 1   在第二台显示器上显示观众屏幕，无控制按钮
```

在 Windows 上请使用 `scripts\start_windows.bat` 代替 `scripts/start.sh`。

## 灯光、喇叭和更多设备

技术文档为英文。安装指南提供 11 种语言版本。

| 我想要…… | 阅读 |
| --- | --- |
| 连接交通灯和喇叭（ESP32 板、接线、引脚） | [docs/firmware.md](docs/firmware.md) |
| 给 ESP32 模块刷写固件（Windows、Linux、macOS；无需编译器） | [docs/flashing.md](docs/flashing.md)：`scripts\flash.bat` 或 `sh scripts/flash.sh` |
| 设置喇叭和扬声器、声音测试 | [docs/audio.md](docs/audio.md) |
| 把多块屏幕、电脑或 Pi 当作一个计时器使用（局域网或无线电） | [docs/cluster.md](docs/cluster.md) |
| 无线灯箱和遥控按钮 | [docs/mesh.md](docs/mesh.md) |

## 文档

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | 全部文档索引 |
| [docs/install/](docs/install/) | 安装指南（11 种语言） |
| [docs/ui.md](docs/ui.md) | 屏幕、按键、显示配置 |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | USB 串口协议；核心到显示端的协议 |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Raspberry Pi 内部细节；计时与渲染测量 |
| [structure.md](structure.md) | 源码目录中各部分的位置 |

## 仓库结构

```text
src/archerytimer/   程序本体（核心服务、界面客户端、硬件、音频、IPC）
config/             计时序列和设置预设（TOML，占位值）
locales/            所有界面文字，en.toml 和 sv.toml
assets/             字体（Inter，OFL）
firmware/           ESP32 固件（PlatformIO）、预编译镜像、共享测试向量
scripts/            安装/启动脚本、Raspberry Pi 安装程序、刷写菜单、性能测试
docs/               文档
tests/  tools/      测试套件、Mesh 网络模拟器
```

## 开发

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # 测试（部分在 Windows 上会跳过）
ruff check . && ruff format --check .
mypy
```

如需翻译文档或界面，请见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目规则与架构：[CLAUDE.md](CLAUDE.md)。
性能测量：[docs/benchmarks.md](docs/benchmarks.md)。

## 许可证

MIT（见 [LICENSE](LICENSE)）：可自由使用、复制、修改、分享和销售，不限用途，不限地区。欢迎在同一许可证下贡献。
第三方部分保留各自的开放许可证，列在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 中（例如 Inter 字体，`assets/fonts/OFL.txt`）。

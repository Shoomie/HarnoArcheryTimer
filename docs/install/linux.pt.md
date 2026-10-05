# Instalar em Linux de ambiente de trabalho (e macOS)

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · [Français](linux.fr.md) · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · **Português** · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.pt.md) · [Raspberry Pi](raspberry-pi.pt.md) · [Voltar ao README](../../README.pt.md)

Para um Raspberry Pi que arranca diretamente no cronómetro, use antes o [guia do Raspberry Pi](raspberry-pi.pt.md).
Esta página é para um PC ou portátil Linux normal com ambiente gráfico (testado na família Debian/Ubuntu; outras
funcionam se tiverem Python 3.9+).

## 1. Instalar os requisitos

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`. Arch: `sudo pacman -S git python sdl2`.

macOS: instale o Python 3 a partir de <https://www.python.org/downloads/> (ou `brew install python`).

## 2. Transferir o projeto

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

Sem git? Transfira o ZIP da página do GitHub (**Code → Download ZIP**) e descompacte-o.

## 3. Instalação (uma só vez)

```bash
scripts/setup_desktop.sh
```

Cria um ambiente privado em `.venv` e instala lá o cronómetro. Se o script não for executável, execute-o com
`bash scripts/setup_desktop.sh`.

## 4. Iniciar o cronómetro

```bash
scripts/start.sh
```

- Demonstração sem equipamento de luzes: `scripts/start.sh --no-serial`
- Ecrã inteiro: `scripts/start.sh -- --fullscreen`
- Interface em sueco: `scripts/start.sh -- --lang sv` (o idioma também se muda no menu de definições)
- Ecrã para o público no segundo monitor, sem controlos: `scripts/start.sh -- --profile audience --display 1`

Teclas: **Espaço** = o botão grande, **P** = pausa, **Esc** = paragem de emergência. Veja o
[README](../../README.pt.md).

## 5. Ligar as luzes e a buzina (opcional)

1. Não é preciso fazer nada à mão: `scripts/setup_desktop.sh` (passo 3) já deu a este computador acesso à placa
   (grupo série mais uma regra udev que também mantém o ModemManager afastado; pede a sua palavra-passe uma vez;
   `--no-system` ignora isto) e `scripts/start.sh` funciona sem terminar a sessão. Se o ignorou, execute
   `sudo usermod -aG dialout $USER` e inicie sessão de novo.

2. Ligue a placa ESP32. É encontrada automaticamente. Para escolher a porta, descubra-a com
   `ls /dev/ttyACM* /dev/ttyUSB*` e inicie com `scripts/start.sh --serial-port /dev/ttyACM0`.

O firmware da placa está em [`firmware/`](../../firmware/); para gravar uma placa nova use o
[guia de gravação](../flashing.md) (em inglês).

## Atualizar

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

As definições ficam em `~/.local/share/archerytimer` (macOS: `~/Library/Application Support/archerytimer`).

## Resolução de problemas

| Problema | O que fazer |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` e repita a instalação |
| Sem janela / erro SDL | Execute dentro de uma sessão de ambiente gráfico (não por SSH simples); instale `libsdl2-2.0-0` |
| «Permission denied» na porta série | Passo 5: grupo `dialout`, depois termine e volte a iniciar sessão |
| Sem som nas colunas do PC | Verifique o dispositivo de saída nas definições de som do programa; o ALSA/PulseAudio tem de funcionar primeiro com outras aplicações |
| Registos | `~/.local/share/archerytimer/logs/` |

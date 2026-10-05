# Instalar num Raspberry Pi (quiosque de TV)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · [हिन्दी](raspberry-pi.hi.md) · [Español](raspberry-pi.es.md) · [Français](raspberry-pi.fr.md) · [العربية](raspberry-pi.ar.md) · [বাংলা](raspberry-pi.bn.md) · **Português** · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.pt.md) · [Linux](linux.pt.md) · [Voltar ao README](../../README.pt.md)

Resultado: o Pi arranca diretamente no cronómetro na TV, sem início de sessão com teclado. O núcleo do cronómetro corre
como serviço em segundo plano e mantém luzes e som mesmo que o programa do ecrã reinicie.

**Alvo testado:** Raspberry Pi 2 Model B, Raspberry Pi OS Lite de 32 bits (Trixie), TV HDMI. Outros modelos de Pi
deverão funcionar, mas não foram testados. Tempo necessário: cerca de 30 minutos.

> O que o instalador configura, em detalhe: [deployment.md](../deployment.md) (em inglês).

## O que precisa

- Raspberry Pi com fonte de alimentação, cartão microSD (8 GB ou mais), cabo HDMI e uma TV ou monitor
- Um computador para preparar o cartão e uma ligação de rede para o Pi (por cabo é o mais fácil) durante a instalação
- Opcional: a placa ESP32 de luzes/buzina numa porta USB, um teclado USB ou um comando de apresentações

## 1. Gravar o sistema operativo no cartão

1. No seu computador instale o **Raspberry Pi Imager** a partir de <https://www.raspberrypi.com/software/>.
2. Escolha o seu modelo de Pi e depois *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***.
3. Escolha o cartão SD, prima *Next*, depois *Edit settings* (personalização do sistema) e defina:
   - um **nome de anfitrião** (por exemplo `archerytimer`) e um **nome de utilizador e palavra-passe** (guarde-os; este
     utilizador passa a ser o utilizador do quiosque),
   - o seu **Wi-Fi**, se não usar cabo, e o seu fuso horário,
   - *Services → Enable SSH*.
4. Grave o cartão, coloque-o no Pi, ligue o HDMI e a rede e alimente-o. Espere uns minutos pelo primeiro arranque.

## 2. Iniciar sessão

A partir do seu computador (o Windows 10/11 e o Linux têm `ssh`):

```bash
ssh <username>@archerytimer.local
```

(Se o nome não for encontrado, use o endereço IP do Pi indicado pelo seu router.) Em alternativa, ligue um teclado ao Pi
e inicie sessão na TV.

## 3. Transferir o projeto

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. Executar o instalador

```bash
sudo bash scripts/install_pi.sh
```

Demora vários minutos. Instala os pacotes necessários, copia o programa para `/opt/archerytimer`, configura o serviço
em segundo plano, ativa a camada de ecrã por GPU e faz com que o Pi inicie sessão sozinho na primeira consola e aí
arranque o cronómetro. Quando terminar, reinicie:

```bash
sudo reboot
```

Depois de reiniciar, o cronómetro aparece sozinho na TV. Use o rato ou o teclado (Espaço = botão grande,
Esc = paragem de emergência).

Opções: `--no-ui` para uma caixa só de luzes/som sem ecrã, `--user NAME` para escolher o utilizador do quiosque.
Execute `scripts/install_pi.sh --help` para ver a lista.

## 5. Ligar as luzes e a buzina (opcional)

Ligue a placa ESP32 a uma porta USB do Pi. É encontrada automaticamente (o utilizador do quiosque já está no grupo
`dialout`). O estado aparece no menu de equipamento do programa. Para gravar uma placa nova, veja o
[guia de gravação](../flashing.md) (em inglês); o código do firmware está em [`firmware/`](../../firmware/).

## Definições

As opções de arranque adicionais ficam em dois ficheiros pequenos. Edite-os com `sudo nano`:

| Ficheiro | Serve para | Exemplo |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | o núcleo em segundo plano | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | o ecrã | `UI_ARGS="--lang sv --profile audience"` |

Para aplicar: `sudo systemctl restart archerytimer-core` e reinicie (ou termine a sessão da consola) para o ecrã. Para
usar vários Pi em conjunto (um líder e seguidores), veja [cluster.md](../cluster.md) (em inglês).

## Atualizar

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

As suas definições e os ficheiros em `/etc/archerytimer` são mantidos.

**A partir de um computador Windows**, sem git no Pi: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(copia o projeto e executa o instalador; acrescente `-Reboot` para reiniciar no fim).

## Obter uma shell normal na TV

O quiosque ocupa a primeira consola do Pi. Para trabalhar no próprio Pi, inicie sessão por **SSH** a partir de outro
computador, ou crie o ficheiro `~/.no-kiosk` (`touch ~/.no-kiosk`) e reinicie para obter uma linha de comandos normal.
Apague o ficheiro e reinicie para recuperar o cronómetro.

## Resolução de problemas

| Problema | O que fazer |
| --- | --- |
| Ecrã preto depois de reiniciar | Espere 1-2 minutos depois de ligar. Verifique o HDMI. Se persistir, entre por SSH, execute `journalctl -u archerytimer-core -n 50` e veja `~/.local/share/archerytimer/logs/ui.log` |
| O ecrã fica preto só se a TV for ligada depois do Pi | Acrescente `hdmi_force_hotplug=1` a `/boot/firmware/config.txt` e reinicie |
| O ecrã funciona mas diz «sem ligação ao núcleo» | `systemctl status archerytimer-core`; reinicie-o com `sudo systemctl restart archerytimer-core` |
| Sem luzes/buzina | Verifique se o cabo USB transmite dados; `ls /dev/ttyACM* /dev/ttyUSB*` deve mostrar um dispositivo |
| Verificar o ambiente | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| Remover tudo | `sudo bash scripts/uninstall_pi.sh` (mantém as suas definições) |

Registos em direto: `journalctl -u archerytimer-core -f`. Mais detalhes internos: [deployment.md](../deployment.md) (em inglês).

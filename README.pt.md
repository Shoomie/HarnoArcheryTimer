# Archery Timer (cronómetro de tiro com arco)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · **Português** · [Русский](README.ru.md) · [اردو](README.ur.md)

Um relógio de tiro com arco de código aberto. Controla o tempo de tiro em competições e treinos, mostra-o numa televisão
ou monitor e comanda semáforos e uma buzina por USB. Foi feito para um pequeno clube de tiro com arco e para voluntários
sem formação técnica: o ecrã tem um único botão evidente para o que acontece a seguir e uma paragem de emergência sempre
visível.

- Funciona em **Windows 10/11**, **Linux**, **Raspberry Pi** (2B ou superior, como quiosque de TV) e macOS.
- Interface em inglês (predefinição) e sueco.
- O cronómetro, as luzes e o som continuam a funcionar mesmo que o ecrã bloqueie.
- Placa ESP32 opcional para luzes e buzina, segundos ecrãs opcionais e vários dispositivos na mesma rede.

> **Antes de uma competição oficial:** os tempos em `config/` são **provisórios**, não são regras confirmadas da World
> Archery / SBF. Confirme-os com o regulamento em vigor e edite os ficheiros TOML (os clubes podem acrescentar as suas
> próprias predefinições sem alterar o código). O sistema foi testado de ponta a ponta num PC Windows, num PC Linux e
> num Raspberry Pi 2B com módulos ESP32-C3 e WROOM-32D. Ainda por cobrir: um teste contínuo de 4 horas, placas ESP32-S3
> e testes de rádio de longo alcance.

## Conduzir uma sessão

1. Inicie o programa (veja Instalação abaixo). Prima **Espaço** ou o botão grande: abre-se a configuração.
2. Escolha um cartão (por exemplo *Indoor 18 m*), as linhas e o número de séries, e comece.
3. O botão grande diz sempre o que acontece a seguir: iniciar a série, próxima série, retomar. **P** pausa. **Esc** é a
   paragem de emergência: luzes vermelhas e silêncio, sempre com um só toque e sem confirmação.

O ecrã mostra uma luz grande (com um símbolo, não só cor), a contagem decrescente, a série e a linha, e o estado do
equipamento em palavras simples.

## Instalação

Escolha o seu sistema. Cada guia vai passo a passo do zero até ao cronómetro a funcionar.

| Sistema | Guia | Versão curta |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.pt.md](docs/install/windows.pt.md) | Instalar o Python, transferir o projeto, fazer duplo clique em `scripts\setup_windows.bat` e depois em `scripts\start_windows.bat` |
| **Linux** (e macOS) | [docs/install/linux.pt.md](docs/install/linux.pt.md) | `scripts/setup_desktop.sh`, depois `scripts/start.sh` |
| **Raspberry Pi** (quiosque de TV) | [docs/install/raspberry-pi.pt.md](docs/install/raspberry-pi.pt.md) | Gravar o Pi OS Lite, `git clone`, `sudo scripts/install_pi.sh`, reiniciar |

### Início rápido (qualquer computador, sem equipamento)

1. Instale o **Python 3.9 ou mais recente** ([python.org](https://www.python.org/downloads/); em Linux normalmente
   `sudo apt install python3 python3-venv python3-pip`).
2. Transfira o projeto: no GitHub prima **Code → Download ZIP** e descompacte, ou
   `git clone <repository-url>`.
3. Na pasta do projeto execute uma vez o script de instalação e depois o de arranque:

   | | Instalação (uma vez) | Arranque |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` significa «sem equipamento de luzes ligado». Retire-o quando houver uma placa ESP32 ligada; o programa
   encontra-a sozinho.

### Controlos

| Tecla | Ação |
| --- | --- |
| **Espaço** / Enter | O botão grande: o que vier a seguir (abrir a configuração, iniciar a série, ...) |
| **P** | Pausar / retomar |
| **Esc** | **Paragem de emergência**: luzes vermelhas e silêncio, sempre com um só toque |
| S | Parar a série |
| N / Backspace | Fase seguinte / voltar (durante 5 segundos após Parar ou Seguinte, Voltar aparece como *Anular*) |
| M / F1 | Menu: nova sessão, temporizadores, definições, estado do equipamento, rede, som, sair |

Tudo funciona também com o rato. Os comandos de apresentação e os pedais que funcionam como teclado também servem, tal
como os botões dos módulos ESP32. Lista completa: [docs/ui.md](docs/ui.md) (em inglês).

### Opções de arranque úteis

Acrescente-as depois do script de arranque; as opções de ecrã vão depois de `--`:

```text
scripts/start.sh --no-serial                      demonstração sem equipamento
scripts/start.sh --serial-port COM7               escolher a porta USB (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        ecrã inteiro, interface em sueco
scripts/start.sh -- --profile audience --display 1   ecrã para o público no segundo monitor, sem controlos
```

No Windows use `scripts\start_windows.bat` em vez de `scripts/start.sh`.

## Luzes, buzina e mais dispositivos

A documentação técnica está em inglês. Os guias de instalação existem em 11 idiomas.

| Quero... | Ler |
| --- | --- |
| Ligar semáforos e uma buzina (placa ESP32, cablagem, pinos) | [docs/firmware.md](docs/firmware.md) |
| Gravar firmware num módulo ESP32 (Windows, Linux, macOS; não é preciso compilador) | [docs/flashing.md](docs/flashing.md): `scripts\flash.bat` ou `sh scripts/flash.sh` |
| Configurar a buzina e as colunas, teste de som | [docs/audio.md](docs/audio.md) |
| Usar vários ecrãs, PC ou Pi como um só cronómetro (LAN ou rádio) | [docs/cluster.md](docs/cluster.md) |
| Caixas de luzes sem fios e botões remotos | [docs/mesh.md](docs/mesh.md) |

## Documentação

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | Índice de toda a documentação |
| [docs/install/](docs/install/) | Guias de instalação (11 idiomas) |
| [docs/ui.md](docs/ui.md) | Ecrãs, teclas, perfis de visualização |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | Protocolo série USB; protocolo do núcleo para o ecrã |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Detalhes internos do Raspberry Pi; medições de tempo e de desenho |
| [structure.md](structure.md) | Onde está cada coisa no código-fonte |

## Estrutura do repositório

```text
src/archerytimer/   o programa (serviço núcleo, cliente de interface, equipamento, áudio, IPC)
config/             sequências de tempos e predefinições (TOML, provisórias)
locales/            todos os textos da interface, en.toml e sv.toml
assets/             tipo de letra (Inter, OFL)
firmware/           firmware ESP32 (PlatformIO), imagens pré-compiladas, vetores de teste partilhados
scripts/            scripts de instalação/arranque, instalador do Raspberry Pi, menu de gravação, medições de desempenho
docs/               documentação
tests/  tools/      conjunto de testes, simulador de rede em malha
```

## Desenvolvimento

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # testes (alguns são ignorados no Windows)
ruff check . && ruff format --check .
mypy
```

Para traduzir a documentação ou a interface, veja [CONTRIBUTING.md](CONTRIBUTING.md). Regras e arquitetura do projeto:
[CLAUDE.md](CLAUDE.md). Medições: [docs/benchmarks.md](docs/benchmarks.md).

## Licença

MIT (veja [LICENSE](LICENSE)): livre para usar, copiar, alterar, partilhar e vender, para qualquer fim e em qualquer
lugar. As contribuições são bem-vindas sob a mesma licença. As partes de terceiros mantêm as suas próprias licenças
abertas, listadas em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (por exemplo o tipo de letra Inter,
`assets/fonts/OFL.txt`).

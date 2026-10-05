# Instalar no Windows 10/11

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · [हिन्दी](windows.hi.md) · [Español](windows.es.md) · [Français](windows.fr.md) · [العربية](windows.ar.md) · [বাংলা](windows.bn.md) · **Português** · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.pt.md) · [Raspberry Pi](raspberry-pi.pt.md) · [Voltar ao README](../../README.pt.md)

Tempo necessário: cerca de 10 minutos. Só precisa de ligação à internet na primeira instalação.

## 1. Instalar o Python

1. Vá a <https://www.python.org/downloads/> e transfira o Python 3 mais recente (3.9 ou superior).
2. Execute o instalador. **Marque «Add python.exe to PATH»** no primeiro ecrã e prima *Install Now*.

## 2. Transferir o projeto

Escolha uma opção:

- **ZIP (a mais fácil):** na página do GitHub prima **Code → Download ZIP**, depois clique com o botão direito no
  ficheiro e escolha *Extrair tudo*. Ponha a pasta num local simples, por exemplo `C:\ArcheryTimer`.
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. Instalação (uma só vez)

Abra a pasta do projeto e **faça duplo clique em `scripts\setup_windows.bat`**. Cria um ambiente Python privado em
`.venv` e instala o que o cronómetro precisa. Espere por «Done».

Se o Windows SmartScreen avisar sobre o ficheiro, escolha *Mais informações → Executar mesmo assim* (é um script de
texto simples que pode ler no Bloco de notas).

## 4. Iniciar o cronómetro

Faça duplo clique em **`scripts\start_windows.bat`**. Abre-se uma janela com o cronómetro.

- Ainda sem equipamento de luzes? Inicie-o num terminal com `scripts\start_windows.bat --no-serial` para uma demonstração.
- Ecrã inteiro numa TV: `scripts\start_windows.bat -- --fullscreen`
- Interface em sueco: `scripts\start_windows.bat -- --lang sv` (o idioma também se muda no menu de definições)
- Segundo monitor para o público, sem controlos: `scripts\start_windows.bat -- --profile audience --display 1`

(Para criar um atalho no ambiente de trabalho: botão direito em `start_windows.bat` → *Enviar para → Ambiente de trabalho (criar atalho)*.)

Teclas: **Espaço** = o botão grande, **P** = pausa, **Esc** = paragem de emergência. Veja o
[README](../../README.pt.md).

## 5. Ligar as luzes e a buzina (opcional)

Ligue a placa ESP32 a uma porta USB. O programa encontra-a sozinho. Se não encontrar:

1. Abra o *Gestor de Dispositivos → Portas (COM e LPT)* e anote a porta, por exemplo `COM7`.
2. Inicie com `scripts\start_windows.bat --serial-port COM7`.

Algumas placas baratas precisam de um controlador USB-série (CH340 ou CP210x); se não aparecer nenhuma porta COM,
instale o controlador do fabricante do chip. O firmware da placa está em [`firmware/`](../../firmware/); para gravar uma
placa nova use o [guia de gravação](../flashing.md) (em inglês).

## Atualizar

Transfira o novo ZIP (ou `git pull`) e execute de novo `scripts\setup_windows.bat`. As suas definições ficam no seu
perfil de utilizador (`%LOCALAPPDATA%\archerytimer`), não na pasta do projeto.

## Resolução de problemas

| Problema | O que fazer |
| --- | --- |
| «Python was not found» | Reinstale o Python marcando *Add python.exe to PATH*, ou repita a instalação depois de reiniciar o PC |
| A janela abre e fecha | Execute `scripts\start_windows.bat` num terminal (`cmd`) para ver a mensagem de erro |
| O estado do equipamento diz «sem luzes» | Verifique o cabo USB (tem de transmitir dados), a porta e o controlador; veja o passo 5 |
| Registos | `%LOCALAPPDATA%\archerytimer\logs` (cole o caminho no Explorador de Ficheiros) |

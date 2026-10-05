# Instalar en Linux de escritorio (y macOS)

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · **Español** · [Français](linux.fr.md) · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.es.md) · [Raspberry Pi](raspberry-pi.es.md) · [Volver al README](../../README.es.md)

Para una Raspberry Pi que arranca directamente en el temporizador, use mejor la [guía de Raspberry Pi](raspberry-pi.es.md).
Esta página es para un PC o portátil Linux normal con escritorio (probado en la familia Debian/Ubuntu; otras funcionan
si tienen Python 3.9+).

## 1. Instalar los requisitos

Debian / Ubuntu / Mint:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora: `sudo dnf install git python3 python3-pip SDL2`. Arch: `sudo pacman -S git python sdl2`.

macOS: instale Python 3 desde <https://www.python.org/downloads/> (o `brew install python`).

## 2. Descargar el proyecto

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

¿Sin git? Descargue el ZIP desde la página de GitHub (**Code → Download ZIP**) y descomprímalo.

## 3. Instalación (una sola vez)

```bash
scripts/setup_desktop.sh
```

Crea un entorno privado en `.venv` e instala en él el temporizador. Si el script no es ejecutable, ejecútelo como
`bash scripts/setup_desktop.sh`.

## 4. Iniciar el temporizador

```bash
scripts/start.sh
```

- Demostración sin hardware de luces: `scripts/start.sh --no-serial`
- Pantalla completa: `scripts/start.sh -- --fullscreen`
- Interfaz en sueco: `scripts/start.sh -- --lang sv` (el idioma también se cambia en el menú de ajustes)
- Pantalla para el público en el segundo monitor, sin controles: `scripts/start.sh -- --profile audience --display 1`

Teclas: **Espacio** = el botón grande, **P** = pausa, **Esc** = parada de emergencia. Véase el
[README](../../README.es.md).

## 5. Conectar las luces y la bocina (opcional)

1. No hay que hacer nada a mano: `scripts/setup_desktop.sh` (paso 3) ya dio a este ordenador acceso a la placa
   (grupo serie más una regla udev que además mantiene a ModemManager alejado; pide su contraseña una vez;
   `--no-system` lo omite) y `scripts/start.sh` funciona sin cerrar la sesión. Si lo omitió, ejecute
   `sudo usermod -aG dialout $USER` y vuelva a iniciar sesión.

2. Enchufe la placa ESP32. Se encuentra automáticamente. Para elegir usted el puerto, búsquelo con
   `ls /dev/ttyACM* /dev/ttyUSB*` e inicie con `scripts/start.sh --serial-port /dev/ttyACM0`.

El firmware de la placa está en [`firmware/`](../../firmware/); para flashear una placa nueva use la
[guía de flasheo](../flashing.md) (en inglés).

## Actualizar

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

Los ajustes se guardan en `~/.local/share/archerytimer` (macOS: `~/Library/Application Support/archerytimer`).

## Solución de problemas

| Problema | Qué hacer |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` y repita la instalación |
| Sin ventana / error de SDL | Asegúrese de ejecutarlo dentro de una sesión de escritorio (no por SSH simple); instale `libsdl2-2.0-0` |
| «Permission denied» en el puerto serie | Paso 5: grupo `dialout`, luego cierre sesión y vuelva a entrar |
| Sin sonido en los altavoces del PC | Compruebe el dispositivo de salida en los ajustes de sonido del programa; ALSA/PulseAudio debe funcionar antes con otras aplicaciones |
| Registros | `~/.local/share/archerytimer/logs/` |

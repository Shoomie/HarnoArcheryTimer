# Instalar en una Raspberry Pi (quiosco de TV)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · [हिन्दी](raspberry-pi.hi.md) · **Español** · [Français](raspberry-pi.fr.md) · [العربية](raspberry-pi.ar.md) · [বাংলা](raspberry-pi.bn.md) · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.es.md) · [Linux](linux.es.md) · [Volver al README](../../README.es.md)

Resultado: la Pi arranca directamente en el temporizador en la TV, sin inicio de sesión con teclado. El núcleo del
temporizador se ejecuta como servicio en segundo plano y mantiene luces y sonido aunque el programa de pantalla se reinicie.

**Objetivo probado:** Raspberry Pi 2 Model B, Raspberry Pi OS Lite de 32 bits (Trixie), TV con HDMI. Otros modelos de Pi
deberían funcionar, pero no están probados. Tiempo necesario: unos 30 minutos.

> Qué configura el instalador, en detalle: [deployment.md](../deployment.md) (en inglés).

## Qué necesita

- Raspberry Pi con fuente de alimentación, tarjeta microSD (8 GB o más), cable HDMI y una TV o monitor
- Un ordenador para preparar la tarjeta y una conexión de red para la Pi (por cable es lo más fácil) durante la instalación
- Opcional: la placa ESP32 de luces/bocina en un puerto USB, un teclado USB o un mando de presentaciones

## 1. Grabar el sistema operativo en la tarjeta

1. En su ordenador instale **Raspberry Pi Imager** desde <https://www.raspberrypi.com/software/>.
2. Elija su modelo de Pi y después *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***.
3. Elija la tarjeta SD, pulse *Next*, luego *Edit settings* (personalización del sistema) y configure:
   - un **nombre de host** (por ejemplo `archerytimer`) y un **usuario y contraseña** (recuérdelos; este usuario se
     convierte en el usuario del quiosco),
   - su **Wi-Fi** si no usa cable, y su zona horaria,
   - *Services → Enable SSH*.
4. Grabe la tarjeta, colóquela en la Pi, conecte HDMI y red, y encienda. Espere un par de minutos al primer arranque.

## 2. Iniciar sesión

Desde su ordenador (Windows 10/11 y Linux tienen `ssh`):

```bash
ssh <username>@archerytimer.local
```

(Si no se encuentra el nombre, use la dirección IP de la Pi que indique su router.) También puede conectar un teclado a
la Pi e iniciar sesión en la TV.

## 3. Descargar el proyecto

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. Ejecutar el instalador

```bash
sudo bash scripts/install_pi.sh
```

Tarda varios minutos. Instala los paquetes necesarios, copia el programa a `/opt/archerytimer`, configura el servicio en
segundo plano, activa la capa de pantalla por GPU y hace que la Pi inicie sesión sola en la primera consola y arranque
allí el temporizador. Al terminar, reinicie:

```bash
sudo reboot
```

Tras reiniciar, el temporizador aparece solo en la TV. Use el ratón o el teclado (Espacio = botón grande,
Esc = parada de emergencia).

Opciones: `--no-ui` para una caja solo de luces/sonido sin pantalla, `--user NAME` para elegir el usuario del quiosco.
Ejecute `scripts/install_pi.sh --help` para ver la lista.

## 5. Conectar las luces y la bocina (opcional)

Enchufe la placa ESP32 a un puerto USB de la Pi. Se encuentra automáticamente (el usuario del quiosco ya está en el
grupo `dialout`). El estado se muestra en el menú de hardware del programa. Para flashear una placa nueva, véase la
[guía de flasheo](../flashing.md) (en inglés); el código del firmware está en [`firmware/`](../../firmware/).

## Ajustes

Las opciones de inicio adicionales están en dos archivos pequeños. Edítelos con `sudo nano`:

| Archivo | Se usa para | Ejemplo |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | el núcleo en segundo plano | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | la pantalla | `UI_ARGS="--lang sv --profile audience"` |

Para aplicar los cambios: `sudo systemctl restart archerytimer-core` y reinicie (o cierre sesión en la consola) para la
pantalla. Para usar varias Pi juntas (un líder y seguidores), véase [cluster.md](../cluster.md) (en inglés).

## Actualizar

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

Se conservan sus ajustes y los archivos de `/etc/archerytimer`.

**Desde un ordenador Windows**, sin git en la Pi: `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(copia el proyecto y ejecuta el instalador; añada `-Reboot` para reiniciar después).

## Obtener una consola normal en la TV

El quiosco ocupa la primera consola de la Pi. Para trabajar en la propia Pi, inicie sesión por **SSH** desde otro
ordenador, o cree el archivo `~/.no-kiosk` (`touch ~/.no-kiosk`) y reinicie para obtener un prompt normal. Borre el
archivo y reinicie para recuperar el temporizador.

## Solución de problemas

| Problema | Qué hacer |
| --- | --- |
| Pantalla negra tras reiniciar | Espere 1-2 minutos tras encender. Revise el HDMI. Si persiste, entre por SSH, ejecute `journalctl -u archerytimer-core -n 50` y mire `~/.local/share/archerytimer/logs/ui.log` |
| La pantalla queda negra solo si la TV se enciende después que la Pi | Añada `hdmi_force_hotplug=1` a `/boot/firmware/config.txt` y reinicie |
| La pantalla funciona pero dice «sin conexión con el núcleo» | `systemctl status archerytimer-core`; reinícielo con `sudo systemctl restart archerytimer-core` |
| Sin luces/bocina | Compruebe que el cable USB transmite datos; `ls /dev/ttyACM* /dev/ttyUSB*` debe mostrar un dispositivo |
| Comprobar el entorno | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| Quitar todo | `sudo bash scripts/uninstall_pi.sh` (conserva sus ajustes) |

Registros en vivo: `journalctl -u archerytimer-core -f`. Más detalles internos: [deployment.md](../deployment.md) (en inglés).

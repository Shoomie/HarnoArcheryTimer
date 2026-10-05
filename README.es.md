# Archery Timer (temporizador de tiro con arco)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · **Español** · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [اردو](README.ur.md)

Un reloj de tiro con arco de código abierto. Controla el tiempo de tiro en competiciones y entrenamientos, lo muestra
en un televisor o monitor y maneja semáforos y una bocina por USB. Está pensado para un club pequeño de tiro con arco y
para voluntarios sin conocimientos técnicos: la pantalla tiene un único botón evidente para lo que ocurre a continuación
y una parada de emergencia siempre visible.

- Funciona en **Windows 10/11**, **Linux**, **Raspberry Pi** (2B o superior, como quiosco de TV) y macOS.
- Interfaz en inglés (por defecto) y sueco.
- El temporizador, las luces y el sonido siguen funcionando aunque la pantalla se bloquee.
- Placa ESP32 opcional para luces y bocina, segundas pantallas opcionales y varios dispositivos en una misma red.

> **Antes de una competición oficial:** los tiempos de `config/` son **provisionales**, no reglas confirmadas de World
> Archery / SBF. Compruébelos con el reglamento vigente y edite los archivos TOML (los clubes pueden añadir sus propios
> ajustes preestablecidos sin tocar el código). El sistema se ha probado de principio a fin en un PC con Windows, un PC
> con Linux y una Raspberry Pi 2B con módulos ESP32-C3 y WROOM-32D. Aún sin cubrir: una prueba continua de 4 horas,
> placas ESP32-S3 y pruebas de radio de largo alcance.

## Cómo llevar una sesión

1. Inicie el programa (véase Instalación más abajo). Pulse **Espacio** o el botón grande: se abre la configuración.
2. Elija una tarjeta (por ejemplo *Indoor 18 m*), escoja las líneas y el número de tandas, y empiece.
3. El botón grande siempre dice qué ocurre a continuación: empezar la tanda, siguiente tanda, reanudar. **P** pausa.
   **Esc** es la parada de emergencia: luces rojas y silencio, siempre con una sola pulsación y sin confirmación.

La pantalla muestra una luz grande (con un símbolo, no solo color), la cuenta atrás, la tanda y la línea, y el estado
del hardware en palabras sencillas.

## Instalación

Elija su sistema. Cada guía va paso a paso desde cero hasta un temporizador en marcha.

| Sistema | Guía | Versión corta |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.es.md](docs/install/windows.es.md) | Instale Python, descargue el proyecto, haga doble clic en `scripts\setup_windows.bat` y luego en `scripts\start_windows.bat` |
| **Linux** (y macOS) | [docs/install/linux.es.md](docs/install/linux.es.md) | `scripts/setup_desktop.sh`, luego `scripts/start.sh` |
| **Raspberry Pi** (quiosco de TV) | [docs/install/raspberry-pi.es.md](docs/install/raspberry-pi.es.md) | Grabe Pi OS Lite, `git clone`, `sudo scripts/install_pi.sh`, reinicie |

### Inicio rápido (cualquier ordenador, sin hardware)

1. Instale **Python 3.9 o superior** ([python.org](https://www.python.org/downloads/); en Linux normalmente
   `sudo apt install python3 python3-venv python3-pip`).
2. Descargue el proyecto: en GitHub pulse **Code → Download ZIP** y descomprímalo, o
   `git clone <repository-url>`.
3. En la carpeta del proyecto ejecute una vez el script de instalación y después el de inicio:

   | | Instalación (una vez) | Inicio |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` significa «sin hardware de luces conectado». Quítelo cuando haya una placa ESP32 enchufada; el
   programa la encuentra solo.

### Controles

| Tecla | Acción |
| --- | --- |
| **Espacio** / Intro | El botón grande: lo que toque a continuación (abrir la configuración, empezar la tanda, ...) |
| **P** | Pausar / reanudar |
| **Esc** | **Parada de emergencia**: luces rojas y silencio, siempre con una sola pulsación |
| S | Detener la tanda |
| N / Retroceso | Siguiente fase / atrás (durante 5 segundos tras Detener o Siguiente, Atrás aparece como *Deshacer*) |
| M / F1 | Menú: nueva sesión, temporizadores, ajustes, estado del hardware, red, sonido, salir |

Todo funciona también con el ratón. Los mandos de presentaciones y los pedales que actúan como teclado también sirven,
igual que los botones de los módulos ESP32. Lista completa: [docs/ui.md](docs/ui.md) (en inglés).

### Opciones de inicio útiles

Añádalas después del script de inicio; las opciones de pantalla van después de `--`:

```text
scripts/start.sh --no-serial                      demostración sin hardware
scripts/start.sh --serial-port COM7               elegir usted el puerto USB (Linux: /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        pantalla completa, interfaz en sueco
scripts/start.sh -- --profile audience --display 1   pantalla para el público en el segundo monitor, sin controles
```

En Windows use `scripts\start_windows.bat` en lugar de `scripts/start.sh`.

## Luces, bocina y más dispositivos

La documentación técnica está en inglés. Las guías de instalación existen en 11 idiomas.

| Quiero... | Leer |
| --- | --- |
| Conectar semáforos y una bocina (placa ESP32, cableado, pines) | [docs/firmware.md](docs/firmware.md) |
| Flashear un módulo ESP32 (Windows, Linux, macOS; no hace falta compilador) | [docs/flashing.md](docs/flashing.md): `scripts\flash.bat` o `sh scripts/flash.sh` |
| Configurar la bocina y los altavoces, prueba de sonido | [docs/audio.md](docs/audio.md) |
| Usar varias pantallas, PC o Pi como un solo temporizador (LAN o radio) | [docs/cluster.md](docs/cluster.md) |
| Cajas de luces inalámbricas y botones remotos | [docs/mesh.md](docs/mesh.md) |

## Documentación

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | Índice de toda la documentación |
| [docs/install/](docs/install/) | Guías de instalación (11 idiomas) |
| [docs/ui.md](docs/ui.md) | Pantallas, teclas, perfiles de pantalla |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | Protocolo serie USB; protocolo del núcleo a la pantalla |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Detalles internos de Raspberry Pi; mediciones de tiempo y de dibujo |
| [structure.md](structure.md) | Dónde está cada cosa en el código fuente |

## Estructura del repositorio

```text
src/archerytimer/   el programa (servicio núcleo, cliente de interfaz, hardware, audio, IPC)
config/             secuencias de tiempos y ajustes preestablecidos (TOML, provisionales)
locales/            todos los textos de la interfaz, en.toml y sv.toml
assets/             tipografía (Inter, OFL)
firmware/           firmware ESP32 (PlatformIO), imágenes precompiladas, vectores de prueba compartidos
scripts/            scripts de instalación/inicio, instalador para Raspberry Pi, menú de flasheo, pruebas de rendimiento
docs/               documentación
tests/  tools/      batería de pruebas, simulador de malla
```

## Desarrollo

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # pruebas (algunas se omiten en Windows)
ruff check . && ruff format --check .
mypy
```

Para traducir la documentación o la interfaz, véase [CONTRIBUTING.md](CONTRIBUTING.md). Reglas y arquitectura del
proyecto: [CLAUDE.md](CLAUDE.md). Mediciones: [docs/benchmarks.md](docs/benchmarks.md).

## Licencia

MIT (véase [LICENSE](LICENSE)): libre para usar, copiar, modificar, compartir y vender, con cualquier fin y en cualquier
lugar. Las contribuciones son bienvenidas bajo la misma licencia. Las partes de terceros conservan sus propias licencias
abiertas, indicadas en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (por ejemplo la tipografía Inter,
`assets/fonts/OFL.txt`).

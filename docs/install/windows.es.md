# Instalar en Windows 10/11

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · [हिन्दी](windows.hi.md) · **Español** · [Français](windows.fr.md) · [العربية](windows.ar.md) · [বাংলা](windows.bn.md) · [Português](windows.pt.md) · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.es.md) · [Raspberry Pi](raspberry-pi.es.md) · [Volver al README](../../README.es.md)

Tiempo necesario: unos 10 minutos. Solo necesita conexión a internet para la primera instalación.

## 1. Instalar Python

1. Vaya a <https://www.python.org/downloads/> y descargue la última versión de Python 3 (3.9 o superior).
2. Ejecute el instalador. **Marque «Add python.exe to PATH»** en la primera pantalla y pulse *Install Now*.

## 2. Descargar el proyecto

Elija una opción:

- **ZIP (la más fácil):** en la página de GitHub pulse **Code → Download ZIP**, luego haga clic derecho en el archivo y
  elija *Extraer todo*. Ponga la carpeta en un lugar sencillo, por ejemplo `C:\ArcheryTimer`.
- **Git:** `git clone <repository-url> C:\ArcheryTimer`

## 3. Instalación (una sola vez)

Abra la carpeta del proyecto y **haga doble clic en `scripts\setup_windows.bat`**. Crea un entorno de Python privado en
`.venv` e instala lo que necesita el temporizador. Espere hasta que aparezca «Done».

Si Windows SmartScreen muestra una advertencia sobre el archivo, elija *Más información → Ejecutar de todas formas* (es
un script de texto sencillo que puede leer con el Bloc de notas).

## 4. Iniciar el temporizador

Haga doble clic en **`scripts\start_windows.bat`**. Se abre una ventana con el temporizador.

- ¿Todavía sin hardware de luces? Inícielo desde una terminal como `scripts\start_windows.bat --no-serial` para una demostración.
- Pantalla completa en un televisor: `scripts\start_windows.bat -- --fullscreen`
- Interfaz en sueco: `scripts\start_windows.bat -- --lang sv` (el idioma también se cambia en el menú de ajustes)
- Segundo monitor para el público, sin controles: `scripts\start_windows.bat -- --profile audience --display 1`

(Para crear un acceso directo en el escritorio: clic derecho en `start_windows.bat` → *Enviar a → Escritorio (crear acceso directo)*.)

Teclas: **Espacio** = el botón grande, **P** = pausa, **Esc** = parada de emergencia. Véase el
[README](../../README.es.md).

## 5. Conectar las luces y la bocina (opcional)

Enchufe la placa ESP32 a un puerto USB. El programa la encuentra solo. Si no lo hace:

1. Abra *Administrador de dispositivos → Puertos (COM y LPT)* y anote el puerto, por ejemplo `COM7`.
2. Inicie con `scripts\start_windows.bat --serial-port COM7`.

Algunas placas baratas necesitan un controlador USB-serie (CH340 o CP210x); si no aparece ningún puerto COM, instale el
controlador del fabricante del chip. El firmware de la placa está en [`firmware/`](../../firmware/); para flashear una
placa nueva use la [guía de flasheo](../flashing.md) (en inglés).

## Actualizar

Descargue el nuevo ZIP (o `git pull`) y ejecute de nuevo `scripts\setup_windows.bat`. Sus ajustes se guardan en su perfil
de usuario (`%LOCALAPPDATA%\archerytimer`), no en la carpeta del proyecto.

## Solución de problemas

| Problema | Qué hacer |
| --- | --- |
| «Python was not found» | Reinstale Python y marque *Add python.exe to PATH*, o repita la instalación tras reiniciar el PC |
| La ventana se abre y se cierra | Ejecute `scripts\start_windows.bat` desde una terminal (`cmd`) para ver el mensaje de error |
| El estado del hardware dice «sin luces» | Compruebe el cable USB (debe transmitir datos), el puerto y el controlador; véase el paso 5 |
| Registros | `%LOCALAPPDATA%\archerytimer\logs` (péguelo como ruta en el Explorador de archivos) |

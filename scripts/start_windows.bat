@echo off
rem Starts the timer (core + display) on Windows. Extra options are passed on, for example:
rem   scripts\start_windows.bat --no-serial          (no lights hardware, demo)
rem   scripts\start_windows.bat -- --fullscreen --lang en
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Run scripts\setup_windows.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m archerytimer.launcher %*

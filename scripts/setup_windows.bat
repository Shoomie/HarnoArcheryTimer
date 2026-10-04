@echo off
rem One-time setup on Windows: creates .venv in the project folder and installs the app.
rem Double-click this file, or run it from a terminal. Needs Python 3.9+ from python.org
rem (tick "Add python.exe to PATH" in the installer).
cd /d "%~dp0.."
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || (
    echo Python was not found. Install it from https://www.python.org/downloads/ and run this again.
    pause
    exit /b 1
)
%PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -e . || goto :fail
echo.
echo Done. Start the timer with scripts\start_windows.bat
pause
exit /b 0
:fail
echo.
echo Setup failed, see the messages above.
pause
exit /b 1

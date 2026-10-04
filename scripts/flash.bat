@echo off
rem Flashing menu: finds a Python 3 and runs scripts\flash.py (arguments are passed on).
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0flash.py" %*
) else (
    python "%~dp0flash.py" %*
)
if not "%~1"=="" exit /b %errorlevel%
pause

@echo off
rem Builds and runs the native hostcore tests (serial frame logic, both vector files) with MSVC Build Tools.
rem Usage: run_hostcore_tests.bat   (from any directory)
setlocal
set HERE=%~dp0
set FW=%HERE%..\..
set HCSRC=%FW%\lib\hostcore\src
set OUT=%TEMP%\hostcore_native
if not exist "%OUT%" mkdir "%OUT%"
set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
where cl >nul 2>nul || call %VCVARS% >nul
cl /nologo /std:c++17 /EHsc /W4 /I"%HCSRC%" /Fo"%OUT%\\" /Fe"%OUT%\test_hostcore.exe" "%HERE%test_hostcore.cpp" "%HCSRC%\hostcore.cpp" || exit /b 1
"%OUT%\test_hostcore.exe" "%FW%"
exit /b %ERRORLEVEL%

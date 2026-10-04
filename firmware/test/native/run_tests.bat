@echo off
rem Builds and runs the native meshcore tests with MSVC Build Tools (no PlatformIO needed).
rem Usage: run_tests.bat   (from any directory)
setlocal
set HERE=%~dp0
set FW=%HERE%..\..
set MCSRC=%FW%\lib\meshcore\src
set OUT=%TEMP%\meshcore_native
if not exist "%OUT%" mkdir "%OUT%"
set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
where cl >nul 2>nul || call %VCVARS% >nul
cl /nologo /std:c++17 /EHsc /W4 /I"%MCSRC%" /Fo"%OUT%\\" /Fe"%OUT%\test_mesh.exe" "%HERE%test_mesh.cpp" "%MCSRC%\mesh_crypto.cpp" "%MCSRC%\mesh_frame.cpp" "%MCSRC%\mesh_peers.cpp" "%MCSRC%\mesh_arbiter.cpp" "%MCSRC%\mesh_cmd.cpp" "%MCSRC%\mesh_pair.cpp" "%MCSRC%\mesh_x25519.cpp" || exit /b 1
"%OUT%\test_mesh.exe" "%FW%"
exit /b %ERRORLEVEL%

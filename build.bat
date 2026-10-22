@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo             KPS Overlay Build Suite
echo ===================================================
echo.
echo  [1] Build Server (kps_server.exe for OBS)
echo  [2] Build Overlay (kps_overlay.exe for Desktop)
echo  [3] Build Both (Server + Desktop Overlay)
echo.

set /p choice="Enter choice [1/2/3]: "

if "%choice%"=="1" goto build_server
if "%choice%"=="2" goto build_overlay
if "%choice%"=="3" goto build_both
echo Invalid choice.
pause
exit /b 1

:build_server
call build_server.bat
exit /b

:build_overlay
call build_overlay.bat
exit /b

:build_both
echo.
echo === [Step 1/2] Building kps_server.exe ===
call build_server.bat
echo.
echo === [Step 2/2] Building kps_overlay.exe ===
call build_overlay.bat
exit /b

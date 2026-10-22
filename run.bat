@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo               KPS Overlay Launcher
echo ===================================================
echo.
echo  [1] Launch Server (for OBS / Web)
echo  [2] Launch Desktop Overlay (GUI Window)
echo.

set /p choice="Enter choice [1/2]: "

if "%choice%"=="1" (
    python kps_server.py
) else if "%choice%"=="2" (
    python kps_overlay.py
) else (
    echo Invalid choice.
    pause
)

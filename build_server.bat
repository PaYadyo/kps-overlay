@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo  Building kps_server.exe (OBS & WebSocket Server)
echo ===================================================

taskkill /F /IM kps_server.exe 2>nul
timeout /t 1 /nobreak >nul

echo [1/3] Checking dependencies...
python -m pip install -r requirements.txt --quiet

echo [2/3] Compiling with PyInstaller...
python -m PyInstaller --onefile --console --name "kps_server" kps_server.py

if exist "dist\kps_server.exe" (
    echo [3/3] Copying runtime files to dist\...
    if not exist "dist\config.ini" copy /Y "config.ini" "dist\config.ini" >nul
    copy /Y "overlay.html" "dist\overlay.html" >nul
    echo.
    echo ===================================================
    echo  SUCCESS: dist\kps_server.exe is ready!
    echo ===================================================
) else (
    echo.
    echo [ERROR] Build failed. Check the error log above.
)

pause

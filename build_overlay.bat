@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo  Building kps_overlay.exe (Desktop GUI Overlay)
echo ===================================================

taskkill /F /IM kps_overlay.exe 2>nul
timeout /t 1 /nobreak >nul

echo [1/3] Checking dependencies...
python -m pip install -r requirements.txt --quiet

echo [2/3] Compiling with PyInstaller...
python -m PyInstaller --onefile --noconsole --name "kps_overlay" kps_overlay.py

if exist "dist\kps_overlay.exe" (
    echo [3/3] Copying runtime files to dist\...
    if not exist "dist\kps_overlay.ini" copy /Y "kps_overlay.ini" "dist\kps_overlay.ini" >nul
    echo.
    echo ===================================================
    echo  SUCCESS: dist\kps_overlay.exe is ready!
    echo ===================================================
) else (
    echo.
    echo [ERROR] Build failed. Check the error log above.
)

pause

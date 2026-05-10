@echo off
echo Installing dependencies...
pip install pynput pyinstaller

echo.
echo Building kps_overlay.exe...
pyinstaller --onefile --noconsole --name "kps_overlay" kps_overlay.py

echo.
echo Done! Your .exe is in the dist\ folder.
pause
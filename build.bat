@echo off
echo Installing dependencies...
pip install pynput websockets pyinstaller

echo.
echo Building kps_server.exe...
pyinstaller --onefile --console --hidden-import=pynput.keyboard._win32 --hidden-import=pynput.mouse._win32 --hidden-import=pynput.keyboard._base --name "kps_server" kps_server.py

echo.
echo Copying config.ini to dist\...
copy /Y config.ini dist\config.ini

echo.
echo =============================================
echo  DONE! Files are in the dist\ folder.
echo =============================================
echo.
echo HOW TO USE:
echo   1. Run tosu.exe first
echo   2. Run dist\kps_server.exe
echo   3. OBS Browser Source: http://localhost:24050/kps-overlay/
echo      Size: 160 x 200 px
echo.
pause

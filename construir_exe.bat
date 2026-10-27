@echo off
rem Crea los ejecutables (no hace falta tener Python para usarlos) en la carpeta dist\
cd /d "%~dp0"
call _preparar.bat || exit /b 1
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6,<7" || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --name telegram-looker-panel --add-data "tgdl\estatico;tgdl\estatico" panel.py || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --name telegram-looker-consola descargar_canal.py || exit /b 1
echo.
echo Listo: dist\telegram-looker-panel.exe y dist\telegram-looker-consola.exe
echo Copialos a una carpeta junto a tu .env (las sesiones y descargas se guardan al lado del .exe).
pause

@echo off
rem Prepara el entorno virtual e instala/actualiza dependencias si faltan.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv || exit /b 1
)
".venv\Scripts\python.exe" -c "import telethon, tqdm, aiohttp" 2>nul
if errorlevel 1 (
    echo Instalando dependencias...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1
)
exit /b 0

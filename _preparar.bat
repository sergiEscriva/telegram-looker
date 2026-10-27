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
rem cryptg es opcional: si no se puede instalar se sigue sin el (y no se reintenta en cada arranque).
if not exist ".venv\sin_cryptg" (
    ".venv\Scripts\python.exe" -c "import cryptg" 2>nul || (
        ".venv\Scripts\python.exe" -m pip install cryptg >nul 2>&1 || (
            echo Aviso: no se pudo instalar cryptg ^(opcional^), las descargas iran algo mas lentas.
            type nul > ".venv\sin_cryptg"
        )
    )
)
exit /b 0

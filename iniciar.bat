@echo off
chcp 65001 >nul
cd /d "%~dp0"
call _preparar.bat || goto :error

".venv\Scripts\python.exe" descargar_canal.py %*
pause
exit /b 0

:error
echo.
echo Ha ocurrido un error instalando las dependencias.
pause
exit /b 1

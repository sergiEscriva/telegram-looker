@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TG Downloader - Panel
call _preparar.bat || goto :error

".venv\Scripts\python.exe" panel.py
pause
exit /b 0

:error
echo.
echo Ha ocurrido un error instalando las dependencias.
pause
exit /b 1

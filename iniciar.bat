@echo off
title GORVAX GAME FACTORY
echo.
echo  ====================================================
echo       GORVAX GAME FACTORY - Iniciando...
echo  ====================================================
echo.
cd /d "%~dp0"
call venv\Scripts\activate.bat
start "GORVAX-FACTORY" python start.py
echo  Servicos iniciados! Pode fechar esta janela.
echo.
pause

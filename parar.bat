@echo off
title GORVAX GAME FACTORY - Encerrando
echo.
echo  ====================================================
echo       GORVAX GAME FACTORY - Encerrando tudo...
echo  ====================================================
echo.

echo  [PY] Encerrando Backend (porta 8000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM uvicorn.exe >nul 2>&1

echo  [PY] Encerrando processos Python do backend...
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%backend.main%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo  [UI] Encerrando Dashboard (porta 3000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo  [GM] Encerrando Game (porta 5174)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5174" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo  [**] Encerrando processos Node restantes do projeto...
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%ai-game-factory%%' and name='node.exe'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo  [**] Encerrando processo start.py...
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%start.py%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo  ====================================================
echo       Tudo encerrado! Ate mais.
echo  ====================================================
echo.
pause

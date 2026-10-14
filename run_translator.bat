@echo off
title LEZGi AI Server
echo ===================================================
echo   LEZGi AI - Local Assistant & Translation Server
echo ===================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python translate.py --server
pause

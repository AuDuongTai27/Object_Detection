@echo off
chcp 65001 >nul
title FabLab AI - Dobot Studio Launcher
cd /d "%~dp0"

echo ======================================================================
echo   [+] FABLAB AI - DOBOT ALL-IN-ONE WEB STUDIO
echo ======================================================================
echo.
echo   [*] Dang khoi chay may chu va tu dong mo trinh duyet...
echo.

python DOBOT\dobot_live_server.py

if %errorlevel% neq 0 (
    echo.
    echo [-] Co loi xay ra khi chay may chu!
)

pause

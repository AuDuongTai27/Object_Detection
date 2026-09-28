@echo off
chcp 65001 > nul
title FabLab AI Vision & Dobot Web Studio
echo ======================================================================
echo   🚀 DANG KHOI DONG FABLAB AI & DOBOT ALL-IN-ONE WEB STUDIO
echo ======================================================================
echo.
echo   [1] Ban Sao So 3D (Digital Twin): Dieu khien, mo phong 3D Three.js
echo   [2] Thu Thap Du Lieu (Data Studio): Chup anh & phan nhan truc tiep
echo   [3] Huan Luyen AI (AI Trainer): Train YOLO 1-Click / Xuat Colab Zip
echo   [4] Tu Dong Phan Loai (Auto Sort): YOLO AI Vision + Click-to-Pick
echo.
echo ======================================================================
echo   [*] May chu dang khoi chay tai: http://localhost:8080
echo   [*] Dang mo trinh duyet tu dong...
echo ======================================================================
echo.

start "" "http://localhost:8080"
python DOBOT\dobot_live_server.py

pause

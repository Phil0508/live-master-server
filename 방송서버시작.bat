@echo off
chcp 65001 >nul
title 방송 마스터 V40 서버
color 0A
echo =======================================
echo.
echo     🚀 방송 마스터 서버를 시작합니다 🚀
echo.
echo =======================================
echo.
set HEADLESS=1
python server.py
pause

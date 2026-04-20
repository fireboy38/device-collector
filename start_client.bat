@echo off
chcp 65001 >nul
title 设备信息采集器 - 客户端
echo ============================================
echo   设备信息采集器 - 启动客户端
echo ============================================
echo.
cd /d "%~dp0client"
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe client.py
pause

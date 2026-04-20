@echo off
chcp 65001 >nul
title 设备信息采集器 - 服务端
echo ============================================
echo   设备信息采集器 - 启动服务端
echo ============================================
echo.

REM 检查 Flask 是否安装
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe -c "import flask" 2>nul
if errorlevel 1 (
    echo 正在安装 Flask ...
    C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\pip.exe install flask
)

cd /d "%~dp0server"
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe app.py
pause

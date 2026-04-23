#!/bin/bash
# 设备信息采集器 - 双端口启动脚本
# 管理端口(5000): Web管理界面、用户/项目管理、客户端生成
# 数据端口(5001): 设备数据提交/查询，面向客户端和外部系统

ADMIN_PORT=${ADMIN_PORT:-5000}
DATA_PORT=${DATA_PORT:-5001}

echo "=================================================="
echo "  设备信息采集器 - 启动中"
echo "  管理端口: ${ADMIN_PORT} (Web管理界面)"
echo "  数据端口: ${DATA_PORT} (设备数据API)"
echo "=================================================="

# 启动数据端口（后台）
cd /app/server
gunicorn \
    --bind "0.0.0.0:${DATA_PORT}" \
    --workers 1 \
    --threads 4 \
    --chdir /app/server \
    --daemon \
    --access-logfile /proc/1/fd/1 \
    --error-logfile /proc/1/fd/2 \
    data_app:app

echo "[OK] 数据端口已启动: 0.0.0.0:${DATA_PORT}"

# 启动管理端口（前台，作为主进程）
echo "[OK] 启动管理端口: 0.0.0.0:${ADMIN_PORT}"
exec gunicorn \
    --bind "0.0.0.0:${ADMIN_PORT}" \
    --workers 2 \
    --threads 4 \
    --chdir /app/server \
    app:app

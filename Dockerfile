FROM python:3.12-slim

LABEL maintainer="fireboy38"
LABEL description="Device Collector Server - 设备信息采集器服务端"
LABEL version="2.0.0"

WORKDIR /app

# 安装服务端依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制服务端代码
COPY server/ ./server/

# 复制客户端代码和预编译 EXE
COPY client/ ./client/

# 复制启动脚本
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# 创建数据目录
RUN mkdir -p /app/server/data

# 暴露端口：管理端口 + 数据端口
EXPOSE 5000 5001

# 环境变量
ENV FLASK_APP=server/app.py
ENV PYTHONUNBUFFERED=1
ENV ADMIN_PORT=5000
ENV DATA_PORT=5001

# 启动双端口服务
CMD ["./start.sh"]

FROM python:3.12-slim

LABEL maintainer="fireboy38"
LABEL description="Device Collector Server - 设备信息采集器服务端"
LABEL version="1.0.0"

WORKDIR /app

# 安装服务端依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制服务端代码
COPY server/ ./server/

# 复制客户端代码和预编译 EXE
COPY client/ ./client/

# 创建数据目录
RUN mkdir -p /app/server/data

# 暴露端口
EXPOSE 5000

# 环境变量
ENV FLASK_APP=server/app.py
ENV PYTHONUNBUFFERED=1

# 启动
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--chdir", "server", "app:app"]

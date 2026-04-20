# ============================================================
# 多阶段构建: Wine 打包客户端 EXE + 运行服务端
# ============================================================

# ---- 阶段1: 用 Wine + Windows Python 打包客户端 EXE ----
FROM python:3.12-slim AS builder

# 安装 Wine 和依赖
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        wine64 wine32 wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 设置 Wine 环境
ENV WINEPREFIX=/root/.wine
ENV WINEDEBUG=-all
RUN wineboot --init 2>/dev/null || true

# 下载并安装 Windows Python (embedded)
RUN mkdir -p /tmp/python-win && \
    wget -q "https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip" -O /tmp/python-win/python.zip && \
    cd /tmp/python-win && unzip python.zip && rm python.zip

# 下载 pip
RUN cd /tmp/python-win && \
    wget -q "https://bootstrap.pypa.io/get-pip.py" -O get-pip.py

# 用 Wine 安装 pip 和 PyInstaller + pycryptodome
RUN cd /tmp/python-win && \
    wine python.exe get-pip.py 2>/dev/null && \
    wine python.exe -m pip install pyinstaller pycryptodome 2>/dev/null

# 复制客户端源码并打包 EXE
COPY client/ /tmp/client-src/
RUN mkdir -p /tmp/client-build && \
    cd /tmp/client-build && \
    cp /tmp/client-src/client.py . && \
    wine python.exe -m PyInstaller \
        --onefile \
        --windowed \
        --noconfirm \
        --clean \
        --name DeviceCollector \
        --hidden-import Crypto.Cipher.AES \
        --hidden-import Crypto.Util.Padding \
        --hidden-import Crypto.Cipher \
        --hidden-import Crypto.Util \
        client.py 2>/dev/null && \
    ls -la dist/

# ---- 阶段2: 运行服务端 ----
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
COPY client/ ./client/

# 从 builder 阶段复制预编译的客户端 EXE
COPY --from=builder /tmp/client-build/dist/DeviceCollector.exe ./client/prebuilt/DeviceCollector.exe

# 创建数据目录
RUN mkdir -p /app/server/data

# 暴露端口
EXPOSE 5000

# 环境变量
ENV FLASK_APP=server/app.py
ENV PYTHONUNBUFFERED=1

# 启动
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--chdir", "server", "app:app"]

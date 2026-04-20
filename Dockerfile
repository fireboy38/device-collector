FROM python:3.12-slim

LABEL maintainer="fireboy38"
LABEL description="Device Collector Server - 设备信息采集器服务端"
LABEL version="1.0.0"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server/ ./server/
COPY client/ ./client/

# Create data directory
RUN mkdir -p /app/server/data

# Expose port
EXPOSE 5000

# Environment variables
ENV FLASK_APP=server/app.py
ENV PYTHONUNBUFFERED=1

# Run with gunicorn in production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--chdir", "server", "app:app"]

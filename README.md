# 🖥️ 设备信息采集器

C/S 架构的电脑设备信息采集系统，用于统一收集和管理组织内终端电脑的硬件与网络配置信息。

## 📋 功能特性

### 服务端 (Server)
- 📊 **数据概览** — 实时统计设备数量、今日采集数、各单位分布
- 💻 **设备列表** — 按单位筛选、关键词搜索、查看详细配置
- 🏢 **单位管理** — 增删单位信息，支持编码和描述
- 🔌 **RESTful API** — 供客户端调用提交数据

### 客户端 (Client)
- 🔗 **连接服务端** — 输入服务器地址，自动获取单位列表
- 👤 **人员信息录入** — 使用人姓名、电话、职位
- 🔄 **自动采集** — 一键采集以下设备信息：
  - 电脑名称
  - IP 地址 / MAC 地址
  - 是否自动获取IP (DHCP)
  - 子网掩码 / 默认网关 / DNS 服务器
  - 网卡型号
  - 操作系统
  - CPU / 内存 / 硬盘
  - 主板 / 显卡
- 📤 **一键提交** — 将信息提交到服务端

## 📁 项目结构

```
device-collector/
├── server/
│   ├── app.py              # Flask 服务端
│   ├── templates/
│   │   └── index.html      # Web 管理界面
│   └── data/               # SQLite 数据库（自动生成）
├── client/
│   └── client.py           # Tkinter 客户端
├── start_server.bat        # Windows 启动服务端
├── start_client.bat        # Windows 启动客户端
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install flask
```

> 客户端使用 Python 内置的 tkinter 和标准库，无需额外安装。

### 2. 启动服务端

```bash
cd server
python app.py
```

服务端启动后访问 http://localhost:5000 即可打开管理界面。

### 3. 启动客户端

```bash
cd client
python client.py
```

或者在 Windows 上直接双击 `start_server.bat` / `start_client.bat`。

## 🔧 使用流程

1. **启动服务端** → 浏览器打开管理页面，查看/管理单位信息
2. **启动客户端** → 输入服务器地址，点击"连接并获取单位"
3. **选择单位** → 从下拉列表选择所属单位
4. **填写信息** → 输入使用人姓名、电话、职位
5. **确认采集** → 自动采集的设备信息会显示在界面上
6. **提交** → 点击"提交到服务器"，数据保存到服务端数据库

## 🔌 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/departments` | 获取单位列表 |
| POST | `/api/departments` | 添加单位 |
| DELETE | `/api/departments/<id>` | 删除单位 |
| GET | `/api/devices` | 获取设备列表（支持 `department_id`、`keyword` 参数） |
| POST | `/api/devices` | 提交设备信息 |
| DELETE | `/api/devices/<id>` | 删除设备记录 |
| GET | `/api/stats` | 获取统计信息 |

## ⚙️ 技术栈

- **服务端**: Python 3 + Flask + SQLite
- **客户端**: Python 3 + Tkinter
- **前端**: HTML + CSS + Vanilla JS

## 📝 注意事项

- 客户端目前仅支持 Windows 系统的完整信息采集（网络信息使用 `ipconfig /all`）
- 服务端默认监听 `0.0.0.0:5000`，局域网内客户端可通过服务器IP访问
- 首次启动服务端会自动创建数据库并插入示例单位数据
- 如果需要修改端口，请同步修改 `server/app.py` 和客户端的服务器地址

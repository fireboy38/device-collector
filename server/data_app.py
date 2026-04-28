"""
设备信息采集器 - 数据端口（独立服务）
仅提供设备数据上传/查询 API，与管理端口分离
运行在独立端口（默认 5001），供客户端直接提交数据

与管理端口的区别：
  - 管理端口(5000)：Web管理界面、用户/项目管理、客户端生成等
  - 数据端口(5001)：仅设备数据提交/查询，面向客户端和外部系统集成

共用同一个 SQLite 数据库
"""
import os
import sys
import csv
import io
import sqlite3
import hashlib
import secrets
import datetime
import base64

from functools import wraps
from flask import Flask, request, jsonify, g, send_file

# AES 加密（用于客户端密码密文）
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# AES-128 密钥（与管理端一致）
_AES_KEY = b'DC2026SK16BYTKEY'

app = Flask(__name__)
app.secret_key = 'device-collector-data-2026-secure'

# 共用数据库路径（与管理端同一数据库）
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'devices.db')
SECRET_KEY = 'device-collector-2026'


def get_db():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password):
    """密码哈希"""
    return hashlib.sha256((password + SECRET_KEY).encode()).hexdigest()


def generate_api_key():
    """生成 API Key"""
    return 'dc_' + secrets.token_hex(32)


def api_response(data=None, message='success', code=200):
    """统一 API 响应格式"""
    resp = {
        'code': code,
        'message': message,
        'data': data,
        'timestamp': datetime.datetime.now().isoformat()
    }
    return jsonify(resp), code


def add_log(log_type, content, detail=None, operator=None, ip_address=None):
    """写入操作日志"""
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO logs (log_type, content, detail, operator, ip_address) VALUES (?, ?, ?, ?, ?)',
            (log_type, content, detail, operator, ip_address)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"写入日志失败: {e}")


# ==================== API Key 认证 ====================

def validate_api_key(api_key_str):
    """验证 API Key 是否有效"""
    if not api_key_str:
        return False, None
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM api_keys WHERE api_key = ? AND is_active = 1',
        (api_key_str,)
    ).fetchone()
    if not row:
        conn.close()
        return False, None
    key_info = dict(row)
    if key_info.get('expires_at'):
        try:
            expires = datetime.datetime.fromisoformat(key_info['expires_at'])
            if expires < datetime.datetime.now():
                conn.close()
                return False, None
        except (ValueError, TypeError):
            pass
    conn.execute(
        'UPDATE api_keys SET last_used_at = ? WHERE id = ?',
        (datetime.datetime.now().isoformat(), key_info['id'])
    )
    conn.commit()
    conn.close()
    return True, key_info


def require_api_key(permissions='read'):
    """API Key 认证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key_str = request.headers.get('X-API-Key') or request.args.get('api_key')
            if not api_key_str:
                return api_response(message='缺少 API Key，请在请求头 X-API-Key 或参数 api_key 中传入', code=401)
            is_valid, key_info = validate_api_key(api_key_str)
            if not is_valid:
                return api_response(message='API Key 无效或已过期', code=401)
            key_perms = (key_info.get('permissions') or '').split(',')
            if permissions == 'write' and 'write' not in key_perms:
                return api_response(message='API Key 权限不足，需要 write 权限', code=403)
            g.api_key_info = key_info
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ==================== 首页 & 健康检查 ====================

@app.route('/')
def index():
    """数据端口首页 - 展示服务器信息和API列表"""
    import socket
    try:
        hostname = socket.gethostname()
        # 获取所有本机IP
        local_ips = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            local_ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
        try:
            for info in socket.getaddrinfo(hostname, None):
                ip = info[4][0]
                if ip not in local_ips and not ip.startswith('127.') and ':' not in ip:
                    local_ips.append(ip)
        except Exception:
            pass

        conn = get_db()
        device_count = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
        project_count = conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        dept_count = conn.execute('SELECT COUNT(*) FROM departments').fetchone()[0]
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        conn.close()

        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>设备采集器 - 数据端口</title>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; background:#f0f2f5; color:#333; padding:40px 20px; }}
    .container {{ max-width:700px; margin:0 auto; }}
    h1 {{ font-size:24px; margin-bottom:6px; color:#1a73e8; }}
    .subtitle {{ color:#666; font-size:14px; margin-bottom:24px; }}
    .card {{ background:#fff; border-radius:12px; padding:20px 24px; margin-bottom:16px; box-shadow:0 2px 8px rgba(0,0,0,0.08); }}
    .card h2 {{ font-size:16px; color:#1a73e8; margin-bottom:12px; border-bottom:1px solid #e8e8e8; padding-bottom:8px; }}
    .info-row {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #f5f5f5; }}
    .info-row:last-child {{ border-bottom:none; }}
    .info-label {{ color:#666; font-size:14px; }}
    .info-value {{ font-weight:600; font-size:14px; font-family:Consolas,monospace; }}
    .ip-highlight {{ color:#1a73e8; font-size:16px; font-weight:700; }}
    .api-list {{ list-style:none; }}
    .api-list li {{ padding:8px 0; border-bottom:1px solid #f5f5f5; display:flex; gap:10px; align-items:center; }}
    .api-list li:last-child {{ border-bottom:none; }}
    .method {{ background:#1a73e8; color:#fff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:600; min-width:40px; text-align:center; }}
    .method.post {{ background:#34a853; }}
    .path {{ font-family:Consolas,monospace; font-size:13px; color:#333; }}
    .desc {{ color:#888; font-size:12px; }}
    .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:8px; }}
    .stat {{ text-align:center; }}
    .stat .num {{ font-size:28px; font-weight:700; color:#1a73e8; }}
    .stat .label {{ font-size:12px; color:#888; margin-top:2px; }}
</style>
</head>
<body>
<div class="container">
    <h1>📡 设备信息采集器 - 数据端口</h1>
    <p class="subtitle">Data Port (:{DATA_PORT}) · 供客户端提交设备数据</p>

    <div class="card">
        <h2>🌐 服务器地址</h2>
        <div class="info-row">
            <span class="info-label">主机名</span>
            <span class="info-value">{hostname}</span>
        </div>
        <div class="info-row">
            <span class="info-label">数据端口地址</span>
            <span class="info-value ip-highlight">{local_ips[0] if local_ips else "127.0.0.1"}:{DATA_PORT}</span>
        </div>
        {''.join(f'<div class="info-row"><span class="info-label">其他IP</span><span class="info-value">{ip}</span></div>' for ip in local_ips[1:])}
        <div class="info-row">
            <span class="info-label">管理端口</span>
            <span class="info-value">{local_ips[0] if local_ips else "127.0.0.1"}:5000</span>
        </div>
        <div style="margin-top:12px; padding:10px; background:#e8f5e9; border-radius:8px; font-size:13px; color:#2e7d32;">
            💡 客户端 CONFIG.INI 中 ServerUrl 请填写: <strong>http://{local_ips[0] if local_ips else "127.0.0.1"}:{DATA_PORT}</strong>
        </div>
    </div>

    <div class="card">
        <h2>📊 数据统计</h2>
        <div class="stats">
            <div class="stat"><div class="num">{project_count}</div><div class="label">项目</div></div>
            <div class="stat"><div class="num">{dept_count}</div><div class="label">单位</div></div>
            <div class="stat"><div class="num">{user_count}</div><div class="label">用户</div></div>
            <div class="stat"><div class="num">{device_count}</div><div class="label">设备</div></div>
        </div>
    </div>

    <div class="card">
        <h2>📋 API 接口</h2>
        <ul class="api-list">
            <li><span class="method post">POST</span><span class="path">/api/login</span><span class="desc">客户端登录</span></li>
            <li><span class="method post">POST</span><span class="path">/api/data/login</span><span class="desc">数据端口登录</span></li>
            <li><span class="method post">POST</span><span class="path">/api/devices</span><span class="desc">提交设备信息</span></li>
            <li><span class="method get">GET</span><span class="path">/api/departments</span><span class="desc">获取单位列表</span></li>
            <li><span class="method get">GET</span><span class="path">/api/data/health</span><span class="desc">健康检查</span></li>
            <li><span class="method get">GET</span><span class="path">/api/v1/devices</span><span class="desc">查询设备(API Key)</span></li>
            <li><span class="method get">GET</span><span class="path">/api/v1/projects</span><span class="desc">项目列表(API Key)</span></li>
            <li><span class="method get">GET</span><span class="path">/api/v1/stats</span><span class="desc">统计信息(API Key)</span></li>
        </ul>
    </div>
</div>
</body>
</html>'''
    except Exception as e:
        return f'<h3>数据端口运行中</h3><p>信息加载失败: {e}</p>'


@app.route('/api/data/health', methods=['GET'])
def health_check():
    """数据端口健康检查"""
    try:
        conn = get_db()
        device_count = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
        conn.close()
        return api_response(data={
            'status': 'ok',
            'port': 'data',
            'device_count': device_count,
            'database': DB_PATH
        })
    except Exception as e:
        return api_response(message=f'数据库连接失败: {str(e)}', code=500)


# ==================== 客户端登录（数据端口） ====================

@app.route('/api/data/login', methods=['POST'])
def data_login():
    """客户端登录验证（数据端口专用，仅返回用户信息和单位列表）"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    conn = get_db()
    user = conn.execute(
        'SELECT u.*, p.name as project_name, p.code as project_code '
        'FROM users u LEFT JOIN projects p ON u.project_id = p.id '
        'WHERE u.username = ?',
        (username,)
    ).fetchone()

    if not user or user['password_hash'] != hash_password(password):
        conn.close()
        return jsonify({'error': '用户名或密码错误'}), 401

    # 获取项目列表和单位列表
    departments = []
    projects = []
    is_admin = (user['role'] == 'admin')

    if user['project_id']:
        # 有关联项目：返回该项目下的单位
        rows = conn.execute(
            'SELECT id, name, code, description FROM departments WHERE project_id = ? ORDER BY id',
            (user['project_id'],)
        ).fetchall()
        departments = [dict(r) for r in rows]
        # 返回关联的项目
        proj = conn.execute(
            'SELECT id, name, code, description FROM projects WHERE id = ?',
            (user['project_id'],)
        ).fetchone()
        if proj:
            projects = [dict(proj)]
    elif is_admin:
        # admin 无关联项目：返回所有项目+所有单位
        proj_rows = conn.execute(
            'SELECT id, name, code, description FROM projects ORDER BY id'
        ).fetchall()
        projects = [dict(r) for r in proj_rows]
        dept_rows = conn.execute(
            'SELECT id, name, code, description, project_id FROM departments ORDER BY project_id, id'
        ).fetchall()
        departments = [dict(r) for r in dept_rows]

    conn.close()

    # 记录登录日志
    add_log('DATA_LOGIN',
            f'数据端口登录: {user["display_name"] or user["username"]}',
            f'用户名:{user["username"]}, 角色:{user["role"]}',
            operator=user['username'],
            ip_address=request.remote_addr)

    result = {
        'user': {
            'id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'],
            'role': user['role'],
            'project_id': user['project_id'],
            'project_name': user['project_name'] or ('全部项目' if is_admin else None),
        },
        'departments': departments
    }
    # admin 无关联项目时返回项目列表供选择
    if is_admin and not user['project_id']:
        result['projects'] = projects
    return jsonify(result)


# 兼容客户端使用的 /api/login 路径（客户端默认调用此路径）
@app.route('/api/login', methods=['POST'])
def api_login_compat():
    """兼容旧客户端的登录接口，转发到 data_login"""
    return data_login()


# 兼容客户端使用的 /api/departments 路径
@app.route('/api/departments', methods=['GET'])
def api_departments_compat():
    """获取单位列表（兼容客户端）"""
    project_id = request.args.get('project_id')
    conn = get_db()
    if project_id:
        rows = conn.execute(
            'SELECT id, name, code, description FROM departments WHERE project_id = ? ORDER BY id',
            (project_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, name, code, description FROM departments ORDER BY id'
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ==================== 设备数据提交 ====================

@app.route('/api/devices', methods=['POST'])
def submit_device():
    """客户端提交设备信息（兼容原接口）"""
    data = request.json
    required = ['department_id', 'user_name']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    ip_address = data.get('ip_address', '')
    mac_address = data.get('mac_address', '')
    force = data.get('force', False)
    username = data.get('_username', '未知')
    computer_name = data.get('computer_name', '未知')

    conn = get_db()

    # 检查 IP/MAC 重复
    duplicates = []
    if ip_address and ip_address not in ('未知', '0.0.0.0'):
        ip_dup = conn.execute('''
            SELECT d.id, d.computer_name, d.user_name, d.ip_address, d.mac_address,
                   dept.name as department_name
            FROM devices d
            LEFT JOIN departments dept ON d.department_id = dept.id
            WHERE d.ip_address = ? AND d.ip_address != '未知'
        ''', (ip_address,)).fetchall()
        for r in ip_dup:
            duplicates.append({
                'type': 'IP地址重复', 'field': 'ip_address', 'value': ip_address,
                'device_id': r['id'], 'computer_name': r['computer_name'],
                'user_name': r['user_name'], 'department_name': r['department_name'],
                'mac_address': r['mac_address'],
            })

    if mac_address and mac_address not in ('未知', '00:00:00:00:00:00'):
        mac_dup = conn.execute('''
            SELECT d.id, d.computer_name, d.user_name, d.ip_address, d.mac_address,
                   dept.name as department_name
            FROM devices d
            LEFT JOIN departments dept ON d.department_id = dept.id
            WHERE d.mac_address = ? AND d.mac_address != '未知'
        ''', (mac_address,)).fetchall()
        for r in mac_dup:
            duplicates.append({
                'type': 'MAC地址重复', 'field': 'mac_address', 'value': mac_address,
                'device_id': r['id'], 'computer_name': r['computer_name'],
                'user_name': r['user_name'], 'department_name': r['department_name'],
                'ip_address': r['ip_address'],
            })

    if duplicates and not force:
        conn.close()
        return jsonify({
            'duplicate': True,
            'message': '检测到IP或MAC地址与已有设备重复',
            'duplicates': duplicates
        }), 409

    if duplicates and force:
        dup_info = '; '.join(
            f"{d['type']}:{d['value']}(已存在设备ID:{d['device_id']})"
            for d in duplicates
        )
        add_log('DUPLICATE_CONFIRMED',
                f'设备提交（确认覆盖重复）',
                f'电脑:{computer_name}, IP:{ip_address}, MAC:{mac_address}, [{dup_info}]',
                operator=username)

    cursor = conn.cursor()
    now_local = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO devices (
            department_id, user_name, user_phone, user_position,
            computer_name, ip_address, mac_address, dhcp_enabled,
            os_info, cpu_info, ram_info, disk_info,
            motherboard_info, gpu_info, network_adapter,
            subnet_mask, gateway, dns_servers, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('department_id'), data.get('user_name'), data.get('user_phone'),
        data.get('user_position'), data.get('computer_name'), data.get('ip_address'),
        data.get('mac_address'), data.get('dhcp_enabled'), data.get('os_info'),
        data.get('cpu_info'), data.get('ram_info'), data.get('disk_info'),
        data.get('motherboard_info'), data.get('gpu_info'), data.get('network_adapter'),
        data.get('subnet_mask'), data.get('gateway'), data.get('dns_servers'),
        now_local,
    ))
    conn.commit()
    device_id = cursor.lastrowid
    conn.close()

    add_log('DEVICE_SUBMIT',
            f'设备信息提交成功(数据端口)',
            f'设备ID:{device_id}, 电脑:{computer_name}, IP:{ip_address}, MAC:{mac_address}',
            operator=username,
            ip_address=request.remote_addr)

    return jsonify({'message': '提交成功', 'id': device_id}), 201


# ==================== V1 标准化 API（数据端口） ====================

@app.route('/api/v1/devices', methods=['GET'])
@require_api_key('read')
def v1_get_devices():
    """获取设备列表"""
    project_id = request.args.get('project_id')
    dept_id = request.args.get('department_id')
    keyword = request.args.get('keyword', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 20))))

    conn = get_db()
    query = '''
        SELECT d.*, dept.name as department_name, dept.code as department_code,
               dept.project_id, p.name as project_name
        FROM devices d
        LEFT JOIN departments dept ON d.department_id = dept.id
        LEFT JOIN projects p ON dept.project_id = p.id
        WHERE 1=1
    '''
    count_query = 'SELECT COUNT(*) as total FROM devices d LEFT JOIN departments dept ON d.department_id = dept.id LEFT JOIN projects p ON dept.project_id = p.id WHERE 1=1'
    params = []
    if project_id:
        query += ' AND dept.project_id = ?'
        params.append(project_id)
    if dept_id:
        query += ' AND d.department_id = ?'
        params.append(dept_id)
    if keyword:
        query += ' AND (d.user_name LIKE ? OR d.computer_name LIKE ? OR d.ip_address LIKE ?)'
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    total = conn.execute(count_query, params).fetchone()[0]
    query += ' ORDER BY d.collected_at DESC'
    query += f' LIMIT {per_page} OFFSET {(page - 1) * per_page}'
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return api_response(data={
        'items': [dict(r) for r in rows],
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


@app.route('/api/v1/devices/<int:device_id>', methods=['GET'])
@require_api_key('read')
def v1_get_device(device_id):
    """获取单个设备详情"""
    conn = get_db()
    row = conn.execute('''
        SELECT d.*, dept.name as department_name, dept.code as department_code,
               dept.project_id, p.name as project_name
        FROM devices d LEFT JOIN departments dept ON d.department_id = dept.id
        LEFT JOIN projects p ON dept.project_id = p.id WHERE d.id = ?
    ''', (device_id,)).fetchone()
    conn.close()
    if not row:
        return api_response(message='设备不存在', code=404)
    return api_response(data=dict(row))


@app.route('/api/v1/devices', methods=['POST'])
@require_api_key('write')
def v1_create_device():
    """创建设备记录（API Key 认证）"""
    data = request.json
    required = ['department_id', 'user_name']
    for field in required:
        if not data.get(field):
            return api_response(message=f'缺少必填字段: {field}', code=400)

    ip_address = data.get('ip_address', '')
    mac_address = data.get('mac_address', '')
    force = data.get('force', False)
    key_name = g.api_key_info.get('name', 'API')

    conn = get_db()
    duplicates = []
    if ip_address and ip_address not in ('未知', '0.0.0.0'):
        ip_dup = conn.execute('''
            SELECT d.id, d.computer_name, d.user_name, d.ip_address, dept.name as department_name
            FROM devices d LEFT JOIN departments dept ON d.department_id = dept.id
            WHERE d.ip_address = ? AND d.ip_address != '未知'
        ''', (ip_address,)).fetchall()
        for r in ip_dup:
            duplicates.append({'type': 'IP地址重复', 'value': ip_address, 'device_id': r['id'], 'computer_name': r['computer_name']})

    if mac_address and mac_address not in ('未知', '00:00:00:00:00:00'):
        mac_dup = conn.execute('''
            SELECT d.id, d.computer_name, d.user_name, d.mac_address, dept.name as department_name
            FROM devices d LEFT JOIN departments dept ON d.department_id = dept.id
            WHERE d.mac_address = ? AND d.mac_address != '未知'
        ''', (mac_address,)).fetchall()
        for r in mac_dup:
            duplicates.append({'type': 'MAC地址重复', 'value': mac_address, 'device_id': r['id'], 'computer_name': r['computer_name']})

    if duplicates and not force:
        conn.close()
        return api_response(data={'duplicates': duplicates}, message='检测到IP或MAC地址重复，设置 force=true 强制提交', code=409)

    cursor = conn.cursor()
    now_local = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO devices (department_id, user_name, user_phone, user_position,
            computer_name, ip_address, mac_address, dhcp_enabled,
            os_info, cpu_info, ram_info, disk_info,
            motherboard_info, gpu_info, network_adapter,
            subnet_mask, gateway, dns_servers, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('department_id'), data.get('user_name'), data.get('user_phone'),
        data.get('user_position'), data.get('computer_name'), data.get('ip_address'),
        data.get('mac_address'), data.get('dhcp_enabled'), data.get('os_info'),
        data.get('cpu_info'), data.get('ram_info'), data.get('disk_info'),
        data.get('motherboard_info'), data.get('gpu_info'), data.get('network_adapter'),
        data.get('subnet_mask'), data.get('gateway'), data.get('dns_servers'),
        now_local,
    ))
    conn.commit()
    device_id = cursor.lastrowid
    conn.close()

    add_log('DEVICE_SUBMIT', f'API设备提交成功(数据端口)', f'设备ID:{device_id}, IP:{ip_address}', operator=f'API:{key_name}')
    return api_response(data={'id': device_id}, message='创建成功', code=201)


@app.route('/api/v1/projects', methods=['GET'])
@require_api_key('read')
def v1_get_projects():
    """获取项目列表"""
    conn = get_db()
    rows = conn.execute('SELECT * FROM projects ORDER BY id').fetchall()
    conn.close()
    return api_response(data=[dict(r) for r in rows])


@app.route('/api/v1/departments', methods=['GET'])
@require_api_key('read')
def v1_get_departments():
    """获取单位列表"""
    project_id = request.args.get('project_id')
    conn = get_db()
    query = 'SELECT d.*, p.name as project_name FROM departments d LEFT JOIN projects p ON d.project_id = p.id WHERE 1=1'
    params = []
    if project_id:
        query += ' AND d.project_id = ?'
        params.append(project_id)
    query += ' ORDER BY d.id'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return api_response(data=[dict(r) for r in rows])


@app.route('/api/v1/stats', methods=['GET'])
@require_api_key('read')
def v1_get_stats():
    """获取统计信息"""
    conn = get_db()
    device_count = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
    today_count = conn.execute("SELECT COUNT(*) FROM devices WHERE DATE(collected_at) = DATE('now', 'localtime')").fetchone()[0]
    conn.close()
    return api_response(data={'device_count': device_count, 'today_count': today_count})


# ==================== 启动 ====================

DATA_PORT = int(os.environ.get('DATA_PORT', 5001))

if __name__ == '__main__':
    print('=' * 50)
    print(f'  设备信息采集器 - 数据端口已启动')
    print(f'  数据库: {DB_PATH}')
    print(f'  数据API: http://0.0.0.0:{DATA_PORT}')
    print(f'  健康检查: http://0.0.0.0:{DATA_PORT}/api/data/health')
    print('=' * 50)
    app.run(host='0.0.0.0', port=DATA_PORT, debug=True)

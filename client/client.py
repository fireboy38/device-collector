"""
设备信息采集器 - 客户端
Tkinter GUI，自动采集电脑设备信息并提交到服务端
支持登录、自动关联项目、按项目筛选单位
支持从 CONFIG.INI 读取服务器地址和账号密码（支持AES密文密码）
"""
import os
import sys
import traceback

# ===== PyInstaller Tkinter 兼容性修复 =====
def _setup_tcl_tk():
    """确保 PyInstaller 打包后 Tcl/Tk 库路径正确"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        tcl_dir = os.path.join(base_path, 'tcl', 'tcl8.6')
        tk_dir = os.path.join(base_path, 'tcl', 'tk8.6')
        if os.path.exists(tcl_dir):
            os.environ['TCL_LIBRARY'] = tcl_dir
        if os.path.exists(tk_dir):
            os.environ['TK_LIBRARY'] = tk_dir

_setup_tcl_tk()

import tkinter as tk
from tkinter import ttk, messagebox
import platform
import subprocess
import re
import json
import uuid
import base64
import configparser
import urllib.request
import urllib.error

# ===== subprocess 兼容性 =====
# PyInstaller --windowed 模式下，subprocess 调用必须指定 CREATE_NO_WINDOW
# 否则 wmic/ipconfig 等命令会卡住或弹出控制台窗口
if getattr(sys, 'frozen', False):
    _SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW
else:
    _SUBPROCESS_FLAGS = 0

# AES 加密密钥（与服务端一致，硬编码在客户端EXE中）
_AES_KEY = b'DC2026SK16BYTKEY'  # 16字节 AES-128 密钥


def _aes_decrypt(encrypted_b64):
    """AES-CBC 解密，兼容服务端加密格式"""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        raw = base64.b64decode(encrypted_b64)
        iv = raw[:16]
        ct = raw[16:]
        cipher = AES.new(_AES_KEY, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt.decode('utf-8')
    except Exception as e:
        print(f"AES解密失败: {e}")
        return encrypted_b64  # 解密失败返回原文（可能是明文密码）


def _is_encrypted(value):
    """判断密码是否为 AES 加密密文（ENC: 前缀）"""
    return value.startswith('ENC:')


def _get_app_dir():
    """获取应用所在目录（兼容 PyInstaller 打包后的路径）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，使用 exe 所在目录
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def load_config():
    """从 CONFIG.INI 读取配置（支持密文密码自动解密）"""
    config = {
        'server_url': 'http://localhost:5000',
        'username': '',
        'password': '',
    }

    # CONFIG.INI 与 EXE 同目录
    config_path = os.path.join(_get_app_dir(), 'CONFIG.INI')

    if not os.path.exists(config_path):
        return config

    try:
        parser = configparser.ConfigParser()
        # 保持键名大小写
        parser.optionxform = str
        parser.read(config_path, encoding='utf-8')

        if parser.has_section('Server'):
            config['server_url'] = parser.get('Server', 'ServerUrl', fallback=config['server_url']).strip()

        if parser.has_section('Account'):
            config['username'] = parser.get('Account', 'Username', fallback='').strip()
            raw_password = parser.get('Account', 'Password', fallback='').strip()
            # 如果密码是密文格式（ENC: 前缀），则解密
            if _is_encrypted(raw_password):
                config['password'] = _aes_decrypt(raw_password[4:])
            else:
                config['password'] = raw_password

    except Exception as e:
        print(f"读取 CONFIG.INI 失败: {e}")

    return config


class DeviceCollector:
    """设备信息采集类"""

    @staticmethod
    def get_computer_name():
        try:
            return platform.node()
        except Exception:
            return os.environ.get('COMPUTERNAME', '未知')

    @staticmethod
    def get_os_info():
        try:
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['wmic', 'os', 'get', 'Caption,Version,BuildNumber', '/value'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                lines = [l.strip() for l in result.stdout.strip().split('\n') if '=' in l]
                info = {}
                for line in lines:
                    k, v = line.split('=', 1)
                    info[k.strip()] = v.strip()
                caption = info.get('Caption', '')
                build = info.get('BuildNumber', '')
                return f"{caption} (Build {build})".strip() if caption else platform.platform()
            else:
                return platform.platform()
        except Exception:
            return platform.platform()

    @staticmethod
    def get_cpu_info():
        try:
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'Name', '/value'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                for line in result.stdout.strip().split('\n'):
                    if '=' in line:
                        return line.split('=', 1)[1].strip()
            else:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line.lower():
                            return line.split(':', 1)[1].strip()
        except Exception:
            pass
        return '未知'

    @staticmethod
    def get_ram_info():
        try:
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['wmic', 'memorychip', 'get', 'Capacity', '/value'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                total = 0
                for line in result.stdout.strip().split('\n'):
                    if '=' in line:
                        val = line.split('=', 1)[1].strip()
                        if val:
                            total += int(val)
                if total > 0:
                    return f"{total / (1024**3):.1f} GB"
            else:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            return f"{int(line.split()[1]) / (1024**2):.1f} GB"
        except Exception:
            pass
        return '未知'

    @staticmethod
    def get_disk_info():
        try:
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['wmic', 'diskdrive', 'get', 'Model,Size', '/value'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                disks = []
                current = {}
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if '=' in line:
                        k, v = line.split('=', 1)
                        current[k.strip()] = v.strip()
                        if k.strip() == 'Size' and current.get('Model'):
                            size_gb = int(current['Size']) / (1024**3) if current['Size'] else 0
                            disks.append(f"{current['Model']} ({size_gb:.0f}GB)")
                            current = {}
                return '; '.join(disks) if disks else '未知'
        except Exception:
            pass
        return '未知'

    @staticmethod
    def get_motherboard_info():
        try:
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['wmic', 'baseboard', 'get', 'Manufacturer,Product', '/value'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                info = {}
                for line in result.stdout.strip().split('\n'):
                    if '=' in line:
                        k, v = line.split('=', 1)
                        info[k.strip()] = v.strip()
                m, p = info.get('Manufacturer', ''), info.get('Product', '')
                if m or p:
                    return f"{m} {p}".strip()
        except Exception:
            pass
        return '未知'

    @staticmethod
    def get_gpu_info():
        try:
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['wmic', 'path', 'win32_videocontroller', 'get', 'Name', '/value'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                gpus = []
                for line in result.stdout.strip().split('\n'):
                    if '=' in line:
                        val = line.split('=', 1)[1].strip()
                        if val:
                            gpus.append(val)
                return '; '.join(gpus) if gpus else '未知'
        except Exception:
            pass
        return '未知'

    @staticmethod
    def _parse_ipconfig_line(line):
        if ':' not in line or not line.startswith('   '):
            return None
        parts = line.split(':', 1)
        if len(parts) != 2:
            return None
        key_raw, val = parts[0].strip(), parts[1].strip()
        m = re.search(r'\.\s*\.', key_raw)
        if m:
            key = key_raw[:m.start()].strip()
        else:
            m2 = re.search(r'\s+\.\s*$', key_raw)
            key = key_raw[:m2.start()].strip() if m2 else key_raw
        return (key, val) if key else None

    @staticmethod
    def get_network_info():
        info = {
            'ip_address': '未知', 'mac_address': '未知', 'dhcp_enabled': '未知',
            'network_adapter': '未知', 'subnet_mask': '未知', 'gateway': '未知',
            'dns_servers': '未知',
        }
        if platform.system() != 'Windows':
            try:
                info['mac_address'] = ':'.join(re.findall('..', '%012x' % uuid.getnode()))
            except Exception:
                pass
            return info
        try:
            result = subprocess.run(
                ['ipconfig', '/all'], capture_output=True, text=True, timeout=15,
                encoding='gbk', errors='ignore',
                creationflags=_SUBPROCESS_FLAGS
            )
            adapters, current_adapter = [], None
            for line in result.stdout.split('\n'):
                if not line.startswith(' ') and line.strip():
                    adapter_match = re.match(
                        r'^.*?(?:adapter|适配器)\s*(.+?)\s*[:：]\s*$', line, re.IGNORECASE
                    )
                    if adapter_match:
                        if current_adapter:
                            adapters.append(current_adapter)
                        current_adapter = {
                            'name': adapter_match.group(1).strip(),
                            'ip': None, 'mac': None, 'dhcp': None,
                            'subnet': None, 'gateway': None,
                            'dns': None, 'dns_extra': [], 'description': None,
                        }
                        continue
                if current_adapter is None:
                    continue
                parsed = DeviceCollector._parse_ipconfig_line(line)
                if parsed is None:
                    continue
                key, val = parsed
                kl = key.lower()
                if kl in ('description', '描述'):
                    current_adapter['description'] = val
                elif kl in ('physical address', '物理地址'):
                    if val and val != '(None)' and '-' in val:
                        current_adapter['mac'] = val.replace('-', ':').upper()
                elif 'ipv4' in kl and ('address' in kl or '地址' in kl):
                    val = re.sub(r'\(.*?\)', '', val).strip()
                    if val and not val.startswith('169.254') and val != '0.0.0.0':
                        current_adapter['ip'] = val
                elif 'dhcp' in kl and ('enabled' in kl or '启用' in kl):
                    vl = val.lower()
                    if '是' in val or 'yes' in vl:
                        current_adapter['dhcp'] = '是'
                    elif '否' in val or 'no' in vl:
                        current_adapter['dhcp'] = '否'
                elif 'subnet' in kl or '子网掩码' in kl:
                    if val: current_adapter['subnet'] = val
                elif 'default gateway' in kl or '默认网关' in kl:
                    if val: current_adapter['gateway'] = val
                elif 'dns' in kl and ('server' in kl or '服务器' in kl):
                    if val and val != '(None)':
                        current_adapter['dns'] = val
                        current_adapter['dns_extra'] = [val]
                else:
                    if current_adapter.get('dns_extra') and val and re.match(r'^\d+\.\d+\.\d+\.\d+$', val):
                        current_adapter['dns_extra'].append(val)
            if current_adapter:
                adapters.append(current_adapter)

            best = None
            for a in adapters:
                if a['ip'] and a['mac']:
                    desc = (a.get('description') or '').lower()
                    if any(s in desc for s in ['virtual','vmware','vbox','hyper-v','virtualbox','虚拟','vpn','loopback']):
                        continue
                    best = a; break
            if not best:
                for a in adapters:
                    if a['ip'] and a['mac']:
                        best = a; break
            if best:
                info['ip_address'] = best['ip'] or '未知'
                info['mac_address'] = best['mac'] or '未知'
                info['dhcp_enabled'] = best['dhcp'] or '未知'
                info['subnet_mask'] = best['subnet'] or '未知'
                info['gateway'] = best['gateway'] or '未知'
                dns_list = best.get('dns_extra', [])
                info['dns_servers'] = ', '.join(dns_list) if dns_list else (best.get('dns') or '未知')
                info['network_adapter'] = best.get('description') or best.get('name') or '未知'
        except Exception as e:
            print(f"获取网络信息异常: {e}")
        return info

    @classmethod
    def collect_all(cls):
        network = cls.get_network_info()
        return {
            'computer_name': cls.get_computer_name(),
            'os_info': cls.get_os_info(),
            'cpu_info': cls.get_cpu_info(),
            'ram_info': cls.get_ram_info(),
            'disk_info': cls.get_disk_info(),
            'motherboard_info': cls.get_motherboard_info(),
            'gpu_info': cls.get_gpu_info(),
            **network
        }


class CollectorApp:
    """客户端 GUI 应用"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("设备信息采集器")

        # 自适应窗口大小：1024x768 屏幕也可完整显示
        WIN_W = 700
        screen_h = self.root.winfo_screenheight()
        # 预留任务栏 40px，窗口高度取 min(880, 可用高度-20)
        WIN_H = min(880, screen_h - 60)
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.minsize(WIN_W, 600)
        self.root.resizable(False, True)

        # 居中
        x = (self.root.winfo_screenwidth() - WIN_W) // 2
        y = max(0, (screen_h - WIN_H) // 2 - 20)
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        # 从 CONFIG.INI 加载配置
        self.config = load_config()

        self.server_url = tk.StringVar(value=self.config['server_url'])
        self.username_var = tk.StringVar(value=self.config['username'])
        self.password_var = tk.StringVar(value=self.config['password'])
        self.departments = []
        self.device_info = {}
        self.logged_in_user = None
        self._login_projects = []
        self._login_departments = []

        self._build_ui()
        # 延迟采集设备信息（先让窗口渲染完成，避免 wmic 卡住导致窗口白屏）
        self.root.after(200, self._collect_info)

        # 如果 CONFIG.INI 中有账号密码，自动登录
        if self.config['username'] and self.config['password']:
            self.root.after(1000, self._auto_login)

    def _build_ui(self):
        """构建界面（自适应屏幕高度，1024x768 也可完整显示）"""

        # ===== 底部固定按钮（先 pack，确保始终可见） =====
        bottom_frame = tk.Frame(self.root, bg="#ffffff", height=56)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=12, pady=(0, 10))
        bottom_frame.pack_propagate(False)

        tk.Button(
            bottom_frame, text="🔄 重新采集", command=self._collect_info,
            font=("Microsoft YaHei UI", 11),
            bg="#f0f0f0", fg="#333", activebackground="#e0e0e0",
            relief=tk.FLAT, padx=14, pady=4, cursor="hand2"
        ).pack(side=tk.LEFT, pady=8)

        self.submit_btn = tk.Button(
            bottom_frame, text="📤 提交到服务器", command=self._submit,
            font=("Microsoft YaHei UI", 13, "bold"),
            bg="#1a73e8", fg="white", activebackground="#1557b0", activeforeground="white",
            relief=tk.FLAT, padx=24, pady=6, cursor="hand2"
        )
        self.submit_btn.pack(side=tk.RIGHT, pady=8)

        # ===== 中间可滚动区域 =====
        canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)

        self._scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=(8, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2), pady=(8, 0))

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        top_frame = self._scroll_frame

        # 标题（缩小字号节省空间）
        title_frame = ttk.Frame(top_frame)
        title_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(title_frame, text="🖥️ 设备信息采集器",
                  font=("Microsoft YaHei UI", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(title_frame, text="客户端",
                  font=("Microsoft YaHei UI", 10), foreground="#888").pack(side=tk.LEFT, padx=(6, 0))

        # ===== 服务器配置 + 登录 =====
        server_frame = ttk.LabelFrame(top_frame, text=" 服务器配置与登录 ", padding=8)
        server_frame.pack(fill=tk.X, pady=(0, 6))

        row0 = ttk.Frame(server_frame)
        row0.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row0, text="服务地址:", width=8).pack(side=tk.LEFT)
        ttk.Entry(row0, textvariable=self.server_url, width=38).pack(side=tk.LEFT, padx=4)

        row1 = ttk.Frame(server_frame)
        row1.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row1, text="用户名:", width=8).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.username_var, width=16).pack(side=tk.LEFT, padx=4)
        ttk.Label(row1, text="密码:").pack(side=tk.LEFT, padx=(6, 0))
        ttk.Entry(row1, textvariable=self.password_var, width=14, show="*").pack(side=tk.LEFT, padx=4)

        row2 = ttk.Frame(server_frame)
        row2.pack(fill=tk.X)
        ttk.Button(row2, text="🔐 登录", command=self._login).pack(side=tk.LEFT)
        self.login_status = ttk.Label(row2, text="未登录", foreground="#ea4335")
        self.login_status.pack(side=tk.LEFT, padx=8)
        self.project_label = ttk.Label(row2, text="", foreground="#1a73e8",
                                        font=("Microsoft YaHei UI", 9, "bold"))
        self.project_label.pack(side=tk.LEFT, padx=4)

        # ===== 人员信息 =====
        person_frame = ttk.LabelFrame(top_frame, text=" 使用人员信息 ", padding=8)
        person_frame.pack(fill=tk.X, pady=(0, 6))

        row_dept = ttk.Frame(person_frame)
        row_dept.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row_dept, text="所属单位:", width=8).pack(side=tk.LEFT)
        self.dept_combo = ttk.Combobox(row_dept, state="readonly", width=34)
        self.dept_combo.pack(side=tk.LEFT, padx=4)

        row_name = ttk.Frame(person_frame)
        row_name.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row_name, text="使用人:", width=8).pack(side=tk.LEFT)
        self.user_name = ttk.Entry(row_name, width=38)
        self.user_name.pack(side=tk.LEFT, padx=4)

        row_phone = ttk.Frame(person_frame)
        row_phone.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row_phone, text="联系电话:", width=8).pack(side=tk.LEFT)
        self.user_phone = ttk.Entry(row_phone, width=38)
        self.user_phone.pack(side=tk.LEFT, padx=4)

        row_loc = ttk.Frame(person_frame)
        row_loc.pack(fill=tk.X)
        ttk.Label(row_loc, text="安装位置:", width=8).pack(side=tk.LEFT)
        self.install_location = ttk.Entry(row_loc, width=38)
        self.install_location.pack(side=tk.LEFT, padx=4)

        # ===== 设备信息展示 =====
        device_frame = ttk.LabelFrame(top_frame, text=" 自动采集设备信息 ", padding=8)
        device_frame.pack(fill=tk.X, pady=(0, 6))

        # 固定高度显示设备信息，内部可滚动
        self.info_text = tk.Text(device_frame, font=("Consolas", 10), wrap=tk.WORD,
                                  bg="#f8f9fb", relief=tk.FLAT, padx=10, pady=6, height=12)
        info_scroll = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=info_scroll.set)
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        info_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.info_text.config(state=tk.DISABLED)

    def _auto_login(self):
        """CONFIG.INI 中有账号密码时自动登录"""
        self._login(silent=True)

    def _login(self, silent=False):
        """登录服务器"""
        url = self.server_url.get().rstrip('/') + '/api/login'
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()

        if not username or not password:
            if not silent:
                messagebox.showwarning("提示", "请输入用户名和密码！")
            return

        try:
            payload = json.dumps({'username': username, 'password': password}).encode('utf-8')
            req = urllib.request.Request(url, data=payload,
                                          headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            # data_login 返回 {user: {...}, departments: [...], projects: [...]}
            user = result.get('user', result)
            self.logged_in_user = user

            # 保存项目列表和单位列表
            self._login_projects = result.get('projects', [])
            self._login_departments = result.get('departments', [])

            if user.get('role') == 'admin':
                self.login_status.config(text=f"✅ 管理员: {user.get('display_name', username)}", foreground="#1a73e8")
                if user.get('project_name'):
                    self.project_label.config(text=f"📂 项目: {user['project_name']}")
                else:
                    self.project_label.config(text="📂 全部项目")
            else:
                project_name = user.get('project_name') or '未关联'
                self.login_status.config(text=f"✅ {user.get('display_name', username)}", foreground="#34a853")
                self.project_label.config(text=f"📂 项目: {project_name}")

            self._fetch_departments()

        except urllib.error.HTTPError as e:
            if not silent:
                if e.code == 401:
                    messagebox.showerror("登录失败", "用户名或密码错误！")
                else:
                    messagebox.showerror("登录失败", f"服务器错误: {e.code}")
            self.login_status.config(text="❌ 登录失败", foreground="#ea4335")
        except urllib.error.URLError:
            if not silent:
                messagebox.showerror("连接失败", "无法连接到服务器\n请检查服务端是否已启动。")
            self.login_status.config(text="❌ 连接失败", foreground="#ea4335")
        except Exception as e:
            if not silent:
                messagebox.showerror("错误", f"登录失败:\n{str(e)}")
            self.login_status.config(text="❌ 异常", foreground="#ea4335")

    def _fetch_departments(self):
        """根据登录用户的项目加载单位列表"""
        if not self.logged_in_user:
            messagebox.showwarning("提示", "请先登录！")
            return

        project_id = self.logged_in_user.get('project_id')

        # 优先使用登录时返回的单位数据，避免额外请求
        if self._login_departments:
            data = self._login_departments
            # 如果用户有关联项目，只显示该项目的单位
            if project_id:
                data = [d for d in data if d.get('project_id') == project_id]
        else:
            url = self.server_url.get().rstrip('/') + '/api/departments'
            if project_id:
                url += f'?project_id={project_id}'

            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                messagebox.showerror("错误", f"获取单位列表失败:\n{str(e)}")
                return

        self.departments = data
        dept_names = [f"{d['name']} (ID:{d['id']})" for d in data]
        self.dept_combo['values'] = dept_names

        if dept_names:
            self.dept_combo.current(0)

    def _collect_info(self):
        """采集设备信息"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, "⏳ 正在采集设备信息...\n\n")
        self.root.update()

        self.device_info = DeviceCollector.collect_all()
        self.info_text.delete(1.0, tk.END)

        display_items = [
            ("🖥️ 电脑名称", self.device_info.get('computer_name')),
            ("📡 IP 地址", self.device_info.get('ip_address')),
            ("🏷️ MAC 地址", self.device_info.get('mac_address')),
            ("🔀 自动获取IP (DHCP)", self.device_info.get('dhcp_enabled')),
            ("🌐 子网掩码", self.device_info.get('subnet_mask')),
            ("🚪 默认网关", self.device_info.get('gateway')),
            ("📋 DNS 服务器", self.device_info.get('dns_servers')),
            ("🔌 网卡", self.device_info.get('network_adapter')),
            ("💻 操作系统", self.device_info.get('os_info')),
            ("⚙️ CPU", self.device_info.get('cpu_info')),
            ("🧠 内存", self.device_info.get('ram_info')),
            ("💾 硬盘", self.device_info.get('disk_info')),
            ("🔧 主板", self.device_info.get('motherboard_info')),
            ("🎮 显卡", self.device_info.get('gpu_info')),
        ]

        for label, value in display_items:
            self.info_text.insert(tk.END, f"  {label}:  ", "label")
            self.info_text.insert(tk.END, f"{value or '未知'}\n", "value")

        self.info_text.tag_configure("label", foreground="#1a73e8",
                                      font=("Microsoft YaHei UI", 10, "bold"))
        self.info_text.tag_configure("value", foreground="#333",
                                      font=("Consolas", 10))
        self.info_text.config(state=tk.DISABLED)

    def _submit(self, force=False):
        """提交设备信息，force=True 表示用户确认覆盖重复"""
        if not self.logged_in_user:
            messagebox.showwarning("提示", "请先登录服务器！")
            return

        name = self.user_name.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入使用人姓名！")
            self.user_name.focus()
            return

        dept_selection = self.dept_combo.get()
        if not dept_selection:
            messagebox.showwarning("提示", "请先登录并选择所属单位！")
            return

        try:
            dept_id = int(dept_selection.split("ID:")[1].rstrip(")"))
        except (IndexError, ValueError):
            messagebox.showwarning("提示", "单位信息解析失败，请重新选择！")
            return

        payload = {
            'department_id': dept_id,
            'user_name': name,
            'user_phone': self.user_phone.get().strip(),
            'user_position': self.install_location.get().strip(),
            '_username': self.logged_in_user.get('username', '未知'),
            'force': force,
            **self.device_info
        }

        url = self.server_url.get().rstrip('/') + '/api/devices'
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data,
                                          headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            messagebox.showinfo("提交成功",
                                f"设备信息已成功提交到服务器！\n记录ID: {result.get('id', '未知')}")

        except urllib.error.HTTPError as e:
            if e.code == 409:
                # IP/MAC 重复，需要用户确认
                try:
                    body = json.loads(e.read().decode('utf-8'))
                except Exception:
                    body = {}
                duplicates = body.get('duplicates', [])
                msg = "⚠️ 检测到以下 IP/MAC 地址与已有设备重复：\n\n"
                for dup in duplicates:
                    msg += f"  • {dup.get('type', '重复')}: {dup.get('value', '')}\n"
                    msg += f"    已存在设备: 电脑={dup.get('computer_name', '未知')}, "
                    msg += f"使用人={dup.get('user_name', '未知')}, "
                    msg += f"单位={dup.get('department_name', '未知')}\n\n"
                msg += "是否仍然提交？（重复记录将保留，请管理员在服务端处理）"

                confirm = messagebox.askyesno("IP/MAC 地址重复确认", msg)
                if confirm:
                    self._submit(force=True)
                else:
                    messagebox.showinfo("已取消", "提交已取消，请检查设备信息或联系管理员。")
            elif e.code == 401:
                messagebox.showerror("提交失败", "认证失败，请重新登录！")
            else:
                messagebox.showerror("提交失败", f"服务器错误: {e.code}")

        except urllib.error.URLError:
            messagebox.showerror("提交失败",
                                  "无法连接到服务器\n请检查服务端是否已启动。")
        except Exception as e:
            messagebox.showerror("提交失败", f"提交设备信息失败:\n{str(e)}")

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    try:
        app = CollectorApp()
        app.run()
    except Exception as e:
        # PyInstaller --windowed 模式下异常无法在控制台看到，写入日志文件
        error_log = os.path.join(os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__)), 'error.log')
        with open(error_log, 'w', encoding='utf-8') as f:
            f.write(f"设备采集器启动失败\n")
            f.write(f"时间: {__import__('datetime').datetime.now()}\n")
            f.write(f"错误: {e}\n\n")
            f.write(traceback.format_exc())
        # 尝试弹出错误对话框
        try:
            import tkinter as _tk
            _root = _tk.Tk()
            _root.withdraw()
            _tk.messagebox.showerror("启动失败", f"程序启动出错：\n{e}\n\n详细信息已保存到 error.log")
            _root.destroy()
        except Exception:
            pass

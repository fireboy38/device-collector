#!/bin/bash
# ============================================
# 设备信息采集器 - 国产操作系统客户端
# 兼容：银河麒麟(Kylin)、统信UOS、深度Deepin
# 以及 Ubuntu/CentOS 等主流 Linux 发行版
# 依赖：bash, curl, 基础系统命令（lshw/dmidecode/ip/hostname）
# 无需 Python
# ============================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/CONFIG.INI"

# ===== 读取 CONFIG.INI =====
SERVER_URL=""
USERNAME=""
PASSWORD=""
DEPARTMENT_ID=""
USER_NAME=""
USER_PHONE=""
FORCE_SUBMIT="0"

read_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}[错误] 未找到 CONFIG.INI 配置文件！${NC}"
        echo "请确保 CONFIG.INI 与本脚本在同一目录。"
        exit 1
    fi

    local section=""
    while IFS='=' read -r key value; do
        # 去除前后空格和注释
        key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        
        # 跳过注释和空行
        [[ "$key" =~ ^#.* ]] && continue
        [[ -z "$key" ]] && continue
        [[ "$key" =~ ^\[.*\]$ ]] && continue
        
        case "$key" in
            ServerUrl) SERVER_URL="$value" ;;
            Username) USERNAME="$value" ;;
            Password) PASSWORD="$value" ;;
            DepartmentId) DEPARTMENT_ID="$value" ;;
            UserName) USER_NAME="$value" ;;
            UserPhone) USER_PHONE="$value" ;;
            ForceSubmit) FORCE_SUBMIT="$value" ;;
        esac
    done < "$CONFIG_FILE"

    # 去除末尾斜杠
    SERVER_URL="${SERVER_URL%/}"

    if [ -z "$SERVER_URL" ]; then
        echo -e "${RED}[错误] CONFIG.INI 中未配置 ServerUrl${NC}"
        exit 1
    fi
}

# ===== 检测操作系统 =====
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_NAME="${NAME:-Unknown}"
        OS_VERSION="${VERSION:-Unknown}"
        OS_ID="${ID:-unknown}"
        OS_INFO="$OS_NAME $OS_VERSION"
    elif [ -f /etc/kylin-release ]; then
        OS_INFO="$(cat /etc/kylin-release)"
        OS_ID="kylin"
    elif [ -f /etc/uos-release ]; then
        OS_INFO="$(cat /etc/uos-release)"
        OS_ID="uos"
    elif command -v lsb_release &>/dev/null; then
        OS_INFO="$(lsb_release -d | cut -f2-) $(lsb_release -r | cut -f2-)"
        OS_ID="$(lsb_release -i | cut -f2- | tr '[:upper:]' '[:lower:]')"
    else
        OS_INFO="$(uname -s) $(uname -r)"
        OS_ID="linux"
    fi
}

# ===== 采集设备信息 =====
collect_info() {
    echo -e "${BLUE}[1/5] 读取配置...${NC}"
    read_config
    echo "  服务器: $SERVER_URL"
    echo "  账号: $USERNAME"
    echo ""

    echo -e "${BLUE}[2/5] 采集设备信息...${NC}"

    # 计算机名
    COMPUTER_NAME=$(hostname 2>/dev/null || echo "未知")

    # 操作系统
    detect_os

    # CPU
    CPU_INFO="未知"
    if [ -f /proc/cpuinfo ]; then
        CPU_INFO=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^[[:space:]]*//' || echo "未知")
    fi
    if [ "$CPU_INFO" = "未知" ] && command -v lscpu &>/dev/null; then
        CPU_INFO=$(lscpu 2>/dev/null | grep 'Model name' | cut -d: -f2- | sed 's/^[[:space:]]*//' || echo "未知")
    fi

    # 内存
    RAM_INFO="未知"
    if [ -f /proc/meminfo ]; then
        RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
        if [ -n "$RAM_KB" ] && [ "$RAM_KB" -gt 0 ] 2>/dev/null; then
            RAM_GB=$(echo "scale=1; $RAM_KB / 1048576" | bc 2>/dev/null || echo "$((RAM_KB / 1048576))")
            RAM_INFO="${RAM_GB} GB"
        fi
    fi

    # 硬盘
    DISK_INFO="未知"
    if command -v lsblk &>/dev/null; then
        DISK_INFO=$(lsblk -d -o MODEL,SIZE -n 2>/dev/null | grep -v '^' | head -5 | tr '\n' ';' | sed 's/;$//' || echo "未知")
    elif command -v fdisk &>/dev/null; then
        DISK_INFO=$(fdisk -l 2>/dev/null | grep "Disk /dev" | head -3 | awk '{print $2, $3, $4}' | tr '\n' ';' | sed 's/;$//' || echo "未知")
    fi
    [ -z "$DISK_INFO" ] && DISK_INFO="未知"

    # 主板
    MOTHERBOARD_INFO="未知"
    if command -v dmidecode &>/dev/null; then
        MB_MFR=$(dmidecode -s baseboard-manufacturer 2>/dev/null | head -1 || echo "")
        MB_PRD=$(dmidecode -s baseboard-product-name 2>/dev/null | head -1 || echo "")
        if [ -n "$MB_MFR" ] || [ -n "$MB_PRD" ]; then
            MOTHERBOARD_INFO="${MB_MFR} ${MB_PRD}"
        fi
    fi

    # 显卡
    GPU_INFO="未知"
    if command -v lspci &>/dev/null; then
        GPU_INFO=$(lspci 2>/dev/null | grep -i 'vga\|3d\|display' | cut -d: -f3- | sed 's/^[[:space:]]*//' | tr '\n' ';' | sed 's/;$//' || echo "未知")
    fi
    [ -z "$GPU_INFO" ] && GPU_INFO="未知"

    # 网络信息
    echo -e "${BLUE}[3/5] 采集网络信息...${NC}"
    
    IP_ADDR="未知"
    MAC_ADDR="未知"
    NET_ADAPTER="未知"
    SUBNET="未知"
    GATEWAY="未知"
    DNS="未知"
    DHCP="未知"

    # 获取主网卡
    if command -v ip &>/dev/null; then
        # 用 ip 命令获取默认路由的网卡
        DEFAULT_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
        if [ -z "$DEFAULT_IF" ]; then
            DEFAULT_IF=$(ip -4 addr show 2>/dev/null | grep -B2 'scope global' | grep -oP '(?<=: )\w+' | head -1)
        fi
        
        if [ -n "$DEFAULT_IF" ]; then
            IP_ADDR=$(ip -4 addr show "$DEFAULT_IF" 2>/dev/null | grep -oP '(?<=inet )\S+' | cut -d/ -f1 | head -1 || echo "未知")
            MAC_ADDR=$(ip link show "$DEFAULT_IF" 2>/dev/null | grep -oP '(?<=link/ether )\S+' | head -1 || echo "未知")
            NET_ADAPTER="$DEFAULT_IF"
            
            # 子网掩码
            PREFIX=$(ip -4 addr show "$DEFAULT_IF" 2>/dev/null | grep -oP '(?<=inet )\S+' | cut -d/ -f2 | head -1)
            if [ -n "$PREFIX" ]; then
                # 前缀转掩码
                case "$PREFIX" in
                    24) SUBNET="255.255.255.0" ;;
                    16) SUBNET="255.255.0.0" ;;
                    8)  SUBNET="255.0.0.0" ;;
                    *)  SUBNET="/$PREFIX" ;;
                esac
            fi
            
            # 网关
            GATEWAY=$(ip route show default 2>/dev/null | awk '{print $3}' | head -1 || echo "未知")
        fi
    elif command -v ifconfig &>/dev/null; then
        # 用 ifconfig（旧系统兼容）
        DEFAULT_IF=$(route -n 2>/dev/null | grep '^0.0.0.0' | awk '{print $8}' | head -1)
        if [ -z "$DEFAULT_IF" ]; then
            DEFAULT_IF=$(ifconfig 2>/dev/null | grep -B1 'inet ' | grep -oP '^\w+' | head -1)
        fi
        if [ -n "$DEFAULT_IF" ]; then
            IP_ADDR=$(ifconfig "$DEFAULT_IF" 2>/dev/null | grep 'inet ' | awk '{print $2}' | head -1 || echo "未知")
            MAC_ADDR=$(ifconfig "$DEFAULT_IF" 2>/dev/null | grep -oP 'ether \K\S+' | head -1 || echo "未知")
            NET_ADAPTER="$DEFAULT_IF"
            GATEWAY=$(route -n 2>/dev/null | grep '^0.0.0.0' | awk '{print $2}' | head -1 || echo "未知")
        fi
    fi

    # DNS
    if [ -f /etc/resolv.conf ]; then
        DNS=$(grep '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | tr '\n' ',' | sed 's/,$//' || echo "未知")
    fi

    # 显示采集结果
    echo ""
    echo "---- 采集到的设备信息 ----"
    echo "  计算机名: $COMPUTER_NAME"
    echo "  操作系统: $OS_INFO"
    echo "  CPU: $CPU_INFO"
    echo "  内存: $RAM_INFO"
    echo "  硬盘: $DISK_INFO"
    echo "  主板: $MOTHERBOARD_INFO"
    echo "  显卡: $GPU_INFO"
    echo "  IP: $IP_ADDR"
    echo "  MAC: $MAC_ADDR"
    echo "  网卡: $NET_ADAPTER"
    echo "  子网: $SUBNET"
    echo "  网关: $GATEWAY"
    echo "  DNS: $DNS"
    echo "---------------------------"
    echo ""
}

# ===== 交互式填写人员信息 =====
fill_user_info() {
    if [ -z "$USER_NAME" ]; then
        read -p "请输入使用人姓名: " USER_NAME
    fi
    if [ -z "$USER_PHONE" ]; then
        read -p "请输入联系电话(可选): " USER_PHONE
    fi
}

# ===== 登录并选择单位 =====
login_and_select_dept() {
    echo -e "${BLUE}[4/5] 连接服务器...${NC}"

    if [ -n "$DEPARTMENT_ID" ]; then
        return 0
    fi

    # 登录
    LOGIN_RESP=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
        "$SERVER_URL/api/data/login" 2>/dev/null || echo "")

    if [ -z "$LOGIN_RESP" ]; then
        echo -e "${YELLOW}[警告] 无法连接服务器，请手动输入单位ID${NC}"
        read -p "请输入单位ID(数字): " DEPARTMENT_ID
        return 0
    fi

    # 检查是否有错误
    ERROR=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); d.get('error','')" 2>/dev/null || echo "")
    if [ -n "$ERROR" ]; then
        echo -e "${RED}[错误] 登录失败: $ERROR${NC}"
        read -p "请手动输入单位ID(数字): " DEPARTMENT_ID
        return 0
    fi

    # 解析单位列表（用 python3 或 jq）
    if command -v python3 &>/dev/null; then
        DEPT_COUNT=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('departments',[])))" 2>/dev/null || echo "0")
    elif command -v jq &>/dev/null; then
        DEPT_COUNT=$(echo "$LOGIN_RESP" | jq '.departments | length' 2>/dev/null || echo "0")
    else
        DEPT_COUNT=0
    fi

    if [ "$DEPT_COUNT" -eq 0 ] 2>/dev/null; then
        echo -e "${YELLOW}[警告] 未获取到单位列表，请手动输入单位ID${NC}"
        read -p "请输入单位ID(数字): " DEPARTMENT_ID
        return 0
    fi

    # 显示单位列表
    echo ""
    echo "  请选择所属单位:"
    echo "  -------------------------"
    if command -v python3 &>/dev/null; then
        echo "$LOGIN_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for i, dept in enumerate(d.get('departments', []), 1):
    print(f'  {i}. {dept[\"name\"]} (ID:{dept[\"id\"]})')
" 2>/dev/null
    elif command -v jq &>/dev/null; then
        echo "$LOGIN_RESP" | jq -r '.departments[] | "  \(.id). \(.name) (ID:\(.id))"' 2>/dev/null
    fi
    echo "  -------------------------"

    read -p "请输入序号: " DEPT_CHOICE

    # 获取选择对应的 department_id
    if command -v python3 &>/dev/null; then
        DEPARTMENT_ID=$(echo "$LOGIN_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
depts = d.get('departments', [])
idx = int('$DEPT_CHOICE') - 1
if 0 <= idx < len(depts): print(depts[idx]['id'])
" 2>/dev/null || echo "")
    elif command -v jq &>/dev/null; then
        DEPARTMENT_ID=$(echo "$LOGIN_RESP" | jq -r ".departments[$((DEPT_CHOICE-1))].id" 2>/dev/null || echo "")
    fi

    if [ -z "$DEPARTMENT_ID" ]; then
        echo -e "${RED}[错误] 无效选择${NC}"
        exit 1
    fi

    echo "  已选择单位ID: $DEPARTMENT_ID"
}

# ===== 提交数据 =====
submit_data() {
    echo ""
    echo -e "${BLUE}[5/5] 提交数据到服务器...${NC}"

    # 构建 JSON（用 python3 或手动拼接）
    if command -v python3 &>/dev/null; then
        JSON_DATA=$(python3 -c "
import json
data = {
    'department_id': int('$DEPARTMENT_ID'),
    'user_name': '$USER_NAME',
    'user_phone': '$USER_PHONE',
    'computer_name': '''$COMPUTER_NAME''',
    'ip_address': '$IP_ADDR',
    'mac_address': '$MAC_ADDR',
    'dhcp_enabled': '$DHCP',
    'os_info': '''$OS_INFO''',
    'cpu_info': '''$CPU_INFO''',
    'ram_info': '$RAM_INFO',
    'disk_info': '''$DISK_INFO''',
    'motherboard_info': '''$MOTHERBOARD_INFO''',
    'gpu_info': '''$GPU_INFO''',
    'network_adapter': '$NET_ADAPTER',
    'subnet_mask': '$SUBNET',
    'gateway': '$GATEWAY',
    'dns_servers': '$DNS',
    'force': True if '$FORCE_SUBMIT' == '1' else False,
    '_username': '$USERNAME'
}
print(json.dumps(data, ensure_ascii=False))
" 2>/dev/null)
    else
        # 无 python3，手动拼接 JSON（注意特殊字符转义）
        JSON_DATA="{
  \"department_id\": $DEPARTMENT_ID,
  \"user_name\": \"$USER_NAME\",
  \"user_phone\": \"$USER_PHONE\",
  \"computer_name\": \"$COMPUTER_NAME\",
  \"ip_address\": \"$IP_ADDR\",
  \"mac_address\": \"$MAC_ADDR\",
  \"dhcp_enabled\": \"$DHCP\",
  \"os_info\": \"$OS_INFO\",
  \"cpu_info\": \"$CPU_INFO\",
  \"ram_info\": \"$RAM_INFO\",
  \"disk_info\": \"$DISK_INFO\",
  \"motherboard_info\": \"$MOTHERBOARD_INFO\",
  \"gpu_info\": \"$GPU_INFO\",
  \"network_adapter\": \"$NET_ADAPTER\",
  \"subnet_mask\": \"$SUBNET\",
  \"gateway\": \"$GATEWAY\",
  \"dns_servers\": \"$DNS\",
  \"force\": $([ "$FORCE_SUBMIT" = "1" ] && echo "true" || echo "false"),
  \"_username\": \"$USERNAME\"
}"
    fi

    # 用 curl 提交
    RESP=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "$JSON_DATA" \
        "$SERVER_URL/api/devices" 2>/dev/null || echo -e "\n000")

    HTTP_CODE=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | sed '$d')

    echo ""
    if [ "$HTTP_CODE" = "201" ]; then
        DEVICE_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "?")
        echo -e "${GREEN}============================================${NC}"
        echo -e "${GREEN}  提交成功！${NC}"
        echo -e "${GREEN}  设备ID: $DEVICE_ID${NC}"
        echo -e "${GREEN}============================================${NC}"
    elif [ "$HTTP_CODE" = "409" ]; then
        echo -e "${YELLOW}============================================${NC}"
        echo -e "${YELLOW}  IP/MAC地址重复！${NC}"
        echo -e "${YELLOW}  如需强制提交，请将 CONFIG.INI 中 ForceSubmit=1${NC}"
        echo -e "${YELLOW}============================================${NC}"
    else
        echo -e "${RED}============================================${NC}"
        echo -e "${RED}  提交失败！HTTP $HTTP_CODE${NC}"
        ERROR_MSG=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','未知'))" 2>/dev/null || echo "$BODY")
        echo -e "${RED}  原因: $ERROR_MSG${NC}"
        echo -e "${RED}============================================${NC}"
    fi
}

# ===== 主流程 =====
main() {
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  设备信息采集器 - 国产操作系统版${NC}"
    echo -e "${GREEN}  兼容: 银河麒麟/统信UOS/Deepin/Linux${NC}"
    echo -e "${GREEN}  无需安装 Python${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""

    # 检查 curl
    if ! command -v curl &>/dev/null; then
        echo -e "${RED}[错误] 未找到 curl 命令，请先安装: sudo apt install curl${NC}"
        exit 1
    fi

    collect_info
    fill_user_info
    login_and_select_dept
    submit_data

    echo ""
}

main

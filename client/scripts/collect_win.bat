@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================
:: 设备信息采集器 - Windows BAT 客户端
:: 兼容 Windows 7/8/10/11（无需 Python）
:: 通过 CONFIG.INI 读取配置，纯批处理采集+PowerShell上传
:: ============================================

title 设备信息采集器
color 0A
echo ============================================
echo   设备信息采集器 - Windows BAT版
echo   兼容 Win7/8/10/11，无需安装Python
echo ============================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: ===== 读取 CONFIG.INI =====
set "SERVER_URL="
set "USERNAME="
set "PASSWORD="
set "DEPARTMENT_ID="
set "USER_NAME="
set "USER_PHONE="
set "FORCE_SUBMIT=0"

if not exist "CONFIG.INI" (
    echo [错误] 未找到 CONFIG.INI 配置文件！
    echo 请确保 CONFIG.INI 与本脚本在同一目录。
    pause
    exit /b 1
)

echo [1/5] 读取配置...
for /f "usebackq tokens=1,* delims==" %%a in ("CONFIG.INI") do (
    set "key=%%a"
    set "val=%%b"
    :: 去除空格
    set "key=!key: =!"
    set "val=!val: =!"
    
    if /i "!key!"=="ServerUrl" set "SERVER_URL=!val!"
    if /i "!key!"=="Username" set "USERNAME=!val!"
    if /i "!key!"=="Password" set "PASSWORD=!val!"
    if /i "!key!"=="DepartmentId" set "DEPARTMENT_ID=!val!"
    if /i "!key!"=="UserName" set "USER_NAME=!val!"
    if /i "!key!"=="UserPhone" set "USER_PHONE=!val!"
    if /i "!key!"=="ForceSubmit" set "FORCE_SUBMIT=!val!"
)

if "%SERVER_URL%"=="" (
    echo [错误] CONFIG.INI 中未配置 ServerUrl
    pause
    exit /b 1
)

:: 去除末尾斜杠
if "%SERVER_URL:~-1%"=="/" set "SERVER_URL=%SERVER_URL:~0,-1%"

echo   服务器: %SERVER_URL%
echo   账号: %USERNAME%
echo.

:: ===== 采集设备信息 =====
echo [2/5] 采集设备信息...

:: 计算机名
set "COMPUTER_NAME=%COMPUTERNAME%"

:: 操作系统
set "OS_INFO="
for /f "tokens=2 delims==" %%a in ('wmic os get Caption /value 2^>nul ^| find "="') do set "OS_INFO=%%a"
for /f "tokens=2 delims==" %%a in ('wmic os get Version /value 2^>nul ^| find "="') do set "OS_INFO=!OS_INFO! (%%a)"
if "%OS_INFO%"=="" set "OS_INFO=未知"

:: CPU
set "CPU_INFO="
for /f "tokens=2 delims==" %%a in ('wmic cpu get Name /value 2^>nul ^| find "="') do set "CPU_INFO=%%a"
if "%CPU_INFO%"=="" set "CPU_INFO=未知"

:: 内存
set "RAM_INFO="
set /a RAM_TOTAL=0
for /f "tokens=2 delims==" %%a in ('wmic memorychip get Capacity /value 2^>nul ^| find "="') do (
    set /a RAM_TOTAL+=%%a/1073741824 2>nul
)
if !RAM_TOTAL! gtr 0 (
    set "RAM_INFO=!RAM_TOTAL! GB"
) else (
    :: 备用方案：用 PhysicalMemory
    for /f "tokens=2 delims==" %%a in ('wmic computersystem get TotalPhysicalMemory /value 2^>nul ^| find "="') do (
        set /a RAM_MB=%%a/1048576 2>nul
        if !RAM_MB! gtr 0 set "RAM_INFO=!RAM_MB! MB"
    )
    if "%RAM_INFO%"=="" set "RAM_INFO=未知"
)

:: 硬盘
set "DISK_INFO="
for /f "tokens=2 delims==" %%a in ('wmic diskdrive get Model /value 2^>nul ^| find "="') do (
    if "%DISK_INFO%"=="" (
        set "DISK_INFO=%%a"
    ) else (
        set "DISK_INFO=!DISK_INFO!; %%a"
    )
)
if "%DISK_INFO%"=="" set "DISK_INFO=未知"

:: 主板
set "MOTHERBOARD_INFO="
set "MB_MFR="
set "MB_PRD="
for /f "tokens=2 delims==" %%a in ('wmic baseboard get Manufacturer /value 2^>nul ^| find "="') do set "MB_MFR=%%a"
for /f "tokens=2 delims==" %%a in ('wmic baseboard get Product /value 2^>nul ^| find "="') do set "MB_PRD=%%a"
if not "%MB_MFR%"=="" set "MOTHERBOARD_INFO=%MB_MFR% %MB_PRD%"
if "%MOTHERBOARD_INFO%"==" " set "MOTHERBOARD_INFO=未知"
if "%MOTHERBOARD_INFO%"=="" set "MOTHERBOARD_INFO=未知"

:: 显卡
set "GPU_INFO="
for /f "tokens=2 delims==" %%a in ('wmic path win32_videocontroller get Name /value 2^>nul ^| find "="') do (
    if "%GPU_INFO%"=="" (
        set "GPU_INFO=%%a"
    ) else (
        set "GPU_INFO=!GPU_INFO!; %%a"
    )
)
if "%GPU_INFO%"=="" set "GPU_INFO=未知"

:: 网络信息（用 PowerShell 采集更可靠）
echo [3/5] 采集网络信息...
set "IP_ADDR="
set "MAC_ADDR="
set "DHCP="
set "NET_ADAPTER="
set "SUBNET="
set "GATEWAY="
set "DNS="

:: 用 PowerShell 获取活跃网卡信息（Win7 自带 PowerShell 2.0）
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; if ($adapter) { $adapter.IPAddress[0] } } catch { '' }" 2^>nul`) do set "IP_ADDR=%%a"

for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; if ($adapter) { $adapter.MACAddress -replace ':','-' } } catch { '' }" 2^>nul`) do set "MAC_ADDR=%%a"

for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; if ($adapter) { if ($adapter.DHCPEnabled) { '是' } else { '否' } } } catch { '' }" 2^>nul`) do set "DHCP=%%a"

for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; $na = Get-WmiObject Win32_NetworkAdapter | Where-Object { $_.Index -eq $adapter.Index }; if ($na) { $na.Name } } catch { '' }" 2^>nul`) do set "NET_ADAPTER=%%a"

for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; if ($adapter) { $adapter.IPSubnet[0] } } catch { '' }" 2^>nul`) do set "SUBNET=%%a"

for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; if ($adapter) { $adapter.DefaultIPGateway[0] } } catch { '' }" 2^>nul`) do set "GATEWAY=%%a"

for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $adapter = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.IPAddress[0] -notmatch '^(169\.254|0\.0\.0)' } | Select-Object -First 1; if ($adapter -and $adapter.DNSServerSearchOrder) { $adapter.DNSServerSearchOrder -join ', ' } } catch { '' }" 2^>nul`) do set "DNS=%%a"

if "%IP_ADDR%"=="" set "IP_ADDR=未知"
if "%MAC_ADDR%"=="" set "MAC_ADDR=未知"
if "%DHCP%"=="" set "DHCP=未知"
if "%NET_ADAPTER%"=="" set "NET_ADAPTER=未知"
if "%SUBNET%"=="" set "SUBNET=未知"
if "%GATEWAY%"=="" set "GATEWAY=未知"
if "%DNS%"=="" set "DNS=未知"

:: 显示采集结果
echo.
echo ---- 采集到的设备信息 ----
echo   计算机名: %COMPUTER_NAME%
echo   操作系统: %OS_INFO%
echo   CPU: %CPU_INFO%
echo   内存: %RAM_INFO%
echo   硬盘: %DISK_INFO%
echo   主板: %MOTHERBOARD_INFO%
echo   显卡: %GPU_INFO%
echo   IP: %IP_ADDR%
echo   MAC: %MAC_ADDR%
echo   DHCP: %DHCP%
echo   网卡: %NET_ADAPTER%
echo   子网: %SUBNET%
echo   网关: %GATEWAY%
echo   DNS: %DNS%
echo ---------------------------
echo.

:: ===== 交互式填写人员信息（CONFIG.INI 未配置时） =====
if "%USER_NAME%"=="" (
    set /p "USER_NAME=请输入使用人姓名: "
)
if "%USER_PHONE%"=="" (
    set /p "USER_PHONE=请输入联系电话(可选): "
)

:: ===== 登录获取 department_id =====
echo.
echo [4/5] 连接服务器...

:: 如果 CONFIG.INI 中已配置 DepartmentId，跳过登录
if not "%DEPARTMENT_ID%"=="" goto :submit

:: 登录获取单位列表
set "LOGIN_JSON={\"username\":\"%USERNAME%\",\"password\":\"%PASSWORD%\"}"

:: 写临时 JSON 文件避免命令行转义问题
set "TMPFILE=%TEMP%\dc_login_%RANDOM%.json"
> "%TMPFILE%" echo {"username":"%USERNAME%","password":"%PASSWORD%"}

:: 用 PowerShell 调用登录 API
set "DEPARTMENTS_JSON="
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "try { $body = Get-Content '%TMPFILE%' -Raw; $resp = Invoke-RestMethod -Uri '%SERVER_URL%/api/data/login' -Method Post -Body $body -ContentType 'application/json'; if ($resp.departments) { $resp.departments | ConvertTo-Json -Compress } } catch { Write-Error $_.Exception.Message; '' }" 2^>nul`) do set "DEPARTMENTS_JSON=%%a"

del "%TMPFILE%" 2>nul

if "%DEPARTMENTS_JSON%"=="" (
    echo [警告] 登录失败，请手动输入单位ID
    set /p "DEPARTMENT_ID=请输入单位ID(数字): "
    goto :submit
)

:: 显示单位列表让用户选择
echo.
echo   请选择所属单位:
echo   -------------------------
powershell -NoProfile -Command "$json = '%DEPARTMENTS_JSON%'; $depts = $json | ConvertFrom-Json; $i = 1; foreach ($d in $depts) { Write-Host ('  ' + $i + '. ' + $d.name + ' (ID:' + $d.id + ')'); $i++ }"
echo   -------------------------
set /p "DEPT_CHOICE=请输入序号: "

:: 根据选择获取 department_id
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "$json = '%DEPARTMENTS_JSON%'; $depts = $json | ConvertFrom-Json; $idx = [int]'%DEPT_CHOICE%' - 1; if ($depts[$idx]) { $depts[$idx].id }" 2^>nul`) do set "DEPARTMENT_ID=%%a"

if "%DEPARTMENT_ID%"=="" (
    echo [错误] 无效选择
    pause
    exit /b 1
)

echo   已选择单位ID: %DEPARTMENT_ID%

:: ===== 提交数据 =====
:submit
echo.
echo [5/5] 提交数据到服务器...

:: 构建 JSON 数据（写临时文件避免转义问题）
set "SUBMIT_FILE=%TEMP%\dc_submit_%RANDOM%.json"

:: 用 PowerShell 构建并提交（避免 BAT 的 JSON 转义地狱）
powershell -NoProfile -Command ^
    "$data = @{ ^
        department_id = [int]'%DEPARTMENT_ID%'; ^
        user_name = '%USER_NAME%'; ^
        user_phone = '%USER_PHONE%'; ^
        computer_name = '%COMPUTER_NAME%'; ^
        ip_address = '%IP_ADDR%'; ^
        mac_address = '%MAC_ADDR%'; ^
        dhcp_enabled = '%DHCP%'; ^
        os_info = '%OS_INFO%'; ^
        cpu_info = '%CPU_INFO%'; ^
        ram_info = '%RAM_INFO%'; ^
        disk_info = '%DISK_INFO%'; ^
        motherboard_info = '%MOTHERBOARD_INFO%'; ^
        gpu_info = '%GPU_INFO%'; ^
        network_adapter = '%NET_ADAPTER%'; ^
        subnet_mask = '%SUBNET%'; ^
        gateway = '%GATEWAY%'; ^
        dns_servers = '%DNS%'; ^
        force = if ('%FORCE_SUBMIT%' -eq '1') { $true } else { $false }; ^
        _username = '%USERNAME%' ^
    }; ^
    $json = $data | ConvertTo-Json -Compress; ^
    Write-Host '[提交] 连接 %SERVER_URL%/api/devices ...'; ^
    try { ^
        $resp = Invoke-RestMethod -Uri '%SERVER_URL%/api/devices' -Method Post -Body $json -ContentType 'application/json; charset=utf-8'; ^
        Write-Host ''; ^
        Write-Host '============================================'; ^
        Write-Host '  提交成功！'; ^
        Write-Host '  设备ID:' $resp.id; ^
        Write-Host '============================================'; ^
    } catch { ^
        $err = $_.Exception; ^
        if ($err.Response) { ^
            $reader = New-Object System.IO.StreamReader($err.Response.GetResponseStream()); ^
            $errBody = $reader.ReadToEnd(); ^
            Write-Host ''; ^
            Write-Host '============================================'; ^
            Write-Host '  提交失败！'; ^
            try { ^
                $errObj = $errBody | ConvertFrom-Json; ^
                if ($errObj.duplicate) { ^
                    Write-Host '  原因: IP/MAC地址重复'; ^
                    Write-Host '  如需强制提交，请将 CONFIG.INI 中 ForceSubmit=1'; ^
                } else { ^
                    Write-Host '  原因:' $errObj.error; ^
                } ^
            } catch { ^
                Write-Host '  原因:' $errBody; ^
            } ^
            Write-Host '============================================'; ^
        } else { ^
            Write-Host ''; ^
            Write-Host '============================================'; ^
            Write-Host '  连接服务器失败！'; ^
            Write-Host '  请检查网络和服务器地址'; ^
            Write-Host '============================================'; ^
        } ^
    }"

del "%SUBMIT_FILE%" 2>nul

echo.
pause

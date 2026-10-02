# ============================================================
# 健身营养 Agent - 多轮交互式服务管理菜单
#   服务：MCP 桥接 8010/8011、嵌入 8001、FastAPI 8000、前端
#   模式：dev(Vite 5173 热更新) / prod(FastAPI 同源托管构建产物)
#   网络：local(127.0.0.1) / public(0.0.0.0 开放局域网访问)
# 由根目录 start.bat 调用（绕过执行策略），也可自行：
#   powershell -ExecutionPolicy Bypass -File scripts\manage.ps1
# ============================================================

$ErrorActionPreference = 'Continue'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $Root
$env:NO_PROXY = 'localhost,127.0.0.1'
$env:no_proxy = 'localhost,127.0.0.1'

# 运行参数（持久于本次菜单会话）
$script:Mode    = 'dev'     # dev | prod
$script:Network = 'local'   # local | public

# Cloudflare 快速隧道（公网）：PID 与日志
$script:TunnelPidPath = Join-Path 'data' 'run' 'cloudflared.pid'
$script:TunnelLog     = Join-Path 'logs' 'cloudflared_quick.log'

$Ports = [ordered]@{
    8000 = 'FastAPI'
    5173 = '前端 Vite (dev)'
    8001 = '嵌入服务'
    8010 = 'MCP 动作库'
    8011 = 'MCP 营养库'
}

# ------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------
function Write-Title($t) {
    Write-Host ''
    Write-Host ('  ' + $t) -ForegroundColor Cyan
}

function Get-LanIp {
    try {
        (Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Select-Object -First 1 -ExpandProperty IPAddress)
    } catch { $null }
}

function Get-PortPid([int]$port) {
    try {
        $line = netstat -ano | Select-String -Pattern "LISTENING" | Select-String -Pattern (":" + $port + " ") | Select-Object -First 1
        if ($line) { return ($line.ToString().Trim() -split '\s+')[-1] }
    } catch {}
    return $null
}

function Stop-Port([int]$port, [string]$label) {
    $p = Get-PortPid $port
    if ($p) {
        taskkill /F /T /PID $p *> $null
        Write-Host ("    [停止] {0} 端口 {1} (PID {2})" -f $label, $port, $p) -ForegroundColor Yellow
    } else {
        Write-Host ("    [跳过] {0} 端口 {1} 未运行" -f $label, $port) -ForegroundColor DarkGray
    }
}

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

# 独立窗口启动：日志完整可见，标题标明服务
function Start-LogWindow([string]$title, [string]$command) {
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', $command) | Out-Null
    Write-Host ("    [启动] {0}" -f $title) -ForegroundColor Green
}

# ------------------------------------------------------------
# 动作
# ------------------------------------------------------------
function Invoke-Setup {
    Write-Title '检查 / 同步依赖'
    if (-not (Test-Command 'uv')) {
        Write-Host '    [错误] 未找到 uv，请先安装：https://docs.astral.sh/uv/' -ForegroundColor Red
        return $false
    }
    & uv sync
    if ($LASTEXITCODE -ne 0) { Write-Host '    [错误] uv sync 失败' -ForegroundColor Red; return $false }
    if ($script:Mode -eq 'dev') {
        if (-not (Test-Path 'frontend/node_modules')) {
            Write-Host '    首次运行：安装前端依赖 ...'
            npm --prefix frontend install
        }
    } else {
        Write-Host '    生产模式：构建前端 ...'
        npm --prefix frontend run build
        if ($LASTEXITCODE -ne 0) { Write-Host '    [错误] 前端构建失败' -ForegroundColor Red; return $false }
    }
    return $true
}

function Start-Services {
    if (-not (Invoke-Setup)) { Read-Return; return }

    $host_ = if ($script:Network -eq 'public') { '0.0.0.0' } else { '127.0.0.1' }

    Write-Title '启动 MCP 数据桥接 (8010 / 8011)'
    & uv run python scripts/start_mcp_servers.py up

    Write-Title '启动嵌入服务 (8001，10-60 秒加载模型)'
    & uv run python scripts/start_embedding_server.py up
    Write-Host '    嵌入失败不阻塞：仅画像语义检索不可用' -ForegroundColor DarkGray

    Write-Title ('启动 FastAPI 与前端 (host={0})' -f $host_)
    if (Get-PortPid 8000) {
        Write-Host '    [跳过] 8000 已在运行（如需应用新 host，请先停止再启动）' -ForegroundColor DarkGray
    } else {
        Start-LogWindow 'FastAPI :8000' ("uv run uvicorn app.main:app --host {0} --port 8000" -f $host_)
    }

    if ($script:Mode -eq 'dev') {
        if (Get-PortPid 5173) {
            Write-Host '    [跳过] 5173 已在运行' -ForegroundColor DarkGray
        } else {
            $viteHost = if ($script:Network -eq 'public') { ' -- --host 0.0.0.0' } else { '' }
            Start-LogWindow ('前端 Vite :5173') ("npm --prefix frontend run dev{0}" -f $viteHost)
        }
    }

    if ($script:Network -eq 'public') { Add-FirewallRules }

    Show-Urls
    Read-Return
}

function Stop-Services {
    Write-Title '停止 FastAPI 与前端'
    Stop-Port 8000 'FastAPI'
    if ($script:Mode -eq 'dev') { Stop-Port 5173 '前端 Vite' }
    Write-Title '停止 MCP 与嵌入服务'
    & uv run python scripts/start_mcp_servers.py down
    & uv run python scripts/start_embedding_server.py down
    # 若隧道在运行一并停止，避免转发到已关闭的服务
    $tp = Get-TunnelPid
    if ($tp) { taskkill /F /T /PID $tp *> $null; Remove-Item $script:TunnelPidPath -ErrorAction SilentlyContinue; Write-Host '    [停止] Cloudflare 隧道' -ForegroundColor Yellow }
    Write-Host '    完成。' -ForegroundColor Green
    Read-Return
}

function Restart-Services {
    Write-Title '重启：先停止'
    Stop-Port 8000 'FastAPI'
    Stop-Port 5173 '前端 Vite'
    & uv run python scripts/start_mcp_servers.py down
    & uv run python scripts/start_embedding_server.py down
    Start-Sleep -Seconds 2
    Start-Services
}

function Show-Status {
    Write-Title '端口监听状态'
    foreach ($p in $Ports.Keys) {
        if ($script:Mode -eq 'prod' -and $p -eq 5173) { continue }
        $pidv = Get-PortPid $p
        if ($pidv) {
            Write-Host ("    [ UP ] {0,-18} 端口 {1}  PID {2}" -f $Ports[$p], $p, $pidv) -ForegroundColor Green
        } else {
            Write-Host ("    [DOWN] {0,-18} 端口 {1}" -f $Ports[$p], $p) -ForegroundColor DarkGray
        }
    }
    Write-Title '当前配置'
    Write-Host ("    运行模式 : {0}    网络 : {1}" -f $script:Mode, $script:Network)
    Show-Urls
    Read-Return
}

function Show-Urls {
    $lan = Get-LanIp
    Write-Title '访问地址'
    if ($script:Mode -eq 'dev') {
        Write-Host '    前端界面 : http://localhost:5173'
        Write-Host '    API 文档 : http://localhost:8000/docs'
        if ($script:Network -eq 'public' -and $lan) {
            Write-Host ''
            Write-Host ("    局域网前端 : http://{0}:5173" -f $lan) -ForegroundColor Cyan
            Write-Host ("    局域网 API  : http://{0}:8000/docs" -f $lan) -ForegroundColor Cyan
        }
    } else {
        Write-Host '    应用入口 : http://localhost:8000'
        Write-Host '    API 文档 : http://localhost:8000/docs'
        if ($script:Network -eq 'public' -and $lan) {
            Write-Host ("    局域网入口 : http://{0}:8000" -f $lan) -ForegroundColor Cyan
        }
    }
    if ($script:Network -eq 'public') {
        Write-Host ''
        Write-Host '    公网仅限局域网/同网段。要真正的互联网访问需自行做端口映射或内网穿透。' -ForegroundColor DarkYellow
    }
}

function Add-FirewallRules {
    Write-Title '配置 Windows 防火墙'
    $ports = @(8000)
    if ($script:Mode -eq 'dev') { $ports += 5173 }
    foreach ($p in $ports) {
        $rule = "FitnessAgent-$p"
        netsh advfirewall firewall show rule name=$rule *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host ("    [已存在] 防火墙规则 {0}" -f $rule) -ForegroundColor DarkGray
            continue
        }
        netsh advfirewall firewall add rule name=$rule dir=in action=allow protocol=TCP localport=$p *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host ("    [放行] TCP {0}" -f $p) -ForegroundColor Green
        } else {
            Write-Host ("    [需手动] 未能添加防火墙规则（可能需要管理员）。请以管理员运行：" -f $p) -ForegroundColor Yellow
            Write-Host ("        netsh advfirewall firewall add rule name=""{0}"" dir=in action=allow protocol=TCP localport={1}" -f $rule, $p) -ForegroundColor Yellow
        }
    }
}

function Show-Logs {
    Write-Title '日志文件'
    $logs = @(
        @{ Name = 'MCP 动作库'; Path = 'logs/mcp/exerciseapi.out.log' },
        @{ Name = 'MCP 营养库'; Path = 'logs/mcp/nutrition-mcp.out.log' },
        @{ Name = '嵌入服务';   Path = 'logs/embedding_server.log' }
    )
    for ($i = 0; $i -lt $logs.Count; $i++) {
        $exists = Test-Path $logs[$i].Path
        Write-Host ("    [{0}] {1}  {2}" -f ($i + 1), $logs[$i].Name, $(if ($exists) { '' } else { '(暂无文件)' }))
    }
    Write-Host '    [0] 返回'
    $c = Read-Host '选择日志（将在新窗口实时跟踪，Ctrl+C 退出跟踪）'
    if ($c -eq '0' -or $c -eq '') { return }
    $idx = 0
    if ([int]::TryParse($c, [ref]$idx) -and $idx -ge 1 -and $idx -le $logs.Count) {
        $item = $logs[$idx - 1]
        if (Test-Path $item.Path) {
            Start-LogWindow ("日志 - " + $item.Name) ("powershell -NoExit -Command ""Get-Content -Path '{0}' -Wait -Tail 40""" -f $item.Path)
        } else {
            Write-Host '    日志文件尚不存在。' -ForegroundColor Yellow
            Start-Sleep -Seconds 1
        }
    }
}

function Set-Config {
    Write-Title '运行模式'
    Write-Host '    [1] 开发模式 dev  —— Vite 热更新 (5173)，适合开发调试'
    Write-Host '    [2] 生产模式 prod —— 构建后由 FastAPI 同源托管 (8000)'
    $c = Read-Host '选择'
    if ($c -eq '2') { $script:Mode = 'prod' } else { $script:Mode = 'dev' }

    Write-Title '网络访问'
    Write-Host '    [1] 仅本机 local —— 127.0.0.1'
    Write-Host '    [2] 开放访问 public —— 0.0.0.0，局域网可连（含防火墙放行）'
    $c = Read-Host '选择'
    if ($c -eq '2') { $script:Network = 'public' } else { $script:Network = 'local' }

    Write-Host ("    已设置：模式={0}  网络={1}" -f $script:Mode, $script:Network) -ForegroundColor Green
    Start-Sleep -Seconds 1
}

# ------------------------------------------------------------
# Cloudflare 快速隧道（真正的公网访问）
# ------------------------------------------------------------
function Find-Cloudflared {
    # 优先 PATH，其次默认安装路径
    $cmd = Get-Command 'cloudflared' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
    if (Test-Path $candidate) { return $candidate }
    $candidate2 = 'C:\Program Files\cloudflared\cloudflared.exe'
    if (Test-Path $candidate2) { return $candidate2 }
    return $null
}

# 隧道转发目标：dev 打到 Vite，prod 打到 FastAPI（与当前模式一致）
function Get-TunnelTarget {
    if ($script:Mode -eq 'dev') { return 'http://localhost:5173' }
    return 'http://localhost:8000'
}

function Get-TunnelPid {
    if (Test-Path $script:TunnelPidPath) {
        $p = (Get-Content $script:TunnelPidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($p) {
            $alive = Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue
            if ($alive) { return [int]$p }
        }
        Remove-Item $script:TunnelPidPath -ErrorAction SilentlyContinue
    }
    return $null
}

function Start-Tunnel {
    Write-Title '启动 Cloudflare 快速隧道'
    $existing = Get-TunnelPid
    if ($existing) {
        Write-Host "    [已运行] 隧道 PID $existing" -ForegroundColor DarkGray
        Show-TunnelUrl
        Read-Return
        return
    }

    $cf = Find-Cloudflared
    if (-not $cf) {
        Write-Host '    [错误] 未找到 cloudflared。' -ForegroundColor Red
        Write-Host '        下载：https://github.com/cloudflare/cloudflared/releases （cloudflared-windows-amd64.exe）' -ForegroundColor Yellow
        Write-Host '        或：winget install --id Cloudflare.cloudflared' -ForegroundColor Yellow
        Read-Return
        return
    }

    # 目标端口需先有服务
    $target = Get-TunnelTarget
    $targetPort = if ($script:Mode -eq 'dev') { 5173 } else { 8000 }
    if (-not (Get-PortPid $targetPort)) {
        Write-Host ("    [错误] 目标 {0} 未运行，请先在当前模式({1})下启动服务。" -f $target, $script:Mode) -ForegroundColor Red
        Read-Return
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $script:TunnelLog) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path $script:TunnelPidPath) | Out-Null

    Write-Host ("    转发：{0} -> 公网" -f $target)
    Write-Host '    正在向 Cloudflare 申请公网地址（约 5-20 秒）...' -ForegroundColor DarkGray

    # --protocol http2：强制 TCP（Clash 下 UDP/QUIC 会丢包）；--edge-ip-version 4：仅 IPv4
    $cfArgs = @(
        'tunnel', '--url', $target,
        '--no-autoupdate', '--protocol', 'http2', '--edge-ip-version', '4'
    )
    $p = Start-Process -FilePath $cf -ArgumentList $cfArgs `
        -RedirectStandardError $script:TunnelLog `
        -RedirectStandardOutput "$script:TunnelLog.out" `
        -WindowStyle Hidden -PassThru
    $p.Id | Set-Content $script:TunnelPidPath

    # 轮询日志，拿到 https://*.trycloudflare.com 地址
    $url = $null
    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep -Seconds 1
        $url = Get-TunnelUrlFromLog
        if ($url) { break }
    }
    Show-TunnelUrl
    Read-Return
}

function Get-TunnelUrlFromLog {
    foreach ($f in @($script:TunnelLog, "$script:TunnelLog.out")) {
        if (Test-Path $f) {
            $m = Select-String -Path $f -Pattern 'https://[-a-z0-9]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { return ($m.Matches[0].Value) }
        }
    }
    return $null
}

function Show-TunnelUrl {
    $url = Get-TunnelUrlFromLog
    if ($url) {
        Write-Host ''
        Write-Host '    公网访问地址（任何人可访问，无需同网段）：' -ForegroundColor Green
        Write-Host ("      " + $url) -ForegroundColor Cyan
        Write-Host '    提示：隧道停止后地址失效；快速隧道地址每次启动都会变化。' -ForegroundColor DarkGray
    } else {
        Write-Host '    暂未解析到公网地址，请稍后用「隧道状态」查看，或查看日志：' -ForegroundColor Yellow
        Write-Host ("      " + $script:TunnelLog) -ForegroundColor Yellow
    }
}

function Stop-Tunnel {
    Write-Title '停止 Cloudflare 隧道'
    $p = Get-TunnelPid
    if ($p) {
        taskkill /F /T /PID $p *> $null
        Remove-Item $script:TunnelPidPath -ErrorAction SilentlyContinue
        Write-Host "    [停止] 隧道 PID $p" -ForegroundColor Yellow
    } else {
        Write-Host '    [跳过] 隧道未运行' -ForegroundColor DarkGray
    }
    Read-Return
}

function Show-TunnelStatus {
    Write-Title 'Cloudflare 隧道状态'
    $p = Get-TunnelPid
    if ($p) {
        Write-Host ("    [ UP ] 隧道运行中  PID {0}  目标 {1}" -f $p, (Get-TunnelTarget)) -ForegroundColor Green
        Show-TunnelUrl
    } else {
        Write-Host ('    [DOWN] 隧道未运行（模式 {0}，目标将为 {1}）' -f $script:Mode, (Get-TunnelTarget)) -ForegroundColor DarkGray
    }
    Read-Return
}

# 隧道子菜单：启动 / 停止 / 状态（动作内自带回车，随后回到本子菜单）
function Show-TunnelSubmenu {
    while ($true) {
        Clear-Host
        Write-Host '============================================================' -ForegroundColor Cyan
        Write-Host '            Cloudflare 公网快速隧道' -ForegroundColor Cyan
        Write-Host '============================================================' -ForegroundColor Cyan
        Write-Host ('   当前模式 {0}（隧道目标 {1}）' -f $script:Mode, (Get-TunnelTarget)) -ForegroundColor DarkGray
        Write-Host ''
        Write-Host '    [1] 启动隧道并获取公网地址'
        Write-Host '    [2] 停止隧道'
        Write-Host '    [3] 查看隧道状态 / 公网地址'
        Write-Host '    [0] 返回主菜单'
        Write-Host ''
        $c = Read-Host '请输入选项后回车'
        if ($null -eq $c) { return }   # stdin 关闭（EOF）：返回而非死循环
        switch ($c) {
            '1' { Start-Tunnel }
            '2' { Stop-Tunnel }
            '3' { Show-TunnelStatus }
            '0' { return }
            default { Write-Host '无效选项' -ForegroundColor Red; Start-Sleep -Seconds 1 }
        }
    }
}

function Read-Return {
    Write-Host ''
    Read-Host '回车返回主菜单' | Out-Null
}

# ------------------------------------------------------------
# 主循环（多轮，选 0 才退出）
# ------------------------------------------------------------
function Show-Menu {
    Clear-Host
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '                 健身营养 Agent  -  服务管理' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ('   当前：模式 {0}   网络 {1}' -f $script:Mode, $script:Network) -ForegroundColor DarkGray
    Write-Host ''
    Write-Host '    [1] 启动全部服务'
    Write-Host '    [2] 停止全部服务'
    Write-Host '    [3] 重启全部服务'
    Write-Host '    [4] 查看运行状态'
    Write-Host '    [5] 实时查看日志'
    Write-Host '    [6] 模式 / 网络设置'
    Write-Host '    [7] 公网隧道（Cloudflare）启动/停止/状态'
    Write-Host '    [0] 退出（不会停止已运行的服务）'
    Write-Host ''
}

while ($true) {
    Show-Menu
    $choice = Read-Host '请输入选项后回车'
    if ($null -eq $choice) {
        Write-Host '输入已结束，退出菜单。' -ForegroundColor Cyan
        break
    }
    switch ($choice) {
        '1' { Start-Services }
        '2' { Stop-Services }
        '3' { Restart-Services }
        '4' { Show-Status }
        '5' { Show-Logs }
        '6' { Set-Config }
        '7' { Show-TunnelSubmenu }
        '0' {
            Write-Host '再见。已运行的服务继续在各自窗口中，关闭窗口即停止对应服务。' -ForegroundColor Cyan
            break
        }
        default { Write-Host '无效选项' -ForegroundColor Red; Start-Sleep -Seconds 1 }
    }
    if ($choice -eq '0') { break }
}

"""启动/停止本地 MCP stdio -> Streamable HTTP 桥接（supergateway）。

背景：
    .mcp.json 中配置的 exerciseapi / nutrition-mcp 只支持 stdio，
    而本项目的应用代码（app/mcp/*_client.py）通过 HTTP 调用。
    本脚本为每个 stdio MCP 启动一个常驻 supergateway 桥接进程。

用法：
    uv run python scripts/start_mcp_servers.py up       # 启动全部桥接
    uv run python scripts/start_mcp_servers.py down     # 停止全部桥接
    uv run python scripts/start_mcp_servers.py status   # 查看运行状态
    uv run python scripts/start_mcp_servers.py up exerciseapi   # 只操作单个

端口（从 <NAME>_MCP_URL 环境变量解析，也可直接改下面的默认表）：
    exerciseapi   http://localhost:8010/mcp
    nutrition-mcp http://localhost:8011/mcp
"""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Windows 控制台默认 GBK，打印中文/✓ 会乱码或崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG = PROJECT_ROOT / ".mcp.json"
PID_DIR = PROJECT_ROOT / "data" / "run"
LOG_DIR = PROJECT_ROOT / "logs" / "mcp"

# 服务名 -> 默认 HTTP 端点（可被 <NAME>_MCP_URL 覆盖）
DEFAULT_URLS = {
    "exerciseapi": "http://localhost:8010/mcp",
    "nutrition-mcp": "http://localhost:8011/mcp",
}

# 等待端口就绪的最长时间（npx 冷启动可能要下载包）
READY_TIMEOUT_SECONDS = 90
READY_POLL_INTERVAL = 1.0


# ------------------------------------------------------------
# 配置解析
# ------------------------------------------------------------

def load_servers() -> dict[str, dict[str, Any]]:
    """读取 .mcp.json，返回 {服务名: {"command", "args", "env", "url"}}。"""
    if not MCP_CONFIG.exists():
        sys.exit(f"找不到 {MCP_CONFIG}，请先按 CLAUDE.md 第 7 节创建 MCP 配置")

    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    servers: dict[str, dict[str, Any]] = {}
    for name, server in config.get("mcpServers", {}).items():
        env_var = f"{name.upper().replace('-', '_')}_MCP_URL"
        url = os.getenv(env_var, DEFAULT_URLS.get(name))
        if url is None:
            print(f"[skip] {name}: 未配置 HTTP 端口（设置 {env_var} 或补充 DEFAULT_URLS）")
            continue
        servers[name] = {
            "command": server["command"],
            "args": server.get("args", []),
            "env": server.get("env", {}),
            "url": url,
        }
    return servers


def endpoint_of(server: dict[str, Any]) -> tuple[str, int, str]:
    """从 URL 解析 (host, port, path)。"""
    parsed = urlparse(server["url"])
    if not parsed.hostname or not parsed.port:
        sys.exit(f"非法的 MCP URL：{server['url']}，需包含主机名与端口")
    return parsed.hostname, parsed.port, parsed.path or "/mcp"


# ------------------------------------------------------------
# 进程与端口工具
# ------------------------------------------------------------

def pid_path(name: str) -> Path:
    return PID_DIR / f"{name}.pid"


def log_path(name: str) -> Path:
    return LOG_DIR / f"{name}.log"


def open_log(name: str) -> tuple[Path, Any]:
    """以追加模式打开日志。

    Windows 下若有残留进程仍占用该日志（PermissionError），改用带时间戳的
    备用文件名，避免一个日志锁挡住整条启动链。
    """
    path = log_path(name)
    try:
        return path, path.open("ab")
    except PermissionError:
        alt = path.with_name(
            f"{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}"
        )
        print(f"[warn] {path.name} 被占用，本次改用日志 {alt.name}")
        return alt, alt.open("ab")


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return sys.platform != "win32"  # Windows 下 os.kill(pid, 0) 不可靠，见 _read_pid 调用方


def _read_pid(name: str) -> int | None:
    path = pid_path(name)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="ascii").strip())
    except ValueError:
        return None


def _process_exists(pid: int) -> bool:
    """跨平台判断进程是否存在（Windows 用 tasklist 查询）。"""
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    return is_pid_alive(pid)


def _pid_listening_on(port: int) -> int | None:
    """通过 netstat -ano 找到在指定端口 LISTENING 的进程 PID。"""
    try:
        output = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return None
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[3] == "LISTENING":
            try:
                local_port = int(fields[1].rsplit(":", 1)[1])
                pid = int(fields[4])
            except ValueError:
                continue
            if local_port == port:
                return pid
    return None


def _kill_process_tree(pid: int) -> bool:
    """结束进程树：Windows 用 taskkill /T /F；POSIX 用 killpg。"""
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    return True


def wait_until_ready(host: str, port: int) -> bool:
    """轮询直到端口可连接或超时。"""
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(READY_POLL_INTERVAL)
    return False


# ------------------------------------------------------------
# up / down / status
# ------------------------------------------------------------

def start_server(name: str, server: dict[str, Any]) -> bool:
    """启动单个桥接；已在运行则跳过。成功返回 True。"""
    host, port, http_path = endpoint_of(server)

    existing_pid = _read_pid(name)
    if existing_pid and _process_exists(existing_pid):
        print(f"[skip] {name}: 已在运行（PID {existing_pid}，端口 {port}）")
        return True
    if is_port_open(host, port):
        print(f"[skip] {name}: 端口 {port} 已被占用（可能由其他方式启动）")
        return True

    if shutil.which(server["command"]) is None:
        print(f"[fail] {name}: 找不到命令 {server['command']!r}，请先安装 Node.js/npm")
        return False

    # Windows 上 npx 实际是 npx.cmd，CreateProcess 不会自动补扩展名，
    # 必须用 shutil.which 解析出的完整路径。
    npx_exe = shutil.which("npx")
    if npx_exe is None:
        print("[fail] 找不到 npx，请先安装 Node.js")
        return False

    # 内层 stdio 命令以字符串交给 supergateway（它通过系统 shell 启动）
    stdio_cmd = " ".join([server["command"], *server["args"]])
    cmd = [
        npx_exe,
        "-y",
        "supergateway",
        "--stdio",
        stdio_cmd,
        "--outputTransport",
        "streamableHttp",
        "--port",
        str(port),
        "--streamableHttpPath",
        http_path,
        "--logLevel",
        "info",
    ]

    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_actual, log_file = open_log(name)

    popen_kwargs: dict[str, Any] = {
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "env": {**os.environ, **server["env"]},
        "cwd": PROJECT_ROOT,
    }
    if sys.platform == "win32":
        # 独立进程组，脱离当前控制台；终止时用 taskkill /T 杀整棵进程树
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    print(f"[start] {name}: {server['url']} （日志 {log_actual.relative_to(PROJECT_ROOT)}）")
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603 - 命令来自受信任的 .mcp.json
    finally:
        # 子进程已继承句柄，父进程关闭自己的副本
        log_file.close()
    pid_path(name).write_text(str(proc.pid), encoding="ascii")

    if wait_until_ready(host, port):
        print(f"[ok] {name}: 桥接就绪（PID {proc.pid}）")
        return True

    print(f"[fail] {name}: 等待端口 {port} 就绪超时，请查看日志 {log_path(name)}")
    return False


def stop_server(name: str, server: dict[str, Any]) -> bool:
    """停止单个桥接（杀进程树）。"""
    host, port, _ = endpoint_of(server)

    pid = _read_pid(name)
    if pid is None:
        # 无 PID 文件（如桥接由其他方式启动、或上次会话遗留的孤儿进程）：
        # 直接按端口反查监听进程并结束
        orphan_pid = _pid_listening_on(port)
        if orphan_pid is not None:
            _kill_process_tree(orphan_pid)
            print(f"[ok] {name}: 已停止端口 {port} 上的进程（PID {orphan_pid}）")
        else:
            print(f"[skip] {name}: 未在运行")
        return True

    # /T 连同 supergateway 派生的 npx -> node 子进程一并终止
    ok = _kill_process_tree(pid)

    pid_path(name).unlink(missing_ok=True)
    print(f"[{'ok' if ok else 'fail'}] {name}: 已停止（PID {pid}）")
    return ok


def show_status(servers: dict[str, dict[str, Any]]) -> None:
    print(f"{'服务':16}{'端口':8}{'PID':10}状态")
    print("-" * 52)
    all_ok = True
    for name, server in servers.items():
        host, port, _ = endpoint_of(server)
        pid = _read_pid(name)
        pid_alive = pid is not None and _process_exists(pid)
        port_open = is_port_open(host, port)
        running = pid_alive and port_open
        all_ok &= running
        state = "运行中" if running else "已停止"
        print(f"{name:16}{port:<8}{(str(pid) if pid else '-'):<10}{state}")
    print("-" * 52)
    print("全部运行中 ✓" if all_ok else "有服务未运行，执行: uv run python scripts/start_mcp_servers.py up")


def main() -> None:
    parser = argparse.ArgumentParser(description="管理本地 MCP HTTP 桥接")
    parser.add_argument("action", choices=["up", "down", "status"])
    parser.add_argument("names", nargs="*", help="可选：只操作指定服务")
    args = parser.parse_args()

    servers = load_servers()
    targets = args.names or list(servers)

    unknown = [name for name in targets if name not in servers]
    if unknown:
        sys.exit(f"未知服务：{unknown}；可用：{list(servers)}")

    if args.action == "up":
        results = [start_server(name, servers[name]) for name in targets]
        if not all(results):
            raise SystemExit(1)
    elif args.action == "down":
        for name in targets:
            stop_server(name, servers[name])
    else:
        show_status({name: servers[name] for name in targets})


if __name__ == "__main__":
    main()

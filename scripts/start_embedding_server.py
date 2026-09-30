"""启动/停止/检查本地 llama-server 嵌入服务（Ollama 自带运行器旁路）。

背景：
    当前安装的 Ollama（0.34.4）存在版本错配，/api/embed 始终返回 501。
    本脚本绕过 Ollama 路由，直接用其自带的 llama-server 加载本地
    Qwen3-Embedding-8B GGUF，提供 OpenAI 兼容的 /v1/embeddings：

        llama-server -m <gguf blob> --embedding --pooling cls
                     --port 8001 -ngl 99 -c 8192

    GGUF 路径从 Ollama 的模型 manifest 自动解析（取 model 层），
    无需在脚本中写死 blob 文件名。

用法：
    uv run python scripts/start_embedding_server.py up
    uv run python scripts/start_embedding_server.py down
    uv run python scripts/start_embedding_server.py status

可用环境变量：
    OLLAMA_MODELS          Ollama 模型目录（默认 ~/.ollama/models）
    EMBED_MODEL_REF        Ollama 模型引用，默认 dengcao/Qwen3-Embedding-8B:Q5_K_M
    EMBED_SERVER_PORT      端口（默认 8001）
    EMBED_SERVER_HOST      主机（默认 127.0.0.1）
    EMBED_CTX              上下文长度（默认 8192）
    EMBED_BACKEND          vulkan（默认）| cuda_v12 | cuda_v13 | cpu
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Windows 控制台默认 GBK
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PID_DIR = PROJECT_ROOT / "data" / "run"
LOG_DIR = PROJECT_ROOT / "logs"
PID_FILE = PID_DIR / "embedding_server.pid"

OLLAMA_MODELS_DIR = Path(
    os.getenv("OLLAMA_MODELS", str(Path.home() / ".ollama" / "models"))
)
MODEL_REF = os.getenv("EMBED_MODEL_REF", "dengcao/Qwen3-Embedding-8B:Q5_K_M")

HOST = os.getenv("EMBED_SERVER_HOST", "127.0.0.1")
PORT = int(os.getenv("EMBED_SERVER_PORT", "8001"))
CTX_LEN = int(os.getenv("EMBED_CTX", "8192"))
# Ollama 当前配置实际使用 Vulkan 后端，故默认 vulkan
BACKEND = os.getenv("EMBED_BACKEND", "vulkan")

READY_TIMEOUT_SECONDS = 90


# ------------------------------------------------------------
# 路径解析
# ------------------------------------------------------------

def find_ollama_root() -> Path | None:
    """定位 Ollama 安装目录（含 lib/ollama/llama-server）。"""
    explicit = os.getenv("OLLAMA_INSTALL_DIR")
    candidates = [
        Path(explicit) if explicit else None,
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama",
        Path.home() / "AppData" / "Local" / "Programs" / "Ollama",
    ]
    for candidate in candidates:
        if candidate and (candidate / "lib" / "ollama" / "llama-server.exe").exists():
            return candidate
        if candidate and (candidate / "lib" / "ollama" / "llama-server").exists():
            return candidate
    return None


def resolve_gguf_path() -> Path:
    """从 Ollama manifest 解析模型的 GGUF blob 路径。

    manifest 位于 manifests/registry.ollama.ai/<ref 中 / 前的部分>，
    也兼容直接在 manifests/<...> 下的情况；model 层的 digest 即 blob 文件名。
    """
    ref = MODEL_REF
    manifest_paths = [
        OLLAMA_MODELS_DIR / "manifests" / "registry.ollama.ai" / Path(ref.replace(":", "/")),
        OLLAMA_MODELS_DIR / "manifests" / Path(ref.replace(":", "/")),
    ]

    manifest_file = next((p for p in manifest_paths if p.exists()), None)
    if manifest_file is None:
        sys.exit(
            f"找不到模型 {MODEL_REF} 的 manifest（查找过："
            f"{[str(p) for p in manifest_paths]}）。请先 ollama pull 该模型。"
        )

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    model_digest = next(
        (
            layer["digest"]
            for layer in manifest.get("layers", [])
            if layer.get("mediaType", "").endswith(".model")
        ),
        None,
    )
    if model_digest is None:
        sys.exit(f"manifest 中未找到 model 层：{manifest_file}")

    blob = OLLAMA_MODELS_DIR / "blobs" / model_digest.replace(":", "-")
    if not blob.exists():
        sys.exit(f"manifest 指向的 blob 不存在：{blob}")
    return blob


def runner_paths(install_dir: Path) -> tuple[Path, str | None]:
    """返回 (llama-server 路径, 需加入 PATH 的后端 DLL 目录或 None)。"""
    lib_dir = install_dir / "lib" / "ollama"
    server = lib_dir / ("llama-server.exe" if sys.platform == "win32" else "llama-server")

    dll_dir: Path | None = None
    if BACKEND != "cpu":
        candidate = lib_dir / BACKEND
        if candidate.is_dir():
            dll_dir = candidate
    return server, str(dll_dir) if dll_dir else None


# ------------------------------------------------------------
# 进程与端口
# ------------------------------------------------------------

def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="ascii").strip())
    except ValueError:
        return None


def _process_exists(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_listening_on(host: str, port: int) -> int | None:
    """按端口反查监听 PID（netstat -ano，Windows）。"""
    if sys.platform != "win32":
        return None
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
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    import signal

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    return True


def is_server_healthy() -> bool:
    """llama-server /health：加载中返回 503，就绪返回 200。

    只探测 TCP 端口会在模型尚未加载完时误判就绪（首个嵌入请求会失败）。
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://{HOST}:{PORT}/health", timeout=2
        ) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False  # 503 = 仍在加载
    except (urllib.error.URLError, OSError):
        return False


def wait_until_ready() -> bool:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if is_server_healthy():
            return True
        time.sleep(1.0)
    return False


# ------------------------------------------------------------
# up / down / status
# ------------------------------------------------------------

def open_embedding_log() -> tuple[Path, Any]:
    """以追加模式打开嵌入服务日志。

    Windows 下若有残留进程占用该日志（PermissionError），改用带时间戳的备用
    文件名，避免日志锁挡住服务启动。
    """
    path = LOG_DIR / "embedding_server.log"
    try:
        return path, path.open("ab")
    except PermissionError:
        alt = path.with_name(
            f"{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}"
        )
        print(f"[warn] {path.name} 被占用，本次改用日志 {alt.name}")
        return alt, alt.open("ab")


def up() -> bool:
    pid = _read_pid()
    if pid and _process_exists(pid):
        print(f"[skip] 嵌入服务已在运行（PID {pid}，端口 {PORT}）")
        return True
    if is_port_open(HOST, PORT):
        print(f"[skip] 端口 {PORT} 已被占用（可能由其他方式启动）")
        return True

    install_dir = find_ollama_root()
    if install_dir is None:
        print("[fail] 找不到 Ollama 安装目录（可用 OLLAMA_INSTALL_DIR 指定）")
        return False

    server, dll_dir = runner_paths(install_dir)
    gguf = resolve_gguf_path()

    env = dict(os.environ)
    if dll_dir:
        # 后端 DLL 放在 PATH 最前，让 llama-server 加载 ggml-vulkan/cuda
        env["PATH"] = dll_dir + os.pathsep + env.get("PATH", "")

    argv = [
        str(server),
        "-m",
        str(gguf),
        "--embedding",
        "--pooling",
        "cls",
        "--port",
        str(PORT),
        "--host",
        HOST,
        "-c",
        str(CTX_LEN),
        "-ngl",
        "99",
    ]

    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file, log_handle = open_embedding_log()

    popen_kwargs: dict[str, Any] = {
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    print(f"[start] llama-server（后端 {BACKEND}）-> http://{HOST}:{PORT}/v1")
    print(f"        模型 {MODEL_REF}，日志 {log_file.relative_to(PROJECT_ROOT)}")
    proc = subprocess.Popen(argv, **popen_kwargs)  # noqa: S603 - argv 受控
    log_handle.close()  # 子进程已继承句柄，关闭父进程副本
    PID_FILE.write_text(str(proc.pid), encoding="ascii")

    if wait_until_ready():
        print(f"[ok] 嵌入服务就绪（PID {proc.pid}，4096 维）")
        return True

    print(f"[fail] 等待端口 {PORT} 就绪超时，请查看日志 {log_file}")
    return False


def down() -> None:
    pid = _read_pid()
    if pid is None:
        orphan = _pid_listening_on(HOST, PORT)
        if orphan is not None:
            _kill_process_tree(orphan)
            print(f"[ok] 已停止端口 {PORT} 上的进程（PID {orphan}）")
        else:
            print("[skip] 嵌入服务未在运行")
        return

    _kill_process_tree(pid)
    # taskkill /T 杀树时若某子进程已退出会返回非零，
    # 但目标进程可能确实已终止 —— 以死后状态为准。
    time.sleep(0.5)
    ok = not _process_exists(pid) and not is_port_open(HOST, PORT)
    PID_FILE.unlink(missing_ok=True)
    print(f"[{'ok' if ok else 'fail'}] 嵌入服务已停止（PID {pid}）")


def status_cmd() -> None:
    pid = _read_pid()
    pid_alive = pid is not None and _process_exists(pid)
    port_open = is_port_open(HOST, PORT)
    running = pid_alive and port_open

    print(f"嵌入服务 http://{HOST}:{PORT}/v1 : "
          f"{'RUNNING ✓' if running else 'DOWN ✗'}"
          f"{f' (PID {pid})' if pid_alive else ''}")
    if not running:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="本地 llama-server 嵌入服务管理")
    parser.add_argument("action", choices=["up", "down", "status"])
    args = parser.parse_args()

    if args.action == "up":
        if not up():
            raise SystemExit(1)
    elif args.action == "down":
        down()
    else:
        status_cmd()


if __name__ == "__main__":
    main()

"""检查嵌入服务连通性：Ollama 直连或 llama-server 旁路（二选一）。

模式由环境变量决定：
    EMBED_PROVIDER != "openai"（默认）
        检查 OLLAMA_BASE_URL（默认 http://localhost:11434）：
          1. GET  /api/tags  确认服务在线、嵌入模型已下载；
          2. POST /api/embed  实际生成一次向量，确认维度 > 0。
    EMBED_PROVIDER == "openai"（Ollama 501 时的 llama-server 旁路）
        检查 http://127.0.0.1:8001：
          1. GET  /health；
          2. POST /v1/embeddings（OpenAI 兼容）。

用法：
    uv run python scripts/check_ollama.py
退出码：0 全部通过，1 检查失败。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_dotenv  # noqa: E402

load_dotenv()

# Windows 控制台默认 GBK
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OPENAI_EMBED_URL = "http://127.0.0.1:8001"
DEFAULT_EMBED_MODEL = "dengcao/Qwen3-Embedding-8B:Q5_K_M"
TEST_TEXT = "健身营养 Agent 连通性测试"


def check_ollama_embed(
    base_url: str | None = None,
    model: str | None = None,
    *,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """检查 Ollama：模型存在且 /api/embed 能返回非空向量。"""
    base_url = (base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)).rstrip("/")
    model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_EMBED_MODEL)

    # 1. /api/tags 确认服务在线且模型已下载
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, f"无法连接 Ollama（{base_url}）：{exc}。请先启动 ollama serve。"

    installed = [item.get("name", "") for item in tags.get("models", [])]
    if not any(name.startswith(model) or name == model for name in installed):
        return False, (
            f"Ollama 在线，但未找到模型 {model}（已安装：{', '.join(installed) or '无'}）。"
            f"请执行 ollama pull {model}"
        )

    # 2. /api/embed 实际生成向量
    payload = json.dumps({"model": model, "input": TEST_TEXT}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/embed", data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout * 3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return False, f"/api/embed 返回 {exc.code}：{detail}"
    except Exception as exc:
        return False, f"/api/embed 调用失败：{exc}"

    embeddings = data.get("embeddings") or []
    dim = len(embeddings[0]) if embeddings and embeddings[0] else 0
    if dim == 0:
        return False, "/api/embed 未返回向量"
    return True, f"Ollama 嵌入正常：{model}，向量维度 {dim}"


def check_openai_embed(
    base_url: str | None = None,
    model: str | None = None,
    *,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """检查 llama-server 旁路：/health 在线且 /v1/embeddings 返回非空向量。"""
    base_url = (base_url or os.getenv("EMBED_BASE_URL", DEFAULT_OPENAI_EMBED_URL)).rstrip("/")
    model = model or os.getenv("EMBED_MODEL_NAME", "qwen3-embedding")

    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=timeout) as resp:
            if resp.status != 200:
                return False, f"/health 返回 {resp.status}"
    except Exception as exc:
        return False, f"无法连接嵌入旁路（{base_url}）：{exc}。请先执行 make embed-up。"

    payload = json.dumps(
        {"model": model, "input": TEST_TEXT, "encoding_format": "float"}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/v1/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout * 3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, f"/v1/embeddings 调用失败：{exc}"

    items = data.get("data") or []
    dim = len(items[0]["embedding"]) if items and items[0].get("embedding") else 0
    if dim == 0:
        return False, "/v1/embeddings 未返回向量"
    return True, f"嵌入旁路正常：{model}，向量维度 {dim}"


def main() -> None:
    if os.getenv("EMBED_PROVIDER", "").lower() == "openai":
        ok, message = check_openai_embed()
    else:
        ok, message = check_ollama_embed()
    print(("✓ " if ok else "✗ ") + message)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

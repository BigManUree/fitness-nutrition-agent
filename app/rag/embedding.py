"""嵌入服务封装。

两种后端，通过 EMBED_PROVIDER 环境变量切换：
    ollama（默认）  对接本地 Ollama（要求服务支持 /api/embed）
    openai          对接任意 OpenAI 兼容 /v1/embeddings 端点，
                    如 Ollama 自带 llama-server --embedding 的旁路服务
                    （EMBEDDING_BASE_URL，默认 http://127.0.0.1:8001/v1）。

配置项与 CLAUDE.md 第 10 节一致；openai 旁路为环境修复期的过渡方案。
"""

import os
import sys
from pathlib import Path

# Streamlit / 脚本入口未必先经过 app.config，这里主动加载 .env，
# 否则 EMBED_PROVIDER 等变量缺失会静默退回默认 ollama。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import load_dotenv  # noqa: E402

load_dotenv()

from chromadb.utils.embedding_functions.ollama_embedding_function import (  # noqa: E402
    OllamaEmbeddingFunction,
)
from chromadb.utils.embedding_functions.openai_embedding_function import (  # noqa: E402
    OpenAIEmbeddingFunction,
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv(
    "OLLAMA_EMBEDDING_MODEL", "dengcao/Qwen3-Embedding-8B:Q5_K_M"
)

# 旁路 OpenAI 兼容服务
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://127.0.0.1:8001/v1")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "qwen3-embedding")

PROVIDER = os.getenv("EMBED_PROVIDER", "ollama").lower()

# OpenAI SDK（httpx）默认会读取 HTTP(S)_PROXY，系统开着 Clash 时
# 访问 127.0.0.1 的请求也会被代理截走并返回 502。强制本地地址绕过。
_existing_no_proxy = os.getenv("NO_PROXY", "")
for _host in ("localhost", "127.0.0.1"):
    if _host not in _existing_no_proxy:
        _existing_no_proxy = f"{_existing_no_proxy},{_host}".strip(",")
os.environ["NO_PROXY"] = _existing_no_proxy
os.environ["no_proxy"] = _existing_no_proxy


def get_embedding_function():
    """返回 Chroma 嵌入函数，具体后端由 EMBED_PROVIDER 决定。

    Raises:
        ValueError: EMBED_PROVIDER 不是受支持的值。
    """
    if PROVIDER == "ollama":
        return OllamaEmbeddingFunction(
            url=OLLAMA_BASE_URL,
            model_name=OLLAMA_EMBEDDING_MODEL,
        )
    if PROVIDER == "openai":
        # llama-server 不校验 key 与 model 名，给占位值即可
        return OpenAIEmbeddingFunction(
            api_key="not-needed",
            api_base=EMBEDDING_BASE_URL,
            model_name=EMBEDDING_MODEL_NAME,
        )
    raise ValueError(
        f"不支持的 EMBED_PROVIDER={PROVIDER!r}，可选：ollama、openai"
    )

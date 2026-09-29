"""应用配置：从 .env / 环境变量读取，不提供任何硬编码密钥。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """极简 .env 加载器：不覆盖已存在的环境变量。"""
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    local_llm_base_url: str
    local_llm_model: str

    @property
    def use_cloud_llm(self) -> bool:
        return bool(self.llm_api_key) and self.llm_api_key != "your_api_key"


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        # 主模型：DeepSeek（OpenAI 兼容）
        llm_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        llm_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        # 本地兜底聊天模型（Ollama OpenAI 兼容端点）
        local_llm_base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"),
        local_llm_model=os.getenv("LOCAL_LLM_MODEL", "qwen3.5:2b"),
    )

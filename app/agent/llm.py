"""聊天模型工厂：优先 DeepSeek，缺 Key 时降级本地 Ollama。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import get_settings


def get_llm(*, json_mode: bool = True, temperature: float = 0.3) -> ChatOpenAI:
    """返回 OpenAI 兼容 ChatOpenAI 客户端。

    DeepSeek 与 Ollama 的 /v1 均兼容 OpenAI Chat Completions，
    因此同一客户端类切换 base_url / api_key 即可。
    """
    settings = get_settings()
    if settings.use_cloud_llm:
        kwargs = {
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
        }
    else:
        kwargs = {
            "model": settings.local_llm_model,
            "api_key": "not-needed",
            "base_url": settings.local_llm_base_url,
        }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(temperature=temperature, timeout=60, **kwargs)

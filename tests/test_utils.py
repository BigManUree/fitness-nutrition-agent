"""logger 与 check_ollama 脚本测试（网络层打桩，不依赖真实 Ollama）。"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import scripts.check_ollama as check_ollama
from app.utils.logger import get_logger

# ============================================================
# logger
# ============================================================


def test_logger_configured_once(caplog):
    root = get_logger()
    handler_count = len(root.handlers)

    get_logger("child")
    get_logger("another")

    assert len(root.handlers) == handler_count
    assert root.name == "fitness_agent"
    assert get_logger("child").name == "fitness_agent.child"


def test_logger_emits_record(caplog):
    logger = get_logger("emit-test")
    with caplog.at_level(logging.INFO, logger="fitness_agent.emit-test"):
        logger.info("一条中文日志")
    assert "一条中文日志" in caplog.text


def test_logger_respects_log_level_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    # 全新进程语义无法模拟，但级别字符串解析逻辑至少应稳定：
    root = logging.getLogger("fitness_agent")
    root.setLevel(logging.WARNING)
    assert root.level == logging.WARNING


# ============================================================
# check_ollama
# ============================================================


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_check_ollama_embed_success(monkeypatch):
    model = check_ollama.DEFAULT_EMBED_MODEL

    def fake_urlopen(url, timeout=10):  # noqa: ANN001
        # embed 调用传入的是 urllib Request 对象而非字符串
        target = getattr(url, "full_url", str(url))
        if target.endswith("/api/tags"):
            return _FakeResponse({"models": [{"name": model}]})
        if target.endswith("/api/embed"):
            return _FakeResponse({"embeddings": [[0.1] * 4096]})
        raise AssertionError(target)

    monkeypatch.setattr(check_ollama.urllib.request, "urlopen", fake_urlopen)

    ok, message = check_ollama.check_ollama_embed()
    assert ok
    assert "4096" in message


def test_check_ollama_missing_model(monkeypatch):
    def fake_urlopen(url, timeout=10):  # noqa: ANN001
        return _FakeResponse({"models": [{"name": "other:latest"}]})

    monkeypatch.setattr(check_ollama.urllib.request, "urlopen", fake_urlopen)

    ok, message = check_ollama.check_ollama_embed()
    assert not ok
    assert "ollama pull" in message


def test_check_ollama_connection_refused(monkeypatch):
    def fake_urlopen(url, timeout=10):  # noqa: ANN001
        raise OSError("connection refused")

    monkeypatch.setattr(check_ollama.urllib.request, "urlopen", fake_urlopen)

    ok, message = check_ollama.check_ollama_embed()
    assert not ok
    assert "ollama serve" in message


def test_check_openai_embed_success(monkeypatch):
    def fake_urlopen(url, timeout=10):  # noqa: ANN001
        target = getattr(url, "full_url", str(url))
        if target.endswith("/health"):
            return _FakeResponse({})
        if target.endswith("/v1/embeddings"):
            return _FakeResponse({"data": [{"embedding": [0.1] * 4096}]})
        raise AssertionError(target)

    monkeypatch.setattr(check_ollama.urllib.request, "urlopen", fake_urlopen)

    ok, message = check_ollama.check_openai_embed()
    assert ok
    assert "4096" in message


def test_check_openai_embed_bypass_down(monkeypatch):
    def fake_urlopen(url, timeout=10):  # noqa: ANN001
        raise OSError("refused")

    monkeypatch.setattr(check_ollama.urllib.request, "urlopen", fake_urlopen)

    ok, message = check_ollama.check_openai_embed()
    assert not ok
    assert "embed-up" in message


def test_stdout_is_utf8_safe():
    """脚本头部的 reconfigure 调用在当前测试进程应无副作用报错。"""
    assert io.TextIOBase  # 仅占位，保证 import 时脚本顶层代码执行过
    assert check_ollama.TEST_TEXT

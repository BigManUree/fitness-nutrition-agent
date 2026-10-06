"""聊天 SSE 端点测试（注入 fake stream，不依赖 LLM / MCP）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "dave"
PASSWORD = "secret123"

PROFILE = {
    "sex": "male",
    "age": 30,
    "height_cm": 175.0,
    "weight_kg": 72.0,
    "goal": "muscle_gain",
    "days_per_week": 4,
    "equipment": ["barbell"],
    "dietary_preferences": [],
    "allergies": [],
}

PLAN = {"weekly_plan": [], "daily_meals": {}, "rationale": "x"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_chat.db"))
    # 画像保存会触发向量入库：mock Chroma 边界，避免测试依赖 Ollama/污染开发数据
    monkeypatch.setattr("app.rag.profile_indexer.index_profile", lambda *a, **k: None)
    c = TestClient(api_main.app)
    c.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD})
    c.put("/api/profile", json=PROFILE)
    return c


def test_persist_latest_plan_then_get_reads_it_back(client):
    updated = {"weekly_plan": [{"day": 1}], "daily_meals": {}, "rationale": "调整后"}
    resp = client.put("/api/plans/latest", json={"plan": updated})
    assert resp.status_code == 200
    assert resp.json()["plan"]["weekly_plan"] == [{"day": 1}]

    got = client.get("/api/plans/latest")
    assert got.status_code == 200
    assert got.json()["plan"]["weekly_plan"] == [{"day": 1}]


def test_persist_latest_plan_rejects_empty_plan(client):
    resp = client.put("/api/plans/latest", json={"plan": {}})
    assert resp.status_code == 400


def test_chat_without_profile_400(client):
    bare = TestClient(api_main.app)
    bare.post("/api/auth/register", json={"username": "eve", "password": "secret123"})
    resp = bare.post(
        "/api/plans/chat", json={"plan": PLAN, "messages": [], "message": "hi"}
    )
    assert resp.status_code == 400


def test_chat_guard_reply_streams(client, monkeypatch):
    def should_not_run(*a, **k):
        raise AssertionError("命中安全守卫时不应调 stream_with_tools")

    monkeypatch.setattr(api_main, "stream_with_tools", should_not_run)
    resp = client.post(
        "/api/plans/chat",
        json={"plan": PLAN, "messages": [], "message": "我胸痛还能继续练吗"},
    )
    assert resp.status_code == 200
    text = resp.text
    assert "event: token" in text
    assert "建议你暂停训练" in text
    assert "event: done" in text


def test_chat_streams_tokens_and_tool_results(client, monkeypatch):
    def fake_stream(llm, messages, profile, tool_results=None):
        yield "候选："
        yield "Dumbbell Press"
        if tool_results is not None:
            tool_results.append(
                {
                    "original_exercise": "卧推",
                    "alternatives": [{"name": "Dumbbell Press"}],
                    "total": 1,
                    "source": "mcp",
                }
            )

    monkeypatch.setattr(api_main, "stream_with_tools", fake_stream)
    monkeypatch.setattr(api_main, "get_llm", lambda **kw: object())
    resp = client.post(
        "/api/plans/chat",
        json={"plan": PLAN, "messages": [], "message": "把卧推换成哑铃"},
    )
    text = resp.text
    assert "Dumbbell Press" in text
    assert '"tool_results"' in text
    assert '"alternatives"' in text


def test_chat_error_emits_error_event(client, monkeypatch):
    def boom(llm, messages, profile, tool_results=None):
        yield "开始"
        raise RuntimeError("llm 挂了")

    monkeypatch.setattr(api_main, "stream_with_tools", boom)
    monkeypatch.setattr(api_main, "get_llm", lambda **kw: object())
    resp = client.post(
        "/api/plans/chat",
        json={"plan": PLAN, "messages": [], "message": "你好"},
    )
    assert "event: error" in resp.text

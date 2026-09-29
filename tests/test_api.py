"""FastAPI 接口测试。

通过 monkeypatch 替换 run_agent，使测试不依赖 MCP / LLM；
SQLITE_DB_PATH 指向临时库，不碰开发数据。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

SAMPLE_PROFILE = {
    "sex": "male",
    "age": 30,
    "height_cm": 175.0,
    "weight_kg": 72.0,
    "goal": "muscle_gain",
    "days_per_week": 4,
    "equipment": ["barbell", "dumbbell"],
    "dietary_preferences": [],
    "allergies": [],
}

FAKE_PLAN = {
    "weekly_plan": [
        {
            "day": 1,
            "focus": "胸+三头",
            "exercises": [
                {"name": "Barbell Bench Press", "sets": 4, "reps": "8-10",
                 "rest": "90秒", "note": ""}
            ],
        }
    ],
    "daily_meals": {
        "breakfast": [{"food": "鸡蛋", "amount": "2个", "note": ""}],
        "lunch": [{"food": "鸡胸肉", "amount": "150g", "note": ""}],
        "dinner": [{"food": "三文鱼", "amount": "120g", "note": ""}],
    },
    "rationale": "测试理由",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_api.db"))
    return TestClient(api_main.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_profile_save_get_roundtrip(client):
    resp = client.put("/api/profiles/user-001", json=SAMPLE_PROFILE)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    resp = client.get("/api/profiles/user-001")
    assert resp.status_code == 200
    assert resp.json()["profile"]["age"] == 30


def test_get_missing_profile_404(client):
    assert client.get("/api/profiles/nobody").status_code == 404
    assert client.get("/api/profiles").status_code == 404


def test_get_latest_profile(client):
    client.put("/api/profiles/user-a", json=SAMPLE_PROFILE)
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user-a"


def test_invalid_profile_rejected(client):
    bad = {**SAMPLE_PROFILE, "age": 200}
    resp = client.put("/api/profiles/user-bad", json=bad)
    assert resp.status_code == 422


def test_generate_plan_with_profile_in_body(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {
            "user_id": user_id,
            "plan": FAKE_PLAN,
            "validation": {"valid": True, "violations": []},
            "errors": [],
        }

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post(
        "/api/plans/generate",
        json={"user_id": "user-001", "profile": SAMPLE_PROFILE},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["rationale"] == "测试理由"
    assert body["validation"]["valid"] is True


def test_generate_plan_uses_stored_profile(client, monkeypatch):
    client.put("/api/profiles/user-001", json=SAMPLE_PROFILE)

    captured = {}

    async def fake_run_agent(user_id, profile):
        captured["profile"] = profile
        return {"plan": FAKE_PLAN, "validation": {"valid": True}, "errors": []}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={"user_id": "user-001"})
    assert resp.status_code == 200
    assert captured["profile"]["goal"] == "muscle_gain"


def test_generate_plan_without_profile_400(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        raise AssertionError("不应执行 Agent")

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={"user_id": "ghost"})
    assert resp.status_code == 400


def test_generate_plan_missing_fields_422(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {"missing_fields": ["equipment", "goal"], "plan": {}}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post(
        "/api/plans/generate",
        json={"user_id": "user-001", "profile": SAMPLE_PROFILE},
    )
    assert resp.status_code == 422
    assert "equipment" in resp.json()["detail"]["missing_fields"]


def test_generate_plan_empty_plan_502(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {"plan": {}, "errors": ["MCP 超时"]}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post(
        "/api/plans/generate",
        json={"user_id": "user-001", "profile": SAMPLE_PROFILE},
    )
    assert resp.status_code == 502
    assert "MCP 超时" in resp.json()["detail"]["errors"]


def test_generate_plan_agent_crash_502(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post(
        "/api/plans/generate",
        json={"user_id": "user-001", "profile": SAMPLE_PROFILE},
    )
    assert resp.status_code == 502
    assert "boom" in resp.json()["detail"]


def test_persist_false_skips_storage(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {"plan": FAKE_PLAN, "validation": {"valid": True}, "errors": []}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post(
        "/api/plans/generate",
        json={"user_id": "user-001", "profile": SAMPLE_PROFILE, "persist": False},
    )
    assert resp.status_code == 200

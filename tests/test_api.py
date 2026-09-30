"""FastAPI 接口测试（多账号 + Bearer 会话）。

通过 monkeypatch 替换 run_agent，使测试不依赖 MCP / LLM；
SQLITE_DB_PATH 指向临时库，不碰开发数据。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "alice"
PASSWORD = "secret123"

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
    base = TestClient(api_main.app)
    # 注册并取会话 token；后续请求以该账号身份
    resp = base.post(
        "/api/auth/register", json={"username": USERNAME, "password": PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    base.headers["Authorization"] = f"Bearer {token}"
    return base


# ------------------------------------------------------------
# 健康检查与鉴权
# ------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_route_without_token_401(client):
    bare = TestClient(api_main.app)
    assert bare.get("/api/me").status_code == 401
    assert bare.get("/api/profile").status_code == 401


def test_me_returns_current_user(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == USERNAME


def test_register_duplicate_409(client):
    bare = TestClient(api_main.app)
    resp = bare.post(
        "/api/auth/register", json={"username": USERNAME, "password": PASSWORD}
    )
    assert resp.status_code == 409


def test_register_weak_credentials_400(client):
    bare = TestClient(api_main.app)
    resp = bare.post("/api/auth/register", json={"username": "ab", "password": PASSWORD})
    assert resp.status_code == 400
    resp = bare.post("/api/auth/register", json={"username": "charlie", "password": "12"})
    assert resp.status_code == 400


def test_login_wrong_password_401(client):
    bare = TestClient(api_main.app)
    resp = bare.post(
        "/api/auth/login", json={"username": USERNAME, "password": "wrongpass"}
    )
    assert resp.status_code == 401


def test_logout_revokes_token(client):
    assert client.post("/api/auth/logout").status_code == 200
    # token 已吊销，后续请求 401
    assert client.get("/api/me").status_code == 401


# ------------------------------------------------------------
# 画像
# ------------------------------------------------------------

def test_profile_save_get_roundtrip(client):
    resp = client.put("/api/profile", json=SAMPLE_PROFILE)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    resp = client.get("/api/profile")
    assert resp.status_code == 200
    assert resp.json()["profile"]["age"] == 30


def test_get_missing_profile_404(client):
    assert client.get("/api/profile").status_code == 404


def test_invalid_profile_rejected(client):
    bad = {**SAMPLE_PROFILE, "age": 200}
    assert client.put("/api/profile", json=bad).status_code == 422


# ------------------------------------------------------------
# 计划生成
# ------------------------------------------------------------

def test_generate_plan_with_profile_in_body(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        assert user_id == USERNAME
        return {
            "user_id": user_id,
            "plan": FAKE_PLAN,
            "validation": {"valid": True, "violations": []},
            "errors": [],
        }

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={"profile": SAMPLE_PROFILE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == USERNAME
    assert body["plan"]["rationale"] == "测试理由"
    assert body["validation"]["valid"] is True


def test_generate_plan_uses_stored_profile(client, monkeypatch):
    client.put("/api/profile", json=SAMPLE_PROFILE)

    captured = {}

    async def fake_run_agent(user_id, profile):
        captured["profile"] = profile
        return {"plan": FAKE_PLAN, "validation": {"valid": True}, "errors": []}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={})
    assert resp.status_code == 200
    assert captured["profile"]["goal"] == "muscle_gain"


def test_generate_plan_without_profile_400(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        raise AssertionError("不应执行 Agent")

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    assert client.post("/api/plans/generate", json={}).status_code == 400


def test_generate_plan_missing_fields_422(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {"missing_fields": ["equipment", "goal"], "plan": {}}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={"profile": SAMPLE_PROFILE})
    assert resp.status_code == 422
    assert "equipment" in resp.json()["detail"]["missing_fields"]


def test_generate_plan_empty_plan_502(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {"plan": {}, "errors": ["MCP 超时"]}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={"profile": SAMPLE_PROFILE})
    assert resp.status_code == 502
    assert "MCP 超时" in resp.json()["detail"]["errors"]


def test_generate_plan_agent_crash_502(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post("/api/plans/generate", json={"profile": SAMPLE_PROFILE})
    assert resp.status_code == 502
    assert "boom" in resp.json()["detail"]


def test_persist_false_skips_storage(client, monkeypatch):
    async def fake_run_agent(user_id, profile):
        return {"plan": FAKE_PLAN, "validation": {"valid": True}, "errors": []}

    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    resp = client.post(
        "/api/plans/generate", json={"profile": SAMPLE_PROFILE, "persist": False}
    )
    assert resp.status_code == 200

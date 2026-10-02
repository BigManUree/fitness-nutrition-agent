"""httpOnly cookie 会话鉴权测试（Bearer 回退兼容）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "bob"
PASSWORD = "secret123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_cookie.db"))
    return TestClient(api_main.app)


def _register(c: TestClient) -> dict:
    resp = c.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_register_sets_session_cookie(client):
    body = _register(client)
    assert body["username"] == USERNAME
    assert "session" in client.cookies  # TestClient 的 cookie jar 已收到


def test_cookie_auth_without_header(client):
    _register(client)
    resp = client.get("/api/me")  # 不带 Authorization 头，走 cookie
    assert resp.status_code == 200
    assert resp.json()["username"] == USERNAME


def test_bearer_fallback_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_bearer.db"))
    bare = TestClient(api_main.app)
    token = _register(bare)["token"]
    bare.cookies.clear()  # 仅用 Bearer 头
    bare.headers["Authorization"] = f"Bearer {token}"
    assert bare.get("/api/me").status_code == 200


def test_logout_clears_cookie_and_revokes(client):
    _register(client)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_revoked_cookie_rejected(client):
    _register(client)
    client.post("/api/auth/logout")
    # 再注册同账号拿新 cookie 前，旧 cookie 应已失效
    assert client.get("/api/me").status_code == 401

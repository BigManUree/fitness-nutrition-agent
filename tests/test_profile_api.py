"""画像保存增强：装备规整 + 向量入库非阻塞告警。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "carol"
PASSWORD = "secret123"

BASE = {
    "sex": "female",
    "age": 28,
    "height_cm": 165.0,
    "weight_kg": 55.0,
    "goal": "fat_loss",
    "days_per_week": 3,
    "equipment": ["dumbbell"],
    "dietary_preferences": [],
    "allergies": [],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_profile.db"))
    c = TestClient(api_main.app)
    c.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD})
    # 默认不真正写向量库（测试无 Ollama）：把 Chroma 写入边界 mock 成 no-op，
    # 让 index_profile_if_available 的真实 try/except 成为被测对象。
    monkeypatch.setattr("app.rag.profile_indexer.index_profile", lambda *a, **k: None)
    return c


def test_equipment_normalized_before_save(client):
    body = {**BASE, "equipment": [" Dumbbell ", "BARBELL", "dumbbell", "gym"]}
    resp = client.put("/api/profile", json=body)
    assert resp.status_code == 200
    got = client.get("/api/profile").json()["profile"]["equipment"]
    assert got == ["gym"]  # 小写去重后，gym 折叠为唯一值


def test_indexing_failure_sets_warning(client, monkeypatch):
    def boom(profile, user_id):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("app.rag.profile_indexer.index_profile", boom)
    resp = client.put("/api/profile", json=BASE)
    body = resp.json()
    assert body["status"] == "saved"
    assert body["indexing_warning"] is not None


def test_indexing_success_no_warning(client):
    resp = client.put("/api/profile", json=BASE)
    assert resp.json()["indexing_warning"] is None

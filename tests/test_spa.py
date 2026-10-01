"""SPA 静态托管：dist 存在返回 index.html，缺失则 404 且不破坏 /api。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as api_main


def test_spa_fallback_returns_index(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA-ROOT</html>", encoding="utf-8")
    monkeypatch.setattr(api_main, "FRONTEND_DIST", dist)
    resp = TestClient(api_main.app).get("/profile")
    assert resp.status_code == 200
    assert "SPA-ROOT" in resp.text


def test_spa_fallback_without_dist_404(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "FRONTEND_DIST", tmp_path / "missing")
    resp = TestClient(api_main.app).get("/profile")
    assert resp.status_code == 404


def test_api_routes_unaffected_by_fallback():
    bare = TestClient(api_main.app)
    assert bare.get("/health").status_code == 200
    assert bare.get("/api/me").status_code == 401  # 走鉴权，不被 catch-all 吞掉

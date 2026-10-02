"""营养检索缓存测试：nutrition_cache 表 + search_nutrition 缓存行为。

覆盖：
    存取回环、TTL 过期判定、put 覆盖；
    search_nutrition 命中跳过 MCP（source 区分 mcp/cache）、
    key 归一化（大小写/空白不影响命中）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.nutrition_cache import get_cached, put_cache
from app.tools.nutrition_tools import search_nutrition

ITEMS = [{"id": "usda_1", "name": "CHICKEN BREAST", "per_100g": {"calories": 165}}]


def _db(tmp_path: Path) -> Path:
    """tmp_path 是目录，SQLite 需要文件路径。"""
    return tmp_path / "cache.db"


def test_get_cached_miss_when_empty(tmp_path) -> None:
    assert get_cached("chicken breast::[2]", ttl_seconds=86400, db_path=_db(tmp_path)) is None


def test_put_then_get_roundtrip(tmp_path) -> None:
    put_cache("chicken breast::[2]", ITEMS, _db(tmp_path))
    assert get_cached("chicken breast::[2]", ttl_seconds=86400, db_path=_db(tmp_path)) == ITEMS


def test_get_cached_expired_returns_none(tmp_path) -> None:
    put_cache("chicken breast::[2]", ITEMS, _db(tmp_path))
    # ttl_seconds=0：任何已写入行都视为过期（created_at 不晚于 now）
    assert get_cached("chicken breast::[2]", ttl_seconds=0, db_path=_db(tmp_path)) is None


def test_put_cache_overwrites_same_key(tmp_path) -> None:
    put_cache("k::[2]", ITEMS, _db(tmp_path))
    put_cache("k::[2]", [{"id": "usda_2", "name": "EGG", "per_100g": {}}], _db(tmp_path))
    got = get_cached("k::[2]", ttl_seconds=86400, db_path=_db(tmp_path))
    assert len(got) == 1
    assert got[0]["name"] == "EGG"


async def test_search_nutrition_hits_cache_and_skips_mcp(monkeypatch, tmp_path) -> None:
    calls: list[int] = []

    async def fake_call(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        calls.append(1)
        return [
            {
                "id": "usda_1",
                "name": "CHICKEN BREAST",
                "per_100g": {"calories": 165, "protein": 20.4},
            }
        ]

    monkeypatch.setattr(
        "app.tools.nutrition_tools.nutrition_client.search_nutrition", fake_call
    )

    first = await search_nutrition("chicken breast", db_path=_db(tmp_path))
    second = await search_nutrition("chicken breast", db_path=_db(tmp_path))

    assert first["source"] == "mcp"
    assert second["source"] == "cache"
    assert second["items"] == first["items"]
    assert len(calls) == 1  # 第二次命中缓存，未再调 MCP


async def test_search_nutrition_cache_key_normalizes_query(monkeypatch, tmp_path) -> None:
    calls: list[int] = []

    async def fake_call(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        calls.append(1)
        return [
            {"id": "usda_1", "name": "CHICKEN BREAST", "per_100g": {"calories": 165}}
        ]

    monkeypatch.setattr(
        "app.tools.nutrition_tools.nutrition_client.search_nutrition", fake_call
    )

    await search_nutrition("Chicken Breast ", db_path=_db(tmp_path))
    result = await search_nutrition("chicken breast", db_path=_db(tmp_path))

    assert result["source"] == "cache"
    assert len(calls) == 1

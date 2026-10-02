"""营养检索缓存存取：nutrition_cache 表。

search_nutrition 工具在调用 MCP 前用 get_cached 查缓存（命中且未过期则
跳过串行的 MCP 调用），miss 抓取回填后由 put_cache 写入。营养数据近乎静态，
缓存命中率很高，第二次及后续生成计划几乎零检索延迟。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db.sqlite_client import _connect


def get_cached(
    cache_key: str,
    ttl_seconds: int,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]] | None:
    """取未过期的缓存条目；未命中（无记录或已过期）返回 None。

    ttl_seconds：缓存有效期秒数，用 SQLite 的 datetime('now', '-N seconds')
    与写库时的 CURRENT_TIMESTAMP 比较（均为 UTC），避免在 Python 里二次解析。
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT items_json FROM nutrition_cache "
            "WHERE cache_key = ? AND created_at > datetime('now', ?)",
            (cache_key, f"-{int(ttl_seconds)} seconds"),
        ).fetchone()
    if row is None:
        return None
    items = json.loads(row["items_json"])
    return items if isinstance(items, list) else None


def put_cache(
    cache_key: str,
    items: list[dict[str, Any]],
    db_path: str | Path | None = None,
) -> None:
    """写入（或覆盖并刷新时间戳）一条缓存。"""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO nutrition_cache (cache_key, items_json, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cache_key) DO UPDATE SET
                items_json = excluded.items_json,
                created_at = CURRENT_TIMESTAMP
            """,
            (cache_key, json.dumps(items, ensure_ascii=False)),
        )
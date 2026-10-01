"""翻译缓存存取：translation_cache 表。

translate_plan 节点在调用 LLM 前先用 get_cached_translations 批量查缓存，
翻译完成后用 save_translations 回写，避免同一英文文本重复翻译。
"""

from __future__ import annotations

from pathlib import Path

from app.db.sqlite_client import _connect


def get_cached_translations(
    texts: list[str] | set[str], db_path: str | Path | None = None
) -> dict[str, str]:
    """批量取已缓存译文；未命中的文本不出现在返回值中。"""
    unique = [t for t in dict.fromkeys(texts) if t]
    if not unique:
        return {}
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT source_text, translated FROM translation_cache "
            f"WHERE source_text IN ({','.join('?' for _ in unique)})",
            unique,
        ).fetchall()
    return {row["source_text"]: row["translated"] for row in rows}


def save_translations(
    pairs: dict[str, str], db_path: str | Path | None = None
) -> None:
    """批量写入译文（已存在则覆盖）。"""
    items = [(source, target) for source, target in pairs.items() if source and target]
    if not items:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO translation_cache (source_text, translated)
            VALUES (?, ?)
            ON CONFLICT(source_text) DO UPDATE SET
                translated = excluded.translated
            """,
            items,
        )

"""SQLite 存取层：用户画像与生成计划的持久化。

表结构与 docs/requirements.md 第 3 步一致：
    user_profile    一份画像按 user_id 唯一（upsert）
    generated_plans 计划历史（MVP 可选写入）

所有函数都接受可选 db_path：默认读 SQLITE_DB_PATH（./data/app.db），
测试时可传入临时库路径，避免污染开发数据。
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

# 入口可能是 Streamlit / 脚本，主动加载 .env 中的 SQLITE_DB_PATH
from app.config import load_dotenv
from app.db.models import Profile

load_dotenv()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profile (
    user_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generated_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    plan_type TEXT,          -- 'weekly_plan' | 'daily_meals'
    plan_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db_path() -> Path:
    return Path(os.getenv("SQLITE_DB_PATH", "./data/app.db"))


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # 懒建表：任何入口调用时库结构都已就绪（CREATE IF NOT EXISTS，开销极小）
    conn.executescript(SCHEMA_SQL)
    return conn


def ensure_tables(db_path: str | Path | None = None) -> Path:
    """建表（幂等），返回数据库路径。"""
    path = Path(db_path) if db_path is not None else get_db_path()
    with _connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
    return path


def save_profile(
    profile: Profile | dict, user_id: str, db_path: str | Path | None = None
) -> None:
    """按 user_id upsert 画像；已存在则覆盖并刷新 updated_at。"""
    data = profile.model_dump() if isinstance(profile, Profile) else dict(profile)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_profile (user_id, profile_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_json = excluded.profile_json,
                updated_at   = CURRENT_TIMESTAMP
            """,
            (user_id, json.dumps(data, ensure_ascii=False)),
        )


def load_profile(
    user_id: str, db_path: str | Path | None = None
) -> Profile | None:
    """读取指定用户画像；不存在返回 None。数据损坏时抛 ValidationError。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT profile_json FROM user_profile WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return Profile(**json.loads(row["profile_json"]))


def load_latest_profile(
    db_path: str | Path | None = None,
) -> tuple[str, Profile] | None:
    """读取最近更新的画像（跨会话预填用）；库为空返回 None。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT user_id, profile_json FROM user_profile
            ORDER BY updated_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return row["user_id"], Profile(**json.loads(row["profile_json"]))


def save_plan(
    user_id: str,
    plan: dict,
    plan_type: str = "weekly_plan",
    db_path: str | Path | None = None,
) -> int:
    """追加保存一条生成计划，返回自增 id（MVP 可选使用）。"""
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO generated_plans (user_id, plan_type, plan_json)"
            " VALUES (?, ?, ?)",
            (user_id, plan_type, json.dumps(plan, ensure_ascii=False)),
        )
        return int(cur.lastrowid)

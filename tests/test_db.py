"""SQLite 存取层测试：使用 tmp_path 临时库，不碰开发数据。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from app.db.models import Profile
from app.db.sqlite_client import (
    ensure_tables,
    load_latest_plan,
    load_latest_profile,
    load_profile,
    log_performance,
    save_plan,
    save_profile,
    upsert_bad_case,
)
from pydantic import ValidationError


def make_profile(**overrides) -> Profile:
    base = {
        "sex": "male",
        "age": 30,
        "height_cm": 175.0,
        "weight_kg": 72.0,
        "goal": "muscle_gain",
        "days_per_week": 4,
        "equipment": ["barbell", "dumbbell"],
        "dietary_preferences": ["清淡"],
        "allergies": ["花生"],
    }
    base.update(overrides)
    return Profile(**base)


def test_ensure_tables_idempotent(tmp_path):
    db = tmp_path / "test.db"
    ensure_tables(db)
    ensure_tables(db)  # 再执行不应报错、不清数据

    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "user_profile",
        "generated_plans",
        "performance_log",
        "bad_cases",
    } <= tables


def test_save_and_load_profile_roundtrip(tmp_path):
    db = tmp_path / "test.db"
    profile = make_profile()
    save_profile(profile, "user-001", db)

    loaded = load_profile("user-001", db)
    assert loaded == profile


def test_save_profile_accepts_dict(tmp_path):
    db = tmp_path / "test.db"
    profile = make_profile()
    save_profile(profile.model_dump(), "user-002", db)

    assert load_profile("user-002", db) == profile


def test_load_missing_user_returns_none(tmp_path):
    db = tmp_path / "test.db"
    ensure_tables(db)
    assert load_profile("nobody", db) is None


def test_upsert_overwrites_existing(tmp_path):
    db = tmp_path / "test.db"
    save_profile(make_profile(weight_kg=72.0), "user-001", db)
    save_profile(make_profile(weight_kg=80.0), "user-001", db)

    loaded = load_profile("user-001", db)
    assert loaded is not None
    assert loaded.weight_kg == 80.0

    with sqlite3.connect(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM user_profile WHERE user_id = 'user-001'"
        ).fetchone()[0]
    assert count == 1


def test_load_latest_profile(tmp_path):
    db = tmp_path / "test.db"
    assert load_latest_profile(db) is None

    save_profile(make_profile(goal="fat_loss"), "user-a", db)
    save_profile(make_profile(goal="muscle_gain"), "user-b", db)

    user_id, profile = load_latest_profile(db)
    assert user_id == "user-b"
    assert profile.goal == "muscle_gain"


def test_save_plan_appends_rows(tmp_path):
    db = tmp_path / "test.db"
    ensure_tables(db)
    plan = {"weekly_plan": []}

    id1 = save_plan("user-001", plan, "weekly_plan", db)
    id2 = save_plan("user-001", {"daily_meals": {}}, "daily_meals", db)
    assert id2 == id1 + 1

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT user_id, plan_type FROM generated_plans ORDER BY id"
        ).fetchall()
    assert rows == [("user-001", "weekly_plan"), ("user-001", "daily_meals")]


def test_load_latest_plan_returns_newest_for_user_only(tmp_path):
    db = tmp_path / "test.db"
    ensure_tables(db)
    save_plan("user-001", {"v": 1}, "weekly_plan", db)
    save_plan("user-002", {"v": 9}, "weekly_plan", db)
    save_plan("user-001", {"v": 2}, "weekly_plan", db)

    record = load_latest_plan("user-001", db)
    assert record is not None
    plan, _created_at = record
    assert plan == {"v": 2}  # 取该用户最近一条，不受其他用户影响

    assert load_latest_plan("nobody", db) is None


@pytest.mark.parametrize(
    "field,bad_value",
    [("age", 200), ("days_per_week", 9), ("sex", "unknown")],
)
def test_invalid_profile_rejected(field, bad_value):
    with pytest.raises(ValidationError):
        make_profile(**{field: bad_value})


# ============================================================
# performance_log
# ============================================================


def test_log_performance_inserts_rows(tmp_path):
    db = tmp_path / "test.db"
    log_performance(
        session_id="sess-1",
        node_name="generate_plan",
        duration_ms=3200,
        user_id="user-001",
        token_input=500,
        token_output=1200,
        db_path=db,
    )
    log_performance(
        session_id="sess-1",
        node_name="safety_guard",
        duration_ms=2,
        status="error",
        error_message="timeout",
        db_path=db,
    )

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT session_id, node_name, token_input, token_output,"
            " duration_ms, status, error_message FROM performance_log ORDER BY id"
        ).fetchall()

    assert rows == [
        ("sess-1", "generate_plan", 500, 1200, 3200, "success", None),
        ("sess-1", "safety_guard", None, None, 2, "error", "timeout"),
    ]


def test_log_performance_rejects_bad_status(tmp_path):
    db = tmp_path / "test.db"
    with pytest.raises(sqlite3.IntegrityError):
        log_performance(
            session_id="sess-1",
            node_name="n",
            duration_ms=1,
            status="bogus",
            db_path=db,
        )


# ============================================================
# bad_cases
# ============================================================


def test_upsert_bad_case_insert_uses_default_status(tmp_path):
    db = tmp_path / "test.db"
    case_id = upsert_bad_case(
        "BC-001",
        scenario_type="信息不全",
        input_text="帮我生成计划",
        severity="中",
        db_path=db,
    )
    assert case_id == 1

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT status, created_at, updated_at FROM bad_cases"
        ).fetchone()
    assert row[0] == "待修复"
    assert row[1] is not None
    assert row[2] is not None


def test_upsert_bad_case_update_merges_fields(tmp_path):
    db = tmp_path / "test.db"
    upsert_bad_case(
        "BC-001",
        scenario_type="信息不全",
        input_text="帮我生成计划",
        actual_output="（追问缺失字段）",
        severity="中",
        fix_plan="补充器械追问",
        db_path=db,
    )
    same_id = upsert_bad_case(
        "BC-001", actual_output="已修复：追问 equipment", status_text="已修复", db_path=db
    )
    assert same_id == 1

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT scenario_type, input, actual_output, fix_plan, status"
            " FROM bad_cases"
        ).fetchall()
    assert rows == [
        ("信息不全", "帮我生成计划", "已修复：追问 equipment", "补充器械追问", "已修复")
    ]
    assert conn_total(db, "bad_cases") == 1


def test_upsert_bad_case_case_id_unique(tmp_path):
    db = tmp_path / "test.db"
    upsert_bad_case("BC-001", db_path=db)
    upsert_bad_case("BC-002", db_path=db)
    assert conn_total(db, "bad_cases") == 2


def conn_total(db: Path, table: str) -> int:
    with sqlite3.connect(db) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

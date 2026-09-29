"""SQLite 存取层测试：使用 tmp_path 临时库，不碰开发数据。"""

from __future__ import annotations

import sqlite3

import pytest
from app.db.models import Profile
from app.db.sqlite_client import (
    ensure_tables,
    load_latest_profile,
    load_profile,
    save_plan,
    save_profile,
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
    assert {"user_profile", "generated_plans"} <= tables


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


@pytest.mark.parametrize(
    "field,bad_value",
    [("age", 200), ("days_per_week", 9), ("sex", "unknown")],
)
def test_invalid_profile_rejected(field, bad_value):
    with pytest.raises(ValidationError):
        make_profile(**{field: bad_value})

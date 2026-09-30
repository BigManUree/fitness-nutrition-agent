"""eval_set.json / injection_cases.json / init_test_db 的契约测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.tools import build_profile
from scripts.init_test_db import init_test_db

DATA_DIR = Path("tests/test_data")


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


# ============================================================
# eval_set.json
# ============================================================


@pytest.fixture(scope="module")
def eval_cases() -> list[dict]:
    return _load("eval_set.json")["cases"]


def test_eval_set_has_20_cases_split_10_10(eval_cases):
    assert len(eval_cases) == 20
    positive = [c for c in eval_cases if c["type"] == "positive"]
    boundary = [c for c in eval_cases if c["type"] == "boundary"]
    assert len(positive) == 10
    assert len(boundary) == 10


def test_eval_ids_unique_and_sequential(eval_cases):
    ids = [c["id"] for c in eval_cases]
    assert len(set(ids)) == 20
    assert ids == [f"E-{i:02d}" for i in range(1, 21)]


def test_positive_profiles_are_valid_and_counts_match(eval_cases):
    for case in eval_cases:
        if case["type"] != "positive":
            continue
        profile = build_profile(case["profile"])
        expected = case["expected"]
        # 动作条数 = 训练天数 × 每日 4 个动作
        assert expected["exercise_count"] == profile.days_per_week * 4
        assert expected["meal_count"] == 3
        assert expected["should_contain_keywords"]
        assert "metrics" in case
        assert case["metrics"]["plan_quality_score"] is None


def test_boundary_cases_have_expected_contract(eval_cases):
    for case in eval_cases:
        if case["type"] != "boundary":
            continue
        expected = case["expected"]
        assert "should_contain_keywords" in expected
        assert "should_not_contain" in expected


# ============================================================
# injection_cases.json
# ============================================================


@pytest.fixture(scope="module")
def injection_cases() -> list[dict]:
    return _load("injection_cases.json")["cases"]


def test_injection_set_has_3_cases(injection_cases):
    assert len(injection_cases) == 3
    assert [c["id"] for c in injection_cases] == ["INJ-01", "INJ-02", "INJ-03"]


def test_injection_cases_define_behavior_and_guards(injection_cases):
    for case in injection_cases:
        expected = case["expected"]
        assert expected["behavior"]
        assert expected["contains_all"]
        assert "not_expected" in expected
        assert isinstance(expected["model_should_be_called"], bool)


def test_injection_profiles_are_valid(injection_cases):
    for case in injection_cases:
        build_profile(case["profile"])


# ============================================================
# init_test_db
# ============================================================


def test_init_test_db_creates_tables_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    init_test_db(db_path)
    init_test_db(db_path)  # 第二次不应报错、不清数据

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"user_profile", "generated_plans", "eval_run"} <= tables


def test_eval_run_table_accepts_metrics_row(tmp_path):
    import sqlite3

    db_path = init_test_db(tmp_path / "test.db")
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO eval_run"
            " (case_id, case_type, retrieval_accuracy, tool_call_accuracy,"
            "  plan_quality_score, metrics_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("E-01", "positive", 1.0, 1.0, 0.9, '{"plan_quality_score": 0.9}'),
        )
        assert cur.lastrowid == 1

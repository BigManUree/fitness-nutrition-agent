"""performance_logger 装饰器测试：写入临时库，不碰开发数据。"""

from __future__ import annotations

import sqlite3

import pytest
from app.utils import performance_logger as pl
from app.utils.performance_logger import (
    USAGE_KEY,
    extract_llm_usage,
    log_performance,
)


def _rows(db) -> list[sqlite3.Row]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT session_id, user_id, node_name, token_input, token_output,"
            " duration_ms, status, error_message FROM performance_log"
        ).fetchall()


async def test_async_node_logs_usage_and_pops_key(tmp_path):
    db = tmp_path / "test.db"

    @log_performance("generate_plan")
    async def node(state):
        return {"plan": {}, USAGE_KEY: (500, 1200)}

    state = {"user_id": "u-1", "profile": {}}
    result = await node(state, db_path=db)

    assert USAGE_KEY not in result  # 装饰器已弹出，不污染状态
    rows = _rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert (
        row["node_name"] == "generate_plan"
        and row["token_input"] == 500
        and row["token_output"] == 1200
        and row["status"] == "success"
        and row["error_message"] is None
    )
    assert row["session_id"] == "u-1" and row["user_id"] == "u-1"
    assert row["duration_ms"] >= 0


def test_sync_node_logs_without_tokens(tmp_path):
    db = tmp_path / "test.db"

    @log_performance("validate_output")
    def node(state):
        return {"validation": {"valid": True}}

    result = node({"user_id": "u-2"}, db_path=db)
    assert result == {"validation": {"valid": True}}

    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["token_input"] is None and rows[0]["token_output"] is None


async def test_async_node_error_is_recorded_and_reraised(tmp_path):
    db = tmp_path / "test.db"

    @log_performance("search_exercises")
    async def node(state):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await node({"user_id": "u-3"}, db_path=db)

    rows = _rows(db)
    assert rows[0]["status"] == "error" and rows[0]["error_message"] == "boom"


def test_session_id_preferred_over_user_id(tmp_path):
    db = tmp_path / "test.db"

    @log_performance("n")
    def node(state):
        return {}

    node({"session_id": "sess-x", "user_id": "u-9"}, db_path=db)
    assert _rows(db)[0]["session_id"] == "sess-x"


async def test_db_write_failure_does_not_break_node(tmp_path, monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(pl, "db_log_performance", _raise)

    @log_performance("n")
    async def node(state):
        return {"ok": True}

    assert await node({"user_id": "u"}) == {"ok": True}


class _FakeUsage:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeResponse:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_extract_usage_from_usage_metadata():
    resp = _FakeResponse(usage_metadata={"input_tokens": 11, "output_tokens": 22})
    assert extract_llm_usage(resp) == (11, 22)


def test_extract_usage_from_raw_usage_object():
    resp = _FakeResponse(usage=_FakeUsage(prompt_tokens=7, completion_tokens=9))
    assert extract_llm_usage(resp) == (7, 9)


def test_extract_usage_from_dict_and_callable():
    resp = _FakeResponse(usage={"input_tokens": 3, "output_tokens": 4})
    assert extract_llm_usage(resp) == (3, 4)

    resp2 = _FakeResponse(usage=lambda: _FakeUsage(prompt_tokens=1, completion_tokens=2))
    assert extract_llm_usage(resp2) == (1, 2)


def test_extract_usage_from_additional_kwargs():
    resp = _FakeResponse(
        usage_metadata=None,
        additional_kwargs={"token_usage": {"prompt_tokens": 5, "completion_tokens": 6}},
    )
    assert extract_llm_usage(resp) == (5, 6)


def test_extract_usage_missing_returns_none_pair():
    assert extract_llm_usage(_FakeResponse()) == (None, None)

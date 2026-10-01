"""MCP 故障处理测试：重试 1 次、失败不降级、空结果提示。

重要策略说明（CLAUDE.md 4.4 / docs/bad_cases.md 第 7 节）：
    MCP 重试 1 次后仍失败时，**明确告知失败，不降级为模型内置知识**，
    因此任何输出都不应出现"基于通用知识"字样或 source != "mcp" 的数据。
"""

from __future__ import annotations

import pytest
from app.agent.nodes.search_exercises import search_exercises_node
from app.agent.state import AgentState
from app.mcp import exerciseapi_client, nutrition_client
from app.tools import exercise_tools, nutrition_tools
from tests.mocks.mcp_mocks import (
    mock_search_exercises_error,
    mock_search_exercises_timeout,
    mock_search_exercises_timeout_then_success,
    mock_search_nutrition_empty,
)

# 降级为通用知识时可能出现的标注（必须永不出现）
FALLBACK_MARKER = "基于通用知识"


# ============================================================
# 超时：重试 1 次
# ============================================================


async def test_timeout_retries_once_then_raises(monkeypatch):
    failure = mock_search_exercises_timeout()
    monkeypatch.setattr(exerciseapi_client, "search_exercises", failure)

    with pytest.raises(exercise_tools.ExerciseToolError):
        await exercise_tools.search_exercises(muscle="chest", limit=5)

    # 首次调用 + 重试 1 次 = 2 次
    assert failure.calls == 2


async def test_timeout_retry_success_returns_mcp_data(monkeypatch):
    flaky = mock_search_exercises_timeout_then_success()
    monkeypatch.setattr(exerciseapi_client, "search_exercises", flaky)

    result = await exercise_tools.search_exercises(muscle="chest", limit=5)

    assert flaky.calls == 2
    assert result["source"] == "mcp"
    assert result["items"][0]["name"] == "Barbell Bench Press"


# ============================================================
# 重试失败：明确报错，禁止降级为通用知识
# ============================================================


async def test_500_error_retries_once_no_fallback(monkeypatch):
    server_error = mock_search_exercises_error()
    monkeypatch.setattr(exerciseapi_client, "search_exercises", server_error)

    with pytest.raises(exercise_tools.ExerciseToolError) as exc_info:
        await exercise_tools.search_exercises(muscle="chest", limit=5)

    assert server_error.calls == 2
    assert "500" in str(exc_info.value)
    assert FALLBACK_MARKER not in str(exc_info.value)


async def test_node_reports_failure_without_fabricating(monkeypatch):
    """节点层：单肌群失败计入 errors，不产出编造动作、不标注通用知识。"""
    server_error = mock_search_exercises_error()
    monkeypatch.setattr(exerciseapi_client, "search_exercises", server_error)

    state: AgentState = {
        "user_id": "u-1",
        "profile": {"equipment": ["gym"], "days_per_week": 3},
    }
    result = await search_exercises_node(state)

    # 健身房节点会查 9 个肌群，每个肌群 2 次调用，全部失败
    assert server_error.calls == 18
    assert result["exercise_candidates"] == []
    assert result["errors"]  # 有明确的失败信息
    assert FALLBACK_MARKER not in " ".join(result["errors"])


# ============================================================
# 空结果：提示"未找到匹配"
# ============================================================


async def test_nutrition_empty_prompts_no_match(monkeypatch, tmp_path):
    empty = mock_search_nutrition_empty()
    monkeypatch.setattr(nutrition_client, "search_nutrition", empty)

    result = await nutrition_tools.search_nutrition(
        "不存在的外星食物xyz", db_path=tmp_path / "cache.db"
    )

    assert empty.calls == 1
    assert result["items"] == []
    assert result["source"] == "mcp"
    assert "未找到匹配" in result["note"]
    assert FALLBACK_MARKER not in result["note"]


async def test_empty_result_is_not_retried_as_error(monkeypatch, tmp_path):
    """空结果是正常响应（非错误），不应触发重试。"""
    empty = mock_search_nutrition_empty()
    monkeypatch.setattr(nutrition_client, "search_nutrition", empty)

    await nutrition_tools.search_nutrition("xyz", db_path=tmp_path / "cache.db")

    assert empty.calls == 1

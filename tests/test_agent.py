"""Agent 节点单元测试（不调用真实 LLM / MCP）。"""

from __future__ import annotations

import pytest
from app.agent.graph import _route_after_profile, _route_after_validate, build_graph
from app.agent.nodes.collect_profile import collect_profile
from app.agent.nodes.validate_output import validate_output

VALID_PROFILE = {
    "sex": "male",
    "age": 28,
    "height_cm": 175,
    "weight_kg": 72,
    "goal": "muscle_gain",
    "days_per_week": 3,
    "equipment": ["dumbbell"],
    "dietary_preferences": [],
    "allergies": [],
}


def make_plan(exercise: str = "Dumbbell Press", food: str = "EGG") -> dict:
    day = {
        "day": 1,
        "focus": "push",
        "exercises": [
            {"name": exercise, "sets": 3, "reps": "8-12", "rest": "60秒"}
        ],
    }
    return {
        "weekly_plan": [day, day, day],
        "daily_meals": {
            "breakfast": [{"food": food, "amount": "2个"}],
            "lunch": [{"food": food, "amount": "2个"}],
            "dinner": [{"food": food, "amount": "2个"}],
        },
        "rationale": "测试说明",
    }


def test_collect_profile_valid():
    result = collect_profile({"profile": dict(VALID_PROFILE)})
    assert result["missing_fields"] == []
    assert result["profile"]["goal"] == "muscle_gain"


def test_collect_profile_missing():
    result = collect_profile({"profile": {"sex": "male"}})
    assert result["missing_fields"]
    assert "age" in result["missing_fields"]


def test_validate_output_passes():
    state = {
        "profile": VALID_PROFILE,
        "plan": make_plan(),
        "exercise_candidates": [{"name": "Dumbbell Press"}],
        "nutrition_candidates": [{"name": "EGG"}],
    }
    result = validate_output(state)
    assert result["validation"]["valid"] is True
    assert result["validation"]["violations"] == []


def test_validate_detects_fabrication_and_day_mismatch():
    plan = make_plan(exercise="不存在的动作", food="不存在的食物")
    state = {
        "profile": VALID_PROFILE,
        "plan": plan,
        "exercise_candidates": [{"name": "Dumbbell Press"}],
        "nutrition_candidates": [{"name": "EGG"}],
    }
    result = validate_output(state)
    violations = " ".join(result["validation"]["violations"])
    assert not result["validation"]["valid"]
    assert "疑似编造" in violations


def test_routing_profile_incomplete_ends():
    assert _route_after_profile({"missing_fields": ["age"]}) == "__end__"


def test_routing_validate_retry_then_end():
    bad = {"validation": {"valid": False}, "retries": 0}
    assert _route_after_validate(bad) == "generate_plan"
    bad["retries"] = 1
    assert _route_after_validate(bad) == "__end__"


def test_graph_builds():
    graph = build_graph()
    assert graph is not None


def test_graph_default_has_memory_checkpointer():
    assert getattr(build_graph(), "checkpointer", None) is not None
    assert getattr(build_graph(False), "checkpointer", None) is None


def test_checkpointer_requires_thread_id():
    graph = build_graph()
    with pytest.raises(ValueError, match="thread_id"):
        graph.invoke({"user_id": "u", "profile": dict(VALID_PROFILE)})


def test_checkpointer_persists_and_isolates_threads(monkeypatch):
    """同一 thread_id 的状态在调用后可回放；不同 thread 互不影响。"""
    from app.agent import graph as graph_module
    from langgraph.checkpoint.memory import MemorySaver

    # 打桩全部节点：不触网/不调 LLM，走通完整路由
    monkeypatch.setattr(
        graph_module, "collect_profile", lambda state: {"missing_fields": []}
    )
    monkeypatch.setattr(graph_module, "search_exercises_node", lambda state: {})
    monkeypatch.setattr(graph_module, "search_nutrition_node", lambda state: {})
    monkeypatch.setattr(graph_module, "generate_plan", lambda state: {})
    monkeypatch.setattr(
        graph_module,
        "validate_output",
        lambda state: {"validation": {"valid": True}},
    )

    checkpointer = MemorySaver()
    graph = graph_module.build_graph(checkpointer)
    cfg_a = {"configurable": {"thread_id": "thread-a"}}
    cfg_b = {"configurable": {"thread_id": "thread-b"}}

    graph.invoke({"user_id": "u-a", "profile": dict(VALID_PROFILE)}, config=cfg_a)
    graph.invoke({"user_id": "u-b", "profile": dict(VALID_PROFILE)}, config=cfg_b)

    snapshot_a = graph.get_state(cfg_a)
    assert snapshot_a.next == ()  # 已正常结束
    assert snapshot_a.values["user_id"] == "u-a"
    assert graph.get_state(cfg_b).values["user_id"] == "u-b"

    # 历史中可查到本次 run 的 checkpoint
    assert list(graph.get_state_history(cfg_a))

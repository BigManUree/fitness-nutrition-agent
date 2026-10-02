"""对话调整工具调用循环测试：FakeLLM 模拟工具往返，不触网不调真实模型。"""

from __future__ import annotations

from typing import Any

from app.agent.chat_adjust import resolve_with_tools, stream_with_tools
from langchain_core.messages import AIMessage, AIMessageChunk

PROFILE = {
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

FAKE_ALTERNATIVES = {
    "original_exercise": "Barbell Bench Press",
    "alternatives": [
        {
            "id": "Dumbbell_Bench_Press",
            "name": "Dumbbell Bench Press",
            "primary_muscles": ["pectoralis major"],
            "secondary_muscles": [],
            "equipment": "dumbbell",
            "category": "strength",
            "difficulty": "beginner",
            "force": "push",
            "mechanic": "compound",
            "match_reasons": ["同一目标肌群"],
        }
    ],
    "total": 1,
    "source": "mcp",
}


class _FakeBoundLLM:
    """按脚本依次返回响应：先 tool_calls，后最终回答。"""

    def __init__(self, responses: list[AIMessage]):
        self._responses = list(responses)
        self.calls = 0

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls += 1
        return self._responses.pop(0)


class _FakeLLM:
    def __init__(self, responses: list[AIMessage]):
        self._responses = responses
        self.bound: _FakeBoundLLM | None = None

    def bind_tools(self, tools: list[Any]) -> _FakeBoundLLM:
        self.bound = _FakeBoundLLM(self._responses)
        return self.bound


def test_resolve_calls_tool_and_returns_answer():
    captured: dict[str, Any] = {}

    def fake_tool_runner(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return FAKE_ALTERNATIVES

    tool_call = {
        "name": "substitute_exercise",
        "args": {
            "original_exercise": "Barbell Bench Press",
            "reason": "没有杠铃",
            # 模型越权给出 bodyweight，应被画像器械覆盖
            "equipment_available": ["bodyweight"],
        },
        "id": "call-1",
    }
    llm = _FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call]),
            AIMessage(content="可以换成 Dumbbell Bench Press。"),
        ]
    )

    answer, results = resolve_with_tools(
        llm, [], PROFILE, tool_runner=fake_tool_runner
    )

    assert answer == "可以换成 Dumbbell Bench Press。"
    assert results == [FAKE_ALTERNATIVES]
    assert llm.bound is not None and llm.bound.calls == 2
    # 器械被画像强制约束为 dumbbell
    assert captured["equipment_available"] == ["dumbbell"]
    assert captured["original_exercise"] == "Barbell Bench Press"


def test_resolve_without_tool_call_passes_through():
    llm = _FakeLLM([AIMessage(content="这是一个普通回答。")])

    answer, results = resolve_with_tools(llm, [], PROFILE)

    assert answer == "这是一个普通回答。"
    assert results == []
    assert llm.bound.calls == 1


def test_resolve_tool_failure_is_captured():
    def boom(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("MCP down")

    tool_call = {
        "name": "substitute_exercise",
        "args": {"original_exercise": "X", "reason": "r"},
        "id": "call-2",
    }
    llm = _FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call]),
            AIMessage(content="抱歉，替换服务暂不可用。"),
        ]
    )

    answer, results = resolve_with_tools(
        llm, [], PROFILE, tool_runner=boom
    )

    assert "暂不可用" in answer
    assert results[0]["alternatives"] == []
    assert "MCP down" in results[0]["note"]


def test_resolve_multiple_tool_calls_in_sequence():
    """模型连续两轮工具调用后才给最终回答。"""
    calls: list[dict[str, Any]] = []

    def fake_tool_runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return FAKE_ALTERNATIVES

    tc1 = {
        "name": "substitute_exercise",
        "args": {"original_exercise": "A", "reason": "r1"},
        "id": "c1",
    }
    tc2 = {
        "name": "substitute_exercise",
        "args": {"original_exercise": "B", "reason": "r2"},
        "id": "c2",
    }
    llm = _FakeLLM(
        [
            AIMessage(content="", tool_calls=[tc1]),
            AIMessage(content="", tool_calls=[tc2]),
            AIMessage(content="两个动作都换好了。"),
        ]
    )

    answer, results = resolve_with_tools(
        llm, [], PROFILE, tool_runner=fake_tool_runner
    )

    assert answer == "两个动作都换好了。"
    assert len(results) == 2
    assert [c["original_exercise"] for c in calls] == ["A", "B"]


# ============================================================
# 流式输出（#6）：stream_with_tools
# ============================================================


class _StreamBoundLLM:
    """模拟流式：按脚本依次 yield 一组 chunk。"""

    def __init__(self, turns: list[list[AIMessageChunk]]):
        self._turns = list(turns)
        self.stream_calls = 0

    def stream(self, messages: list[Any]):
        self.stream_calls += 1
        return iter(self._turns.pop(0))


class _StreamLLM:
    def __init__(self, turns: list[list[AIMessageChunk]]):
        self._turns = turns
        self.bound: _StreamBoundLLM | None = None

    def bind_tools(self, tools: list[Any]) -> _StreamBoundLLM:
        self.bound = _StreamBoundLLM(self._turns)
        return self.bound


def test_stream_without_tool_call_yields_text():
    llm = _StreamLLM(
        [
            [
                AIMessageChunk(content="你"),
                AIMessageChunk(content="好"),
                AIMessageChunk(content="！"),
            ]
        ]
    )

    pieces = list(stream_with_tools(llm, [], PROFILE))

    assert "".join(pieces) == "你好！"
    assert llm.bound is not None and llm.bound.stream_calls == 1


def test_stream_runs_tool_then_streams_final():
    captured: dict[str, Any] = {}

    def fake_tool_runner(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return FAKE_ALTERNATIVES

    tool_call_chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {
                "name": "substitute_exercise",
                "args": '{"original_exercise": "Barbell Bench Press", '
                '"reason": "没有杠铃", "equipment_available": ["bodyweight"]}',
                "id": "call-1",
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )
    llm = _StreamLLM(
        [
            [tool_call_chunk],
            [
                AIMessageChunk(content="可以换成"),
                AIMessageChunk(content=" Dumbbell Bench Press。"),
            ],
        ]
    )

    tool_results: list = []
    pieces = list(
        stream_with_tools(
            llm, [], PROFILE, tool_runner=fake_tool_runner, tool_results=tool_results
        )
    )

    assert "".join(pieces) == "可以换成 Dumbbell Bench Press。"
    assert tool_results == [FAKE_ALTERNATIVES]
    # 器械被画像强制覆盖为 dumbbell（模型越权 bodyweight 被忽略）
    assert captured["equipment_available"] == ["dumbbell"]
    assert llm.bound is not None and llm.bound.stream_calls == 2

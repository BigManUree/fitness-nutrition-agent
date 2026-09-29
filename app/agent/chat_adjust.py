"""对话调整页的工具调用循环（与 Streamlit 解耦，便于单测）。

流程：
    模型带 substitute_exercise 工具定义
      -> 若返回 tool_calls：执行 substitute_exercise（真实 MCP）
      -> 工具结果作为 ToolMessage 回填
      -> 再次调用模型，拿到最终自然语言回答
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.tools import substitute_exercise
from app.tools.schemas import SUBSTITUTE_EXERCISE_INPUT_SCHEMA

SUBSTITUTE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "substitute_exercise",
        "description": "根据伤病约束或器械限制，为指定动作查找替代方案。"
        "动作数据来自真实动作库，不编造。",
        "parameters": SUBSTITUTE_EXERCISE_INPUT_SCHEMA,
    },
}

# 工具执行器：在同步上下文里跑 async 工具
ToolRunner = Callable[..., dict[str, Any]]


def _shared_loop() -> asyncio.AbstractEventLoop:
    """模块级常驻循环：避免 Windows 下反复 asyncio.run 关闭循环，
    导致 MCP 异步连接报 "Event loop is closed"。"""
    loop = getattr(_shared_loop, "_loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _shared_loop._loop = loop  # type: ignore[attr-defined]
    return loop


def default_tool_runner(**kwargs: Any) -> dict[str, Any]:
    return _shared_loop().run_until_complete(substitute_exercise(**kwargs))


def resolve_with_tools(
    llm: Any,
    messages: list[Any],
    profile: dict[str, Any],
    *,
    tool_runner: ToolRunner | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """执行一轮"可能含工具调用"的对话。

    Args:
        llm: LangChain 聊天模型（无需提前 bind_tools，本函数会绑定）。
        messages: 已组装好的消息（System + 历史）。
        profile: 用户画像，用于强制约束器械范围。
        tool_runner: 工具执行方式（测试注入），默认 asyncio.run。

    Returns:
        (最终回答文本, 本次实际执行的 substitute_exercise 返回列表)
    """
    tool_runner = tool_runner or default_tool_runner
    llm_with_tools = llm.bind_tools([SUBSTITUTE_TOOL_DEFINITION])

    tool_results: list[dict[str, Any]] = []
    response: AIMessage = llm_with_tools.invoke(messages)

    # 循环：模型可能先返回工具调用，拿到结果后也可能再调一次
    while response.tool_calls:
        messages.append(response)
        for call in response.tool_calls:
            tool_output = _run_substitute(call, profile, tool_runner)
            tool_results.append(tool_output)
            messages.append(
                ToolMessage(
                    content=_serialize_tool_output(tool_output),
                    tool_call_id=call["id"],
                )
            )
        response = llm_with_tools.invoke(messages)

    return response.content, tool_results


def _run_substitute(
    call: dict[str, Any], profile: dict[str, Any], tool_runner: ToolRunner
) -> dict[str, Any]:
    """执行一次 substitute_exercise，强制器械范围来自画像。"""
    args = dict(call["args"]) if isinstance(call.get("args"), dict) else {}
    # 安全约束：器械只能来自画像，忽略模型自行提供的器械
    args["equipment_available"] = list(profile.get("equipment", []))
    args.setdefault("original_exercise", "")
    args.setdefault("reason", "")
    try:
        return tool_runner(**args)
    except Exception as exc:
        return {
            "original_exercise": args["original_exercise"],
            "alternatives": [],
            "total": 0,
            "source": "mcp",
            "note": f"动作替换工具执行失败：{exc}",
        }


def _serialize_tool_output(tool_output: dict[str, Any]) -> str:
    import json

    return json.dumps(tool_output, ensure_ascii=False)

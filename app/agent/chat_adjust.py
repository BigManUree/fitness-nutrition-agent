"""对话调整页的工具调用循环（与 Streamlit 解耦，便于单测）。

流程：
    模型带 substitute_exercise 工具定义
      -> 若返回 tool_calls：执行 substitute_exercise（真实 MCP）
      -> 工具结果作为 ToolMessage 回填
      -> 再次调用模型，拿到最终自然语言回答
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

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


CHAT_SYSTEM_TEMPLATE = """你是健身营养 Agent 的对话助手，帮助用户理解和微调"已生成的计划"。

规则：
1. 普通问答只能围绕下方计划内容；不要编造计划之外的新动作或新食物。
2. 当用户要求"替换/换掉某个动作"时，必须调用 substitute_exercise 工具，
   并根据工具返回的真实候选回答；工具返回为空时如实转述，不要自己编候选。
3. 不做医疗诊断，不推荐极端节食或危险动作。
4. 如果用户描述胸痛、头晕、严重关节疼痛、心悸等症状，回复：
   "我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。该症状属于需要重视的症状，建议你暂停训练，尽快咨询医生，由专业医师评估后再决定是否运动。"
5. 用简洁中文回答；列出候选动作时保留动作原名（英文）。

当前计划：
{plan_json}"""


def build_chat_system_prompt(plan: dict[str, Any]) -> str:
    """把当前计划 JSON 内嵌进对话系统提示（plan 随客户端请求带入）。"""
    return CHAT_SYSTEM_TEMPLATE.format(plan_json=json.dumps(plan, ensure_ascii=False))


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


def stream_with_tools(
    llm: Any,
    messages: list[Any],
    profile: dict[str, Any],
    *,
    tool_runner: ToolRunner | None = None,
    tool_results: list[dict[str, Any]] | None = None,
) -> Iterator[str]:
    """流式执行一轮"可能含工具调用"的对话（生成器产出文本增量）。

    与 resolve_with_tools 的区别：最终回答逐 token yield（供 Streamlit 边生成
    边显示）。子代调用循环在生成器内部执行，tool_results（如有）在生成器被
    消费期间就地填充，调用方可在 write_stream 结束后读取。

    Args:
        tool_results: 可选的外部列表，用于把本轮的 substitute_exercise 返回
            回传给调用方（供"应用到计划"）。

    Yields:
        模型回答的文本增量（工具调用轮次通常无正文，故不见增量）。
    """
    tool_runner = tool_runner or default_tool_runner
    llm_with_tools = llm.bind_tools([SUBSTITUTE_TOOL_DEFINITION])
    results = tool_results if tool_results is not None else []

    while True:
        # 流式生成一轮，并用 + 合并 AIMessageChunk 得到含 tool_calls 的完整消息
        full: AIMessageChunk | None = None
        for chunk in llm_with_tools.stream(messages):
            full = chunk if full is None else full + chunk
            text = _chunk_text(chunk)
            if text:
                yield text

        if full is None or not full.tool_calls:
            return

        # 本轮为工具调用：回填工具结果，进入下一轮
        messages.append(full)
        for call in full.tool_calls:
            tool_output = _run_substitute(call, profile, tool_runner)
            results.append(tool_output)
            messages.append(
                ToolMessage(
                    content=_serialize_tool_output(tool_output),
                    tool_call_id=call["id"],
                )
            )


def _chunk_text(chunk: Any) -> str:
    """从 AIMessageChunk 提取正文增量；兼容 str 与多模态内容块列表。"""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


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

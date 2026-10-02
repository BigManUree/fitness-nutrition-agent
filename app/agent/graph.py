"""LangGraph 工作流：
collect_profile → search_exercises → search_nutrition → generate_plan → validate_output

条件路由：
- 画像字段不全：直接结束（missing_fields 交由上层追问）。
- 校验不通过且未重试过：回到 generate_plan 再生成一次；否则结束。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.collect_profile import collect_profile
from app.agent.nodes.enrich_plan import enrich_plan
from app.agent.nodes.generate_plan import generate_plan
from app.agent.nodes.search_exercises import search_exercises_node
from app.agent.nodes.search_nutrition import search_nutrition_node
from app.agent.nodes.translate_plan import translate_plan
from app.agent.nodes.validate_output import validate_output
from app.agent.state import AgentState

MAX_PLAN_RETRIES = 1


def _route_after_profile(state: AgentState) -> str:
    if state.get("missing_fields"):
        return END
    return "search_exercises"


def _route_after_validate(state: AgentState) -> str:
    validation = state.get("validation") or {}
    if validation.get("valid"):
        return "enrich_plan"
    if state.get("retries", 0) < MAX_PLAN_RETRIES:
        return "generate_plan"
    return END


def build_graph(checkpointer: bool | MemorySaver | None = None):
    """编译工作流。

    Args:
        checkpointer: 会话记忆（CLAUDE.md 4.5）。
            - None（默认）: 使用内存版 MemorySaver，调用时必须带 thread_id；
            - MemorySaver 实例: 使用给定实例；
            - False: 不挂 checkpointer（单测/一次性脚本场景）。
    """
    graph = StateGraph(AgentState)

    graph.add_node("collect_profile", collect_profile)
    graph.add_node("search_exercises", search_exercises_node)
    graph.add_node("search_nutrition", search_nutrition_node)
    graph.add_node("generate_plan", generate_plan)
    graph.add_node("validate_output", validate_output)
    graph.add_node("enrich_plan", enrich_plan)
    graph.add_node("translate_plan", translate_plan)

    graph.add_edge(START, "collect_profile")
    graph.add_conditional_edges(
        "collect_profile",
        _route_after_profile,
        ["search_exercises", END],
    )
    graph.add_edge("search_exercises", "search_nutrition")
    graph.add_edge("search_nutrition", "generate_plan")
    graph.add_edge("generate_plan", "validate_output")
    graph.add_conditional_edges(
        "validate_output",
        _route_after_validate,
        ["generate_plan", "enrich_plan", END],
    )
    graph.add_edge("enrich_plan", "translate_plan")
    graph.add_edge("translate_plan", END)

    if checkpointer is False:
        return graph.compile()
    if checkpointer is None:
        checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# 默认图带内存会话记忆；调用方以 user_id 作为 thread_id。
agent_graph = build_graph()

"""LangGraph 全局状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # 输入
    user_id: str
    profile: dict[str, Any]

    # collect_profile 节点输出
    missing_fields: list[str]

    # 检索节点输出（均为 tools 层规范化后的 snake_case 数据）
    exercise_candidates: list[dict[str, Any]]
    nutrition_candidates: list[dict[str, Any]]

    # 生成与校验
    plan: dict[str, Any]
    validation: dict[str, Any]

    # 流程控制
    errors: list[str]
    retries: int

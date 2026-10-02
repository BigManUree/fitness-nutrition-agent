"""节点 4.5：确定性每餐定标（不调用 LLM）。

模型只负责"选哪些食物"，精确的克重定量交由本节点：按 compute_meal_budgets
给出的每餐热量目标，把该餐各食物的 amount_g 等比缩放到目标附近。
随后 validate_output 再做逐餐硬校验，把"定量不准"这一模型短板从 prompt
约束升级为代码层强制，显著降低因热量/蛋白不达标导致的回炉。
"""

from __future__ import annotations

from app.agent.nutrition_planning import (
    _COURSES,
    can_compute_targets,
    compute_meal_budgets,
    repair_course,
)
from app.agent.state import AgentState


def calibrate_meals(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    profile = state["profile"]

    # 画像不足以核算目标，或没有可处理的餐单：原样返回，不误伤
    if not can_compute_targets(profile) or not plan.get("daily_meals"):
        return AgentState()

    food_by_name = {it["name"]: it for it in state.get("nutrition_candidates", [])}
    budgets = compute_meal_budgets(profile)
    meals = plan.get("daily_meals") or {}

    new_meals: dict[str, list] = {}
    for course in _COURSES:
        items = meals.get(course) or []
        new_meals[course] = repair_course(items, budgets[course], food_by_name)

    # plan 键会整体覆盖，故保留原计划其余字段，仅替换 daily_meals
    return AgentState(plan={**plan, "daily_meals": new_meals})

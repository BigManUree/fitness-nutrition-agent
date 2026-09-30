"""节点 5：校验 LLM 输出是否只使用候选数据、结构是否完整。

编造动作处理闭环：
    提取计划全部动作名 → 与候选动作集合比对 → 不在集合中的标记为
    "编造动作"（fabricated_exercises）→ validation.valid=False，图路由
    回到 generate_plan 重试（错误信息随状态回传）→ 最多重试 1 次；
    仍失败则放弃本次结果，给用户明确提示（不降级为模型内置知识）。
"""

from __future__ import annotations

from app.agent.state import AgentState
from app.utils.performance_logger import log_performance

# 重试耗尽后给用户的降级提示（CLAUDE.md 4.4：宁可不给，不可错给）
RETRY_EXHAUSTED_MESSAGE = (
    "本次生成的计划未能通过校验（存在不在真实动作库中的内容），"
    "已重新生成 1 次仍不符合要求，故不提供该计划以免误导。"
    "请稍后重试，或调整训练目标、可用器械等筛选条件后再生成。"
)


@log_performance("validate_output")
def validate_output(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    profile = state["profile"]
    violations: list[str] = []

    exercise_names = {it["name"] for it in state.get("exercise_candidates", [])}
    food_names = {it["name"] for it in state.get("nutrition_candidates", [])}

    # 1) 训练天数与频率一致
    weekly = plan.get("weekly_plan", [])
    if not isinstance(weekly, list) or not weekly:
        violations.append("weekly_plan 缺失或为空")
    elif len(weekly) != profile["days_per_week"]:
        violations.append(
            f"训练天数 {len(weekly)} 与用户每周 {profile['days_per_week']} 天不符"
        )

    # 2) 提取全部动作名，与候选列表比对；不在候选中的标记为"编造动作"
    used_exercises: set[str] = set()
    fabricated_exercises: list[str] = []
    for day in weekly if isinstance(weekly, list) else []:
        for ex in day.get("exercises", []):
            name = ex.get("name", "")
            used_exercises.add(name)
            if name not in exercise_names:
                fabricated_exercises.append(name)
                violations.append(f"编造动作：{name}（不在检索候选动作列表中）")
            for field in ("sets", "reps", "rest"):
                if not ex.get(field):
                    violations.append(f"动作 {name} 缺少字段 {field}")

    # 3) 三餐结构与食物名
    meals = plan.get("daily_meals", {})
    for course in ("breakfast", "lunch", "dinner"):
        items = meals.get(course, [])
        if not items:
            violations.append(f"餐次 {course} 为空")
        for item in items:
            name = item.get("food", "")
            if name not in food_names:
                violations.append(f"食物不在候选库中（疑似编造）：{name}")
            if not item.get("amount"):
                violations.append(f"食物 {name} 缺少分量")

    if not plan.get("rationale"):
        violations.append("缺少 rationale 安排说明")

    # 惰性导入避免与 graph.py 的节点导入形成循环
    from app.agent.graph import MAX_PLAN_RETRIES

    retries = state.get("retries", 0)
    can_retry = retries < MAX_PLAN_RETRIES
    validation: dict = {
        "valid": not violations,
        "violations": violations,
        "fabricated_exercises": fabricated_exercises,
        "exercise_count": len(used_exercises),
        "retries": retries,
        "can_retry": can_retry,
    }
    # 重试机会已耗尽且仍不合法：降级为用户提示，不再回 generate_plan
    if violations and not can_retry:
        validation["user_message"] = RETRY_EXHAUSTED_MESSAGE

    # 回传 retries：节点返回只含本节点键，直接调用（非图合并）时路由也能读到
    return AgentState(validation=validation, retries=retries)

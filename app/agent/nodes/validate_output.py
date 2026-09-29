"""节点 5：校验 LLM 输出是否只使用候选数据、结构是否完整。"""

from __future__ import annotations

from app.agent.state import AgentState


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

    # 2) 动作名必须来自候选
    used_exercises: set[str] = set()
    for day in weekly if isinstance(weekly, list) else []:
        for ex in day.get("exercises", []):
            name = ex.get("name", "")
            used_exercises.add(name)
            if name not in exercise_names:
                violations.append(f"动作不在候选库中（疑似编造）：{name}")
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

    return AgentState(
        validation={
            "valid": not violations,
            "violations": violations,
            "exercise_count": len(used_exercises),
        }
    )

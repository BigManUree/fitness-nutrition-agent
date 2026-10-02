"""节点 5：校验 LLM 输出是否只使用候选数据、结构是否完整。

编造动作处理闭环：
    提取计划全部动作名 → 与候选动作集合比对 → 不在集合中的标记为
    "编造动作"（fabricated_exercises）→ validation.valid=False，图路由
    回到 generate_plan 重试（错误信息随状态回传）→ 最多重试 1 次；
    仍失败则放弃本次结果，给用户明确提示（不降级为模型内置知识）。
"""

from __future__ import annotations

from app.agent.nutrition_planning import (
    can_compute_targets,
    compute_meal_budgets,
    compute_meal_totals,
)
from app.agent.state import AgentState
from app.utils.performance_logger import log_performance

# 重试耗尽后给用户的降级提示（CLAUDE.md 4.4：宁可不给，不可错给）
RETRY_EXHAUSTED_MESSAGE = (
    "本次生成的计划未能通过校验（动作/食物的真实性，或三餐热量、蛋白质不达标），"
    "已重新生成 1 次仍不符合要求，故不提供该计划以免误导。"
    "请稍后重试，或调整训练目标、可用器械等筛选条件后再生成。"
)


def _nutrition_goal_check(
    profile: dict, meals: dict, food_by_name: dict
) -> tuple[list[str], list[str]]:
    """核算三餐热量与蛋白质是否达标，返回 (violations, warnings)。

    violations：硬性违规（热量偏差超 ±10%、蛋白质 <90%），触发回炉重生成；
    warnings：非阻断的可信度打标（如分量为体积估算），不打回炉，仅提示。
    画像不完整或所有食物都缺每 100g 数据时无法核算，返回空列表（不误伤）。
    """
    if not can_compute_targets(profile):
        return [], []

    # 无任何可核算热量（要么缺 amount_g、要么候选缺营养数据）——交给上面的
    # amount_g 缺失校验兜底，这里不再重复问责
    totals_all = compute_meal_totals(meals, food_by_name)
    if totals_all["calories"] <= 0:
        return [], []

    violations: list[str] = []
    warnings: list[str] = []

    # 逐餐硬校验：用每一餐自己的热量区间与蛋白最低线判定，精确指出是哪一餐不达标，
    # 回炉时模型才能定向调整该餐的 amount_g（各餐达标则全天合计必然达标）。
    budgets = compute_meal_budgets(profile)
    course_labels = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
    for course in ("breakfast", "lunch", "dinner"):
        budget = budgets[course]
        course_totals = compute_meal_totals({course: meals.get(course, [])}, food_by_name)
        label = course_labels[course]

        if not (budget["calorie_low"] <= course_totals["calories"] <= budget["calorie_high"]):
            direction = "偏高" if course_totals["calories"] > budget["calorie_high"] else "偏低"
            violations.append(
                f"{label}热量 {course_totals['calories']} 千卡，{direction}；该餐目标 {budget['calories']} 千卡"
                f"（允许 {budget['calorie_low']}–{budget['calorie_high']} 千卡），"
                "不在区间内，请调整该餐分量"
            )

        if course_totals["protein_g"] < budget["protein_min"]:
            violations.append(
                f"{label}蛋白质 {course_totals['protein_g']}g，低于该餐最低线 "
                f"{budget['protein_min']}g（目标 {budget['protein_g']}g），请为该餐增加高蛋白食物"
            )

    # 分量估算打标：parsed_volume 条目的热量为近似值，达标结论需打折，
    # 但不作为硬性违规（数据仍可能大致正确，回炉无法消除估算本身）
    if totals_all.get("estimated"):
        warnings.append(
            f"有 {totals_all['estimated']} 项食物的分量为体积估算（按水密度推算），"
            "实际热量可能偏离，汇总与达标判断仅供参考"
        )

    return violations, warnings


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
            for field in ("sets", "reps", "rest", "weight"):
                if not ex.get(field):
                    violations.append(f"动作 {name} 缺少字段 {field}")

    # 3) 三餐结构与食物名
    meals = plan.get("daily_meals", {})
    food_by_name = {it["name"]: it for it in state.get("nutrition_candidates", [])}
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
            if not item.get("amount_g"):
                violations.append(f"食物 {name} 缺少克重 amount_g（无法核算热量）")

    # 4) 热量与蛋白质目标闭环（确定性核算，服务端强制约束）
    goal_violations, goal_warnings = _nutrition_goal_check(
        profile, meals, food_by_name
    )
    violations += goal_violations

    if not plan.get("rationale"):
        violations.append("缺少 rationale 安排说明")

    # 惰性导入避免与 graph.py 的节点导入形成循环
    from app.agent.graph import MAX_PLAN_RETRIES

    retries = state.get("retries", 0)
    can_retry = retries < MAX_PLAN_RETRIES
    validation: dict = {
        "valid": not violations,
        "violations": violations,
        "warnings": goal_warnings,
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

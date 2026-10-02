"""营养目标确定性计算：Mifflin-St Jeor 估算 TDEE 与宏量目标。

纯代码、不调用 LLM（契合"服务端强制约束"原则）：热量目标、蛋白质目标、
以及三餐实际摄入的核算都由本模块完成，供 generate_plan（给模型目标）与
validate_output（硬校验 ±10% 热量 / 蛋白质达标）共用。

公式来源：Mifflin-St Jeor 基础代谢率（BMR）——
    男：10×体重kg + 6.25×身高cm − 5×年龄 + 5
    女：10×体重kg + 6.25×身高cm − 5×年龄 − 161
TDEE = BMR × 活动系数（由每周训练天数映射）。
目标热量 = TDEE + 目标差值（减脂缺口 / 增肌盈余 / 塑形与常规维持）。
"""

from __future__ import annotations

import re
from typing import Any

# 每周训练天数 -> 活动系数（取上限阈值，如 3 天以内按轻度活动 1.375）
_ACTIVITY_FACTOR_THRESHOLDS: tuple[tuple[int, float], ...] = (
    (1, 1.2),      # 基本久坐
    (3, 1.375),    # 轻度活动（1-3 天/周）
    (5, 1.55),     # 中度活动（3-5 天/周）
    (7, 1.725),    # 高度活动（6-7 天/周）
)

# 目标 -> 每日热量差值（相对 TDEE）
GOAL_CALORIE_DELTA: dict[str, int] = {
    "fat_loss": -500,        # 减脂：约 500 千卡缺口
    "muscle_gain": +300,     # 增肌：温和盈余
    "recomp": 0,             # 塑形/身体重组：维持
    "general_fitness": 0,    # 常规健身：维持
}

# 目标 -> 每公斤体重每日蛋白质克数
GOAL_PROTEIN_PER_KG: dict[str, float] = {
    "fat_loss": 2.0,         # 减脂偏高蛋白以保肌肉
    "muscle_gain": 1.8,
    "recomp": 1.8,
    "general_fitness": 1.4,
}

# 热量校验容差与蛋白质达标下限（比例）
CALORIE_TOLERANCE = 0.10
PROTEIN_MIN_RATIO = 0.90

_COURSES = ("breakfast", "lunch", "dinner")

# 分量克重按体积（假设水密度 1g/ml）估算的来源。这类食物的"每份多少克"并不可靠
# （对油/蜂蜜/糖浆等液体偏差尤大），会连带影响模型对分量的判断，因此核算时
# 只打标警示、不作静默采信（宁可不给，不可错给）。
ESTIMATED_WEIGHT_SOURCES = ("parsed_volume",)

# 计算目标所需的画像字段
TARGET_FIELDS = ("sex", "age", "height_cm", "weight_kg", "goal", "days_per_week")


def can_compute_targets(profile: dict[str, Any]) -> bool:
    """画像是否具备计算目标所需的全部字段（缺字段时调用方应跳过核算）。"""
    return all(profile.get(f) not in (None, "") for f in TARGET_FIELDS)


def compute_targets(profile: dict[str, Any]) -> dict[str, Any]:
    """按画像计算热量与蛋白质目标。

    需要 profile 含 sex / age / height_cm / weight_kg / goal / days_per_week；
    缺失关键字段时抛 KeyError，由调用方按需跳过（validate 会先做防御判断）。
    """
    sex = profile["sex"]
    age = profile["age"]
    height_cm = profile["height_cm"]
    weight_kg = profile["weight_kg"]
    goal = profile["goal"]
    days_per_week = profile["days_per_week"]

    if sex == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    activity_factor = 1.2
    for days_cap, factor in _ACTIVITY_FACTOR_THRESHOLDS:
        if days_per_week <= days_cap:
            activity_factor = factor
            break

    tdee = bmr * activity_factor
    target_calories = tdee + GOAL_CALORIE_DELTA.get(goal, 0)
    target_protein_g = weight_kg * GOAL_PROTEIN_PER_KG.get(goal, 1.6)

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "activity_factor": activity_factor,
        "target_calories": round(target_calories),
        "target_protein_g": round(target_protein_g, 1),
        "calorie_delta": GOAL_CALORIE_DELTA.get(goal, 0),
    }


# 全天目标在三餐间的分摊比例（早 30% / 午 40% / 晚 30%）。
# 午餐作为训练日主餐占比略高。各餐独立满足区间即可保证总量落在 ±10%。
MEAL_SHARE: dict[str, float] = {
    "breakfast": 0.30,
    "lunch": 0.40,
    "dinner": 0.30,
}


def compute_meal_budgets(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """把全天热量/蛋白质目标确定性分摊到早/午/晚三餐。

    返回每餐的热量中心值与 ±10% 允许区间、蛋白质目标与 90% 最低线，
    供 generate_plan 写入 prompt，要求模型按 amount_g 让每一餐都落在区间内
    （而不只是三餐合计），避免系统性把总量配高/配低。
    """
    targets = compute_targets(profile)
    total_cal = targets["target_calories"]
    total_protein = targets["target_protein_g"]

    # 先按比例四舍五入，再把取整余数补给占比最大的一餐，使各餐中心值之和
    # 严格等于全天目标（不出现 1 千卡漂移）。
    meal_cal = {course: round(total_cal * share) for course, share in MEAL_SHARE.items()}
    remainder = total_cal - sum(meal_cal.values())
    largest = max(MEAL_SHARE, key=MEAL_SHARE.get)
    meal_cal[largest] += remainder

    budgets: dict[str, dict[str, Any]] = {}
    for course, share in MEAL_SHARE.items():
        cal = meal_cal[course]
        meal_protein = round(total_protein * share, 1)
        budgets[course] = {
            "share": share,
            "calories": cal,
            "calorie_low": round(cal * (1 - CALORIE_TOLERANCE)),
            "calorie_high": round(cal * (1 + CALORIE_TOLERANCE)),
            "protein_g": meal_protein,
            "protein_min": round(meal_protein * PROTEIN_MIN_RATIO, 1),
        }
    return budgets


# 缩放系数允许范围：防止把分量调到不现实的值（过小/过大）。
SCALE_MIN_FACTOR = 0.4
SCALE_MAX_FACTOR = 2.5


def scale_course_to_targets(
    course_items: list[dict[str, Any]],
    target_calories: int,
    food_by_name: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    """按热量目标等比缩放一餐内各食物的 amount_g（不修改原对象）。

    模型负责选择食物，精确定量交由本函数：系数 = 目标热量 / 该餐当前热量，
    再钳制到 [SCALE_MIN_FACTOR, SCALE_MAX_FACTOR]，逐食物乘算并取整。
    无可核算热量（缺数据/缺 amount_g）时不调整，返回系数 1.0。
    """
    current_calories = 0.0
    for item in course_items:
        amount_g = item.get("amount_g")
        food = food_by_name.get(item.get("food", "")) or {}
        calories = (food.get("per_100g") or {}).get("calories")
        if amount_g and calories is not None:
            current_calories += calories * amount_g / 100

    if current_calories <= 0:
        return list(course_items), 1.0

    factor = target_calories / current_calories
    factor = min(max(factor, SCALE_MIN_FACTOR), SCALE_MAX_FACTOR)

    scaled = []
    for item in course_items:
        new_g = max(1, round((item.get("amount_g") or 0) * factor))
        updated = {**item, "amount_g": new_g}
        # 原文案是纯克重（如 "50g"）时同步，避免与新 amount_g 矛盾；
        # "2个""1根"等非克重描述保留不动
        old_amount = item.get("amount")
        if isinstance(old_amount, str) and re.fullmatch(r"\s*[\d.]+\s*g", old_amount):
            updated["amount"] = f"{new_g}g"
        scaled.append(updated)
    return scaled, factor


# 可作为"蛋白锚点"的食物每 100g 蛋白质下限（挑真正高蛋白、而非中等的）。
ANCHOR_MIN_PROTEIN_PER_100G = 12.0
_REPAIR_ITERATIONS = 4


def sum_items(items: list[dict], food_by_name: dict[str, dict]) -> dict[str, float]:
    """对"一份食物列表"直接求和（不依赖餐次键名），返回热量/蛋白质。"""
    calories = 0.0
    protein = 0.0
    for item in items:
        amount_g = item.get("amount_g")
        per_100g = (food_by_name.get(item.get("food", "")) or {}).get("per_100g") or {}
        if not amount_g:
            continue
        if per_100g.get("calories") is not None:
            calories += per_100g["calories"] * amount_g / 100
        if per_100g.get("protein") is not None:
            protein += per_100g["protein"] * amount_g / 100
    return {"calories": round(calories), "protein_g": round(protein, 1)}


def _totals_for_course(items: list[dict], food_by_name: dict) -> dict[str, Any]:
    return sum_items(items, food_by_name)


def repair_course(
    items: list[dict[str, Any]],
    budget: dict[str, Any],
    food_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """把一餐修复到热量区间内且蛋白质达标。

    1) 先按热量目标等比缩放（见 scale_course_to_targets）；
    2) 若蛋白仍不足，从候选池中选"蛋白/热量"效率最高的食物作为锚点
       （锚点是候选池中的真实食物，非编造），迭代确定锚点克重，并把
       其余食物的热量回配到（目标 − 锚点热量），直到蛋白与热量同时满足。
    无可用锚点时返回仅热量定标的结果，交由 validate_output 判定。
    """
    scaled, _ = scale_course_to_targets(items, budget["calories"], food_by_name)
    if _totals_for_course(scaled, food_by_name)["protein_g"] >= budget["protein_min"]:
        return scaled

    used = {i.get("food") for i in scaled}
    anchors = [
        (name, f["per_100g"])
        for name, f in food_by_name.items()
        if name not in used
        and (f.get("per_100g") or {}).get("calories") is not None
        and (f.get("per_100g") or {}).get("protein", 0) >= ANCHOR_MIN_PROTEIN_PER_100G
    ]
    if not anchors:
        return scaled
    anchors.sort(key=lambda nf: nf[1]["protein"] / nf[1]["calories"], reverse=True)
    anchor_name, anchor_p100 = anchors[0]

    anchor_g = 1
    current = scaled
    for _ in range(_REPAIR_ITERATIONS):
        anchor_cal = anchor_p100["calories"] * anchor_g / 100
        remaining = round(budget["calories"] - anchor_cal)

        base = [i for i in scaled if i.get("food") != anchor_name]
        if remaining <= 0:
            base_scaled = [
                {**i, "amount_g": max(1, round((i.get("amount_g") or 0) * 0.15))}
                for i in base
            ]
        else:
            base_scaled, _ = scale_course_to_targets(base, remaining, food_by_name)

        anchor_item = {
            "food": anchor_name,
            "amount": f"{anchor_g}g",
            "amount_g": anchor_g,
            "note": "为补足该餐蛋白质而添加",
        }
        current = base_scaled + [anchor_item]
        totals = _totals_for_course(current, food_by_name)
        if (
            totals["protein_g"] >= budget["protein_min"]
            and budget["calorie_low"] <= totals["calories"] <= budget["calorie_high"]
        ):
            return current

        # 蛋白还差多少（含 10% 缓冲）→ 反推锚点克重，进入下一轮
        gap = budget["protein_min"] - totals["protein_g"]
        if gap > 0:
            anchor_g = max(anchor_g, round(anchor_g + gap * 100 / anchor_p100["protein"] * 1.1))

    return current


def compute_meal_totals(
    meals: dict[str, Any], food_by_name: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """核算三餐实际热量与蛋白质。

    按每餐食物的 amount_g（克）乘以其候选 per_100g 的 calories/protein 累加；
    缺少 amount_g 或缺少每 100g 数据（per_100g.calories 为 None）的条目分别
    计入 missing_amount / unknown，供调用方判断是否可核算。
    estimated 计入分量为体积估算（parsed_volume）的条目数，供调用方打标。
    """
    total_calories = 0.0
    total_protein = 0.0
    missing_amount = 0
    unknown = 0
    estimated = 0

    for course in _COURSES:
        for item in meals.get(course, []) or []:
            amount_g = item.get("amount_g")
            if not amount_g:
                missing_amount += 1
                continue
            food = food_by_name.get(item.get("food", "")) or {}
            if food.get("weight_source") in ESTIMATED_WEIGHT_SOURCES:
                estimated += 1
            per_100g = food.get("per_100g") or {}
            calories = per_100g.get("calories")
            if calories is None:
                unknown += 1
                continue
            total_calories += calories * amount_g / 100
            protein = per_100g.get("protein")
            if protein is not None:
                total_protein += protein * amount_g / 100

    return {
        "calories": round(total_calories),
        "protein_g": round(total_protein, 1),
        "missing_amount": missing_amount,
        "unknown": unknown,
        "estimated": estimated,
    }
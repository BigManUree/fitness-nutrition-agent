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
"""营养目标确定性计算测试：Mifflin-St Jeor TDEE、目标热量/蛋白、三餐核算。"""

from __future__ import annotations

import pytest
from app.agent.nutrition_planning import (
    can_compute_targets,
    compute_meal_budgets,
    compute_meal_totals,
    compute_targets,
    repair_course,
    scale_course_to_targets,
)

MALE_PROFILE = {
    "sex": "male",
    "age": 28,
    "height_cm": 175,
    "weight_kg": 72,
    "goal": "muscle_gain",
    "days_per_week": 3,
}
FEMALE_PROFILE = {
    "sex": "female",
    "age": 30,
    "height_cm": 165,
    "weight_kg": 60,
    "goal": "fat_loss",
    "days_per_week": 5,
}


def test_mifflin_st_jeor_bmr_male():
    # 男：10*72 + 6.25*175 - 5*28 + 5 = 720 + 1093.75 - 140 + 5 = 1678.75
    targets = compute_targets(MALE_PROFILE)
    assert targets["bmr"] == 1679


def test_mifflin_st_jeor_bmr_female():
    # 女：10*60 + 6.25*165 - 5*30 - 161 = 600 + 1031.25 - 150 - 161 = 1320.25
    targets = compute_targets(FEMALE_PROFILE)
    assert targets["bmr"] == 1320


def test_activity_factor_by_days():
    assert compute_targets(dict(MALE_PROFILE, days_per_week=1))["activity_factor"] == 1.2
    assert compute_targets(dict(MALE_PROFILE, days_per_week=3))["activity_factor"] == 1.375
    assert compute_targets(dict(MALE_PROFILE, days_per_week=5))["activity_factor"] == 1.55
    assert compute_targets(dict(MALE_PROFILE, days_per_week=7))["activity_factor"] == 1.725


def test_goal_deltas_apply():
    # 增肌：TDEE + 300；减脂：TDEE - 500
    gain = compute_targets(MALE_PROFILE)
    assert gain["calorie_delta"] == 300
    assert gain["target_calories"] == round(gain["tdee"] + 300)

    loss = compute_targets(FEMALE_PROFILE)
    assert loss["calorie_delta"] == -500
    assert loss["target_calories"] == round(loss["tdee"] - 500)


def test_protein_target_by_goal():
    # 减脂 2.0g/kg、增肌 1.8g/kg、塑形维持 1.8、常规 1.4
    assert compute_targets(FEMALE_PROFILE)["target_protein_g"] == 60 * 2.0
    assert compute_targets(MALE_PROFILE)["target_protein_g"] == 72 * 1.8
    for goal, per_kg in (("recomp", 1.8), ("general_fitness", 1.4)):
        assert compute_targets(dict(MALE_PROFILE, goal=goal))["target_protein_g"] == 72 * per_kg


def test_can_compute_targets_requires_all_fields():
    assert can_compute_targets(MALE_PROFILE) is True
    incomplete = {k: v for k, v in MALE_PROFILE.items() if k != "height_cm"}
    assert can_compute_targets(incomplete) is False


def test_meal_budgets_split_daily_targets_across_three_courses():
    targets = compute_targets(MALE_PROFILE)
    budgets = compute_meal_budgets(MALE_PROFILE)

    assert set(budgets) == {"breakfast", "lunch", "dinner"}
    # 分摊比例：早 30% / 午 40% / 晚 30%，合计 100%
    assert sum(b["share"] for b in budgets.values()) == pytest.approx(1.0)
    assert budgets["breakfast"]["share"] == 0.30
    assert budgets["lunch"]["share"] == 0.40
    assert budgets["dinner"]["share"] == 0.30

    # 每餐热量中心值之和等于全天目标；每餐给出 ±10% 区间
    cal_sum = sum(b["calories"] for b in budgets.values())
    assert cal_sum == targets["target_calories"]
    lunch = budgets["lunch"]
    # 午餐为占比最大一餐，承担取整余数，故与 40% 中心值相差不超过 1
    expected_lunch = round(targets["target_calories"] * 0.40)
    assert abs(lunch["calories"] - expected_lunch) <= 1
    assert lunch["calorie_low"] == round(lunch["calories"] * 0.90)
    assert lunch["calorie_high"] == round(lunch["calories"] * 1.10)

    # 每餐蛋白质目标与最低线（90%）
    assert budgets["lunch"]["protein_g"] == round(targets["target_protein_g"] * 0.40, 1)
    assert budgets["lunch"]["protein_min"] == round(
        budgets["lunch"]["protein_g"] * 0.90, 1
    )


def test_scale_course_shares_amount_g_down_to_calorie_target():
    # 该餐当前 1000g * 2.6 = 2600 千卡，目标 1800 千卡 → 系数约 0.69（不触发钳制）
    items = [{"food": "FOOD", "amount": "1000g", "amount_g": 1000}]
    food_by_name = {"FOOD": {"per_100g": {"calories": 260, "protein": 13.0}}}

    scaled, factor = scale_course_to_targets(items, 1800, food_by_name)
    assert factor == pytest.approx(1800 / 2600, abs=0.01)
    assert scaled[0]["amount_g"] == round(1000 * factor)
    # 纯克重文案随新克重同步，原对象不被原地修改
    assert scaled[0]["amount"] == f"{scaled[0]['amount_g']}g"
    assert items[0]["amount_g"] == 1000
    assert items[0]["amount"] == "1000g"
    # 缩放后该餐热量落在目标附近
    assert abs(260 * scaled[0]["amount_g"] / 100 - 1800) <= 15


def test_scale_course_clamps_extreme_factor():
    # 当前热量极小、需要极大系数时，钳制到上限，避免产出不现实的分量
    items = [{"food": "FOOD", "amount_g": 10}]
    food_by_name = {"FOOD": {"per_100g": {"calories": 50}}}
    _, factor = scale_course_to_targets(items, 3000, food_by_name)
    assert factor == 2.5  # 被钳到上限


def test_scale_course_noop_when_no_computable_calories():
    items = [{"food": "X", "amount_g": 100}]
    scaled, factor = scale_course_to_targets(items, 800, {"X": {"per_100g": {}}})
    assert factor == 1.0
    assert scaled[0]["amount_g"] == 100


def test_repair_course_adds_high_protein_anchor_and_keeps_calories_in_range():
    # 早餐只有香蕉（高碳水、极低蛋白）：热量在区间但蛋白严重不足
    budget = {"calories": 866, "calorie_low": 779, "calorie_high": 953,
              "protein_g": 38.9, "protein_min": 35.0}
    items = [{"food": "BANANA", "amount_g": 400}]  # 356 千卡 / 4.4g 蛋白
    food_by_name = {
        "BANANA": {"per_100g": {"calories": 89, "protein": 1.1}},
        "CHICKEN": {"per_100g": {"calories": 165, "protein": 20.4}},
    }

    repaired = repair_course(items, budget, food_by_name)
    t = compute_meal_totals({"breakfast": repaired}, food_by_name)
    assert t["protein_g"] >= budget["protein_min"]            # 蛋白达标
    assert budget["calorie_low"] <= t["calories"] <= budget["calorie_high"]  # 热量仍在区间
    assert any(i["food"] == "CHICKEN" for i in repaired)      # 锚点来自候选池，非编造


def test_repair_course_passes_through_meal_that_already_meets_targets():
    budget = {"calories": 1800, "calorie_low": 1620, "calorie_high": 1980,
              "protein_g": 90, "protein_min": 81}
    # 该餐已达标：不应强行塞入蛋白锚点
    items = [{"food": "FOOD", "amount_g": 692}]  # 约1800千卡 / 90g蛋白
    food_by_name = {"FOOD": {"per_100g": {"calories": 260, "protein": 13.0}}}
    repaired = repair_course(items, budget, food_by_name)
    assert [i["food"] for i in repaired] == ["FOOD"]


def test_repair_course_final_nudge_closes_sub_gram_protein_gap():
    # 迭代耗尽后若仅差不到 1g 蛋白且热量仍在上限内，必须给锚点补差，
    # 不得把 53.8/54.0 这种临界不合法餐次交出去。
    budget = {"calories": 900, "calorie_low": 810, "calorie_high": 990,
              "protein_g": 60, "protein_min": 54.0}
    # 米饭 500g：650 千卡 / 13.5g 蛋白；鸡胸补差约 199g → 328 千卡 / 40.6g
    items = [{"food": "RICE", "amount_g": 500}]
    food_by_name = {
        "RICE": {"per_100g": {"calories": 130, "protein": 2.7}},
        "CHICKEN": {"per_100g": {"calories": 165, "protein": 20.4}},
    }
    repaired = repair_course(items, budget, food_by_name)
    t = compute_meal_totals({"lunch": repaired}, food_by_name)
    assert t["protein_g"] >= budget["protein_min"]
    assert t["calories"] <= budget["calorie_high"]


def test_repair_course_tolerates_null_protein_in_candidate():
    # MCP/USDA 数据中 protein 可能为 None（字段存在但值为 null）：
    # 该候选不应作为蛋白锚点，也不能让整个修复崩溃（曾导致 502）。
    budget = {"calories": 866, "calorie_low": 779, "calorie_high": 953,
              "protein_g": 38.9, "protein_min": 35.0}
    items = [{"food": "BANANA", "amount_g": 400}]
    food_by_name = {
        "BANANA": {"per_100g": {"calories": 89, "protein": 1.1}},
        "MYSTERY": {"per_100g": {"calories": 200, "protein": None}},
        "CHICKEN": {"per_100g": {"calories": 165, "protein": 20.4}},
    }

    repaired = repair_course(items, budget, food_by_name)
    assert all(i["food"] != "MYSTERY" for i in repaired)
    assert any(i["food"] == "CHICKEN" for i in repaired)


def test_compute_meal_totals_sums_by_amount_g():
    meals = {
        "breakfast": [{"food": "EGG", "amount_g": 100}],
        "lunch": [{"food": "CHICKEN", "amount_g": 200}],
        "dinner": [{"food": "RICE", "amount_g": 100}],
    }
    food_by_name = {
        "EGG": {"per_100g": {"calories": 155, "protein": 13.0}},
        "CHICKEN": {"per_100g": {"calories": 165, "protein": 20.4}},
        "RICE": {"per_100g": {"calories": 130, "protein": 2.7}},
    }
    totals = compute_meal_totals(meals, food_by_name)
    # 热量：155 + 165*2 + 130 = 615；蛋白：13 + 20.4*2 + 2.7 = 56.5
    assert totals["calories"] == 615
    assert totals["protein_g"] == pytest.approx(56.5)
    assert totals["missing_amount"] == 0
    assert totals["unknown"] == 0
    assert totals["estimated"] == 0


def test_compute_meal_totals_flags_missing_and_unknown():
    meals = {
        "breakfast": [{"food": "EGG", "amount_g": 50}],
        "lunch": [{"food": "NO_DATA", "amount_g": 100}],
        "dinner": [{"food": "NO_AMOUNT"}],
    }
    food_by_name = {
        "EGG": {"per_100g": {"calories": 155, "protein": 13.0}},
        "NO_DATA": {"per_100g": {}},  # 缺热量数据
    }
    totals = compute_meal_totals(meals, food_by_name)
    assert totals["calories"] == 78  # 155 * 50/100 取整
    assert totals["missing_amount"] == 1
    assert totals["unknown"] == 1
    assert totals["estimated"] == 0


def test_compute_meal_totals_flags_estimated_volume_weights():
    meals = {
        "breakfast": [{"food": "OLIVE_OIL", "amount_g": 15}],
        "lunch": [{"food": "EGG", "amount_g": 100}],
    }
    food_by_name = {
        # 油类常用体积估算（假设水密度 1g/ml，实际约 0.92），分量克重不可靠
        "OLIVE_OIL": {
            "per_100g": {"calories": 884, "protein": 0.0},
            "weight_source": "parsed_volume",
        },
        "EGG": {
            "per_100g": {"calories": 155, "protein": 13.0},
            "weight_source": "column",
        },
    }
    totals = compute_meal_totals(meals, food_by_name)
    # 热量不受可信度影响仍正常累加：884*0.15 + 155 = 287.6 -> 288
    assert totals["calories"] == 288
    assert totals["estimated"] == 1
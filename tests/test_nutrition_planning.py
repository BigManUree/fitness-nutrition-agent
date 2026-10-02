"""营养目标确定性计算测试：Mifflin-St Jeor TDEE、目标热量/蛋白、三餐核算。"""

from __future__ import annotations

import pytest
from app.agent.nutrition_planning import (
    can_compute_targets,
    compute_meal_totals,
    compute_targets,
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
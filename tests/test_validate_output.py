"""validate_output 编造动作检测与重试闭环测试。

覆盖：
    动作名提取与候选比对；编造动作标记；
    首次失败回 generate_plan（错误信息随状态回传）；
    最多重试 1 次，仍失败则降级为用户提示；
    generate_plan 重试运行能看到上轮 violations 并递增 retries。
"""

from __future__ import annotations

from typing import Any

from app.agent.graph import _route_after_validate
from app.agent.nodes import generate_plan as gp_module
from app.agent.nodes.validate_output import (
    RETRY_EXHAUSTED_MESSAGE,
    _nutrition_goal_check,
    validate_output,
)

PROFILE = {"days_per_week": 2, "equipment": ["dumbbell"]}
CANDIDATES = ["Dumbbell Press", "Goblet Squat", "Push-up"]


def _day(exercise: str) -> dict[str, Any]:
    return {
        "day": 1,
        "exercises": [
            {"name": exercise, "sets": 3, "reps": "10", "rest": "60秒",
             "weight": "每只手8-12kg"}
        ],
    }


def _state(exercise_names: list[str], retries: int = 0) -> dict[str, Any]:
    plan = {
        "weekly_plan": [_day(n) for n in exercise_names],
        "daily_meals": {
            course: [{"food": "EGG", "amount": "1个", "amount_g": 50}]
            for course in ("breakfast", "lunch", "dinner")
        },
        "rationale": "说明",
    }
    return {
        "profile": PROFILE,
        "plan": plan,
        "exercise_candidates": [{"name": n} for n in CANDIDATES],
        "nutrition_candidates": [{"name": "EGG"}],
        "retries": retries,
    }


# ============================================================
# 动作提取与候选比对
# ============================================================


def test_all_names_in_candidates_pass():
    result = validate_output(_state(["Dumbbell Press", "Push-up"]))
    validation = result["validation"]

    assert validation["valid"] is True
    assert validation["fabricated_exercises"] == []
    assert validation["exercise_count"] == 2


def test_name_not_in_candidates_marked_as_fabrication():
    result = validate_output(_state(["Dumbbell Press", "银河碎星深蹲"]))
    validation = result["validation"]

    assert validation["valid"] is False
    assert validation["fabricated_exercises"] == ["银河碎星深蹲"]
    assert any("编造动作：银河碎星深蹲" in v for v in validation["violations"])


def test_multiple_fabricated_names_collected():
    result = validate_output(_state(["虚构动作A", "虚构动作B"]))
    assert result["validation"]["fabricated_exercises"] == ["虚构动作A", "虚构动作B"]


# ============================================================
# 重试触发：首次失败回 generate_plan
# ============================================================


def test_first_failure_can_retry_and_routes_back():
    result = validate_output(_state(["虚构动作A"], retries=0))
    validation = result["validation"]

    assert validation["can_retry"] is True
    assert "user_message" not in validation
    assert _route_after_validate(result) == "generate_plan"


def test_violations_are_carried_in_state_for_regenerate():
    """回传 generate_plan 的状态里必须带 violations，模型才能定向修正。"""
    result = validate_output(_state(["虚构动作A"], retries=0))

    assert result["validation"]["violations"]
    assert all("编造动作" in v for v in result["validation"]["violations"] if "虚构" in v)


# ============================================================
# 最多重试 1 次：仍失败则降级提示
# ============================================================


def test_retry_exhausted_falls_back_to_user_message():
    result = validate_output(_state(["虚构动作A"], retries=1))
    validation = result["validation"]

    assert validation["valid"] is False
    assert validation["can_retry"] is False
    assert validation["user_message"] == RETRY_EXHAUSTED_MESSAGE
    # 图路由结束，不再回 generate_plan
    assert _route_after_validate(result) == "__end__"


def test_fallback_message_contains_no_fabricated_exercise_data():
    result = validate_output(_state(["虚构动作A"], retries=1))
    message = result["validation"]["user_message"]

    assert "虚构动作A" not in message  # 不把编造内容返回给用户
    assert "稍后重试" in message or "调整" in message


# ============================================================
# generate_plan 重试运行：接收 violations、递增 retries
# ============================================================


class _FakeResponse:
    content = "{}"
    usage_metadata = None


async def test_regenerate_receives_violations_and_increments_retries(monkeypatch):
    captured: dict[str, Any] = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return _FakeResponse()

    monkeypatch.setattr(gp_module, "get_llm", lambda: _FakeLLM())

    state = {
        "profile": PROFILE,
        "exercise_candidates": [{"name": n} for n in CANDIDATES],
        "nutrition_candidates": [],
        "validation": {
            "valid": False,
            "violations": ["编造动作：虚构动作A（不在检索候选动作列表中）"],
        },
        "retries": 0,
    }

    result = await gp_module.generate_plan(state)

    # 重试反馈出现在发给模型的最后一条消息中
    user_text = captured["messages"][-1].content
    assert "上一次生成未通过校验" in user_text
    assert "虚构动作A" in user_text
    assert "禁止使用列表外的任何名称" in user_text
    # 本次重试运行 retries 递增为 1
    assert result["retries"] == 1


async def test_first_generation_does_not_add_retry_feedback(monkeypatch):
    captured: dict[str, Any] = {}

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return _FakeResponse()

    monkeypatch.setattr(gp_module, "get_llm", lambda: _FakeLLM())

    state = {
        "profile": PROFILE,
        "exercise_candidates": [],
        "nutrition_candidates": [],
    }
    result = await gp_module.generate_plan(state)

    assert "上一次生成未通过校验" not in captured["messages"][-1].content
    assert result.get("retries", 0) == 0


# ============================================================
# 热量/蛋白质目标闭环（确定性核算）
# ============================================================

FULL_PROFILE = {
    "sex": "male",
    "age": 28,
    "height_cm": 175.0,
    "weight_kg": 72.0,
    "goal": "muscle_gain",
    "days_per_week": 3,
    "equipment": ["dumbbell"],
}

# 每 100g：260 千卡、13g 蛋白。1000g 合计 2600 千卡 / 130g 蛋白，
# 落在目标（约 2608 千卡 / 129.6g）的 ±10% 与 ≥90% 区间内。
_FOOD = {"per_100g": {"calories": 260, "protein": 13.0}}


def _meals(total_g: int, per_100g: dict = _FOOD) -> dict:
    return {
        "breakfast": [{"food": "FOOD", "amount_g": round(total_g * 0.4)}],
        "lunch": [{"food": "FOOD", "amount_g": round(total_g * 0.3)}],
        "dinner": [{"food": "FOOD", "amount_g": round(total_g * 0.3)}],
    }, {"FOOD": per_100g}


def test_nutrition_goal_check_passes_when_in_range():
    meals, food_by_name = _meals(1000)
    violations, warnings = _nutrition_goal_check(FULL_PROFILE, meals, food_by_name)
    assert violations == []
    assert warnings == []


def test_nutrition_goal_check_flags_calorie_overrun():
    meals, food_by_name = _meals(1500)  # 3900 千卡，远超上限
    violations, _ = _nutrition_goal_check(FULL_PROFILE, meals, food_by_name)
    assert any("总热量" in v for v in violations)


def test_nutrition_goal_check_flags_protein_shortfall():
    low_protein = {"per_100g": {"calories": 260, "protein": 1.0}}
    meals, food_by_name = _meals(1000, low_protein)  # 10g 蛋白，远低于 90% 目标
    violations, _ = _nutrition_goal_check(FULL_PROFILE, meals, food_by_name)
    assert any("总蛋白质" in v for v in violations)


def test_nutrition_goal_check_skips_when_profile_incomplete():
    meals, food_by_name = _meals(1000)
    assert _nutrition_goal_check(PROFILE, meals, food_by_name) == ([], [])


def test_nutrition_goal_check_warns_on_estimated_volume():
    """分量为体积估算（parsed_volume）时：热量仍达标，但附可信度打标（不违规）。"""
    estimated_food = {"per_100g": {"calories": 260, "protein": 13.0},
                      "weight_source": "parsed_volume"}
    meals, food_by_name = _meals(1000, estimated_food)
    violations, warnings = _nutrition_goal_check(FULL_PROFILE, meals, food_by_name)
    assert violations == []  # 热量/蛋白仍在区间内，不触发回炉
    assert any("体积估算" in w for w in warnings)


def test_validate_output_fails_on_missing_amount_g():
    plan = {
        "weekly_plan": [_day("Dumbbell Press")],
        "daily_meals": {
            course: [{"food": "EGG", "amount": "1个"}]
            for course in ("breakfast", "lunch", "dinner")
        },
        "rationale": "说明",
    }
    state = {
        "profile": PROFILE,
        "plan": plan,
        "exercise_candidates": [{"name": "Dumbbell Press"}],
        "nutrition_candidates": [{"name": "EGG", "per_100g": {"calories": 155}}],
    }
    result = validate_output(state)
    violations = " ".join(result["validation"]["violations"])
    assert "缺少克重 amount_g" in violations

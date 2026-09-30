"""enrich_plan 节点测试：MCP 动作指导确定性注入。"""

from __future__ import annotations

from app.agent.graph import _route_after_validate
from app.agent.nodes.enrich_plan import WEIGHT_ADJUST_GUIDANCE, enrich_plan


def _state() -> dict:
    plan = {
        "weekly_plan": [
            {
                "day": 1,
                "exercises": [
                    {"name": "Barbell Squat", "sets": 4, "reps": "8-10",
                     "weight": "20-40kg", "rpe": "RPE 7-8"}
                ],
            }
        ]
    }
    candidates = [
        {
            "name": "Barbell Squat",
            "form_tips": ["Drive through your heels", "Keep chest up"],
            "common_mistakes": ["Knees caving inward"],
            "safety": "Use a squat rack with safety bars.",
        }
    ]
    return {"plan": plan, "exercise_candidates": candidates}


def test_tips_injected_verbatim_from_candidate():
    result = enrich_plan(_state())
    ex = result["plan"]["weekly_plan"][0]["exercises"][0]

    assert ex["form_tips"] == ["Drive through your heels", "Keep chest up"]
    assert ex["common_mistakes"] == ["Knees caving inward"]
    assert ex["safety"] == "Use a squat rack with safety bars."
    assert result["plan"]["weight_guidance"] == WEIGHT_ADJUST_GUIDANCE


def test_unknown_exercise_gets_no_tips_without_crash():
    state = _state()
    state["exercise_candidates"] = []

    result = enrich_plan(state)
    ex = result["plan"]["weekly_plan"][0]["exercises"][0]
    assert ex.get("form_tips", []) == []


def test_valid_validation_routes_to_enrich():
    assert _route_after_validate({"validation": {"valid": True}}) == "enrich_plan"

"""app/tools 工具函数测试。

MCP 传输层通过 monkeypatch 打桩，不依赖真实 MCP 服务：
    - 正向：正常返回、规范化、空结果、截断；
    - 校验：非法入参被 JSON Schema 拒绝；
    - 异常：首次连接失败自动重试，两次都失败抛 ToolError。
"""

from typing import Any

import pytest
from app.mcp.http_client import McpConnectionError
from app.tools import (
    ExerciseToolError,
    search_exercises,
    search_nutrition,
    substitute_exercise,
)
from jsonschema import ValidationError

# ---- 样例数据（字段名与 MCP 原始返回一致） ----

EXERCISE_RAW_CHEST_DUMBBELL = {
    "id": "Dumbbell_Bench_Press",
    "name": "Dumbbell Bench Press",
    "primaryMuscles": ["pectoralis major sternal head", "pectoralis major clavicular head"],
    "secondaryMuscles": ["triceps brachii long head", "deltoid anterior"],
    "equipment": "dumbbell",
    "force": "push",
    "level": "beginner",
    "mechanic": "compound",
    "category": "strength",
}

EXERCISE_RAW_BACK_AS_SECONDARY = {
    "id": "Some_Row",
    "name": "Some Row",
    "primaryMuscles": ["latissimus dorsi"],
    "secondaryMuscles": ["pectoralis major sternal head"],
    "equipment": "cable",
    "level": "intermediate",
    "category": "strength",
}

NUTRITION_RAW_CHICKEN = {
    "id": "usda_2187885",
    "name": "CHICKEN BREAST",
    "brand": "Giant Eagle, Inc.",
    "serving_size": "284g",
    "basis": "per_serving",
    "basis_weight_g": 284,
    "weight_source": "column",
    "per_100g": {"calories": 165, "protein": 20.4, "fat": 8.1, "carbs": 1.06},
    "calories": 469,
    "protein": 57.9,
    "fat": 23,
    "carbs": 3,
}


# ============================================================
# search_exercises
# ============================================================

async def test_search_exercises_normalizes_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"data": [EXERCISE_RAW_CHEST_DUMBBELL], "total": 1}

    monkeypatch.setattr("app.tools.exercise_tools.exerciseapi_client.search_exercises", fake_call)

    result = await search_exercises(muscle="chest", equipment="dumbbell")

    assert result["source"] == "mcp"
    assert result["total"] == 1
    item = result["items"][0]
    # 原始 camelCase 已规范化为 snake_case
    assert item["id"] == "Dumbbell_Bench_Press"
    assert item["primary_muscles"][0] == "pectoralis major sternal head"
    assert item["difficulty"] == "beginner"
    assert "note" not in result


async def test_search_exercises_primary_only_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": [EXERCISE_RAW_CHEST_DUMBBELL, EXERCISE_RAW_BACK_AS_SECONDARY],
            "total": 2,
        }

    monkeypatch.setattr("app.tools.exercise_tools.exerciseapi_client.search_exercises", fake_call)

    result = await search_exercises(muscle="chest", primary_only=True)

    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "Dumbbell_Bench_Press"


async def test_search_exercises_empty_returns_note(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"data": [], "total": 0}

    monkeypatch.setattr("app.tools.exercise_tools.exerciseapi_client.search_exercises", fake_call)

    result = await search_exercises(muscle="chest", equipment="nonexistent")

    assert result["items"] == []
    assert "未找到" in result["note"]


async def test_search_exercises_truncates_to_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"data": [EXERCISE_RAW_CHEST_DUMBBELL] * 5, "total": 5}

    monkeypatch.setattr("app.tools.exercise_tools.exerciseapi_client.search_exercises", fake_call)

    result = await search_exercises(muscle="chest", limit=3)

    assert len(result["items"]) == 3


async def test_search_exercises_rejects_bad_limit() -> None:
    with pytest.raises(ValidationError):
        await search_exercises(muscle="chest", limit=0)


async def test_search_exercises_rejects_unknown_param() -> None:
    # 未知字段在函数签名层即被拒绝（Schema 的 additionalProperties:false
    # 对直接传入 dict 的调用方同样生效，见 test_input_schema_additional_properties）
    with pytest.raises(TypeError):
        await search_exercises(muscle="chest", bogus=1)  # type: ignore[arg-type]


def test_input_schema_additional_properties() -> None:
    from app.tools.schemas import SEARCH_EXERCISES_INPUT_SCHEMA
    from app.utils.validators import is_valid

    assert not is_valid({"muscle": "chest", "bogus": 1}, SEARCH_EXERCISES_INPUT_SCHEMA)


async def test_search_exercises_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    async def flaky_call(arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        if len(calls) == 1:
            raise McpConnectionError("connection refused")
        return {"data": [EXERCISE_RAW_CHEST_DUMBBELL], "total": 1}

    monkeypatch.setattr("app.tools.exercise_tools.exerciseapi_client.search_exercises", flaky_call)

    result = await search_exercises(muscle="chest")

    assert len(calls) == 2
    assert len(result["items"]) == 1


async def test_search_exercises_raises_after_two_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_call(arguments: dict[str, Any]) -> dict[str, Any]:
        raise McpConnectionError("connection refused")

    monkeypatch.setattr("app.tools.exercise_tools.exerciseapi_client.search_exercises", failing_call)

    with pytest.raises(ExerciseToolError, match="connection refused"):
        await search_exercises(muscle="chest")


# ============================================================
# substitute_exercise
# ============================================================

EXERCISE_RAW_BENCH_BARBELL = {
    "id": "Barbell_Bench_Press",
    "name": "Barbell Bench Press",
    "primaryMuscles": ["pectoralis major sternal head"],
    "secondaryMuscles": ["triceps brachii long head"],
    "equipment": "barbell",
    "force": "push",
    "level": "beginner",
    "mechanic": "compound",
    "category": "strength",
}

EXERCISE_RAW_BENCH_DUMBBELL = {
    "id": "Dumbbell_Bench_Press",
    "name": "Dumbbell Bench Press",
    "primaryMuscles": ["pectoralis major clavicular head"],
    "secondaryMuscles": ["triceps brachii long head"],
    "equipment": "dumbbell",
    "force": "push",
    "level": "beginner",
    "mechanic": "compound",
    "category": "strength",
}


async def _fake_substitute_call(arguments: dict[str, Any]) -> dict[str, Any]:
    # 第一段：按名字定位原动作
    if "query" in arguments:
        return {"data": [EXERCISE_RAW_BENCH_BARBELL], "total": 1}
    # 第二段：按肌群 + 器械拉候选池
    if arguments.get("equipment") == "dumbbell":
        data = [EXERCISE_RAW_BENCH_DUMBBELL]
    elif arguments.get("equipment") == "barbell":
        data = [EXERCISE_RAW_BENCH_BARBELL]
    else:
        data = []
    return {"data": data, "total": len(data)}


async def test_substitute_exercise_finds_alternative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.exercise_tools.exerciseapi_client.search_exercises",
        _fake_substitute_call,
    )

    result = await substitute_exercise(
        original_exercise="Barbell Bench Press",
        reason="没有杠铃",
        equipment_available=["dumbbell"],
    )

    assert result["source"] == "mcp"
    assert result["total"] == 1
    alt = result["alternatives"][0]
    assert alt["id"] == "Dumbbell_Bench_Press"
    # 原动作即使同池出现也必须排除
    assert all(a["id"] != "Barbell_Bench_Press" for a in result["alternatives"])
    assert any("哑铃" in reason or "dumbbell" in reason for reason in alt["match_reasons"])


async def test_substitute_exercise_unknown_original_returns_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"data": [], "total": 0}

    monkeypatch.setattr(
        "app.tools.exercise_tools.exerciseapi_client.search_exercises", fake_call
    )

    result = await substitute_exercise(
        original_exercise="天马流星拳", reason="随便换"
    )

    assert result["alternatives"] == []
    assert "未在动作库中找到" in result["note"]


async def test_substitute_exercise_requires_reason() -> None:
    with pytest.raises(ValidationError):
        await substitute_exercise(original_exercise="Barbell Bench Press", reason="")


async def test_substitute_exercise_raises_after_mcp_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_call(arguments: dict[str, Any]) -> dict[str, Any]:
        raise McpConnectionError("connection refused")

    monkeypatch.setattr(
        "app.tools.exercise_tools.exerciseapi_client.search_exercises", failing_call
    )

    with pytest.raises(ExerciseToolError):
        await substitute_exercise(
            original_exercise="Barbell Bench Press", reason="没有杠铃"
        )


# ============================================================
# search_nutrition
# ============================================================

async def test_search_nutrition_normalizes_raw(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    async def fake_call(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        return [NUTRITION_RAW_CHICKEN]

    monkeypatch.setattr("app.tools.nutrition_tools.nutrition_client.search_nutrition", fake_call)

    result = await search_nutrition("chicken breast", db_path=tmp_path / "cache.db")

    assert result["source"] == "mcp"
    item = result["items"][0]
    assert item["id"] == "usda_2187885"
    assert item["serving_weight_g"] == 284
    # 顶层为按份缩放后的值
    assert item["calories"] == 469
    # per_100g 保留标准值，且结构固定（缺失营养字段补 None）
    assert item["per_100g"]["calories"] == 165
    assert item["per_100g"]["fiber"] is None


async def test_search_nutrition_empty_returns_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    async def fake_call(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr("app.tools.nutrition_tools.nutrition_client.search_nutrition", fake_call)

    result = await search_nutrition("xxxxx", db_path=tmp_path / "cache.db")

    assert result["items"] == []
    assert "未找到" in result["note"]


async def test_search_nutrition_requires_query() -> None:
    with pytest.raises(ValidationError):
        await search_nutrition("")


async def test_search_nutrition_retries_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    calls: list[int] = []

    async def flaky_call(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        calls.append(1)
        if len(calls) == 1:
            raise McpConnectionError("connection refused")
        return [NUTRITION_RAW_CHICKEN]

    monkeypatch.setattr("app.tools.nutrition_tools.nutrition_client.search_nutrition", flaky_call)

    result = await search_nutrition("chicken breast", db_path=tmp_path / "cache.db")

    assert len(calls) == 2
    assert result["total"] == 1

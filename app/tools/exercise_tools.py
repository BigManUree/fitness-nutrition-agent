"""动作检索工具：search_exercises。

链路：
    入参 JSON Schema 校验
      -> 调 exerciseapi MCP（连接/JSON 异常自动重试 1 次）
      -> 规范化为内部 snake_case 结构
      -> primary_only 二次过滤 + 截断
      -> 出参 JSON Schema 校验

安全约束（CLAUDE.md 4.1）：动作全部来自 MCP 返回，本函数不编造任何动作。
"""

from typing import Any

from jsonschema import validate

from app.mcp import exerciseapi_client
from app.mcp.http_client import McpConnectionError, McpProtocolError
from app.tools.schemas import (
    SEARCH_EXERCISES_INPUT_SCHEMA,
    SEARCH_EXERCISES_OUTPUT_SCHEMA,
    SUBSTITUTE_EXERCISE_INPUT_SCHEMA,
    SUBSTITUTE_EXERCISE_OUTPUT_SCHEMA,
)
from app.utils.validators import partition_valid

DEFAULT_LIMIT = 20
SUBSTITUTE_DEFAULT_LIMIT = 5
# 每种器械反查候选时的拉取量（候选池越大，排序后质量越稳）
_SUBSTITUTE_POOL_PER_EQUIPMENT = 20

class ExerciseToolError(RuntimeError):
    """动作工具重试后仍失败时抛出，由上层节点决定是否降级。"""


async def search_exercises(
    query: str | None = None,
    muscle: str | None = None,
    category: str | None = None,
    equipment: str | None = None,
    difficulty: str | None = None,
    limit: int = DEFAULT_LIMIT,
    primary_only: bool = False,
) -> dict[str, Any]:
    """搜索动作库。

    Args:
        query: 自由文本（动作名/关键词）。
        muscle: 肌群，如 "chest"。
        category: 动作分类。
        equipment: 器械，如 "dumbbell"。
        difficulty: beginner / intermediate / advanced。
        limit: 返回条数（1-100）。
        primary_only: 仅保留以 muscle 为主肌群的动作。

    Returns:
        ``{"items": [...], "total": int, "source": "mcp", "note"?: str}``

    Raises:
        jsonschema.ValidationError: 入参不合法。
        ExerciseToolError: MCP 重试 1 次后仍失败。
    """
    payload = _build_payload(
        query=query,
        muscle=muscle,
        category=category,
        equipment=equipment,
        difficulty=difficulty,
        limit=limit,
        primary_only=primary_only,
    )
    validate(payload, SEARCH_EXERCISES_INPUT_SCHEMA)

    raw = await _call_with_retry(payload)

    raw_items, total = _extract(raw)
    items = [_normalize_item(raw_item) for raw_item in raw_items]

    if primary_only and muscle:
        items = [item for item in items if _muscle_is_primary(muscle, item)]

    # MCP 自身应已限制条数，这里再兜底截断（CLAUDE.md：控制输出规模）
    items = items[: payload["limit"]]

    item_schema = SEARCH_EXERCISES_OUTPUT_SCHEMA["properties"]["items"]["items"]
    items, dropped = partition_valid(items, item_schema)

    note: str | None = None
    if not items:
        note = "未找到匹配的动作，建议调整肌群、器械或难度等筛选条件。"
    elif dropped:
        note = f"有 {dropped} 条返回数据格式异常，已忽略。"

    result: dict[str, Any] = {
        "items": items,
        # total 用 MCP 报告值；经过滤/丢弃后实际条数可能更少
        "total": total if total is not None else len(items),
        "source": "mcp",
    }
    if note:
        result["note"] = note

    validate(result, SEARCH_EXERCISES_OUTPUT_SCHEMA)
    return result


async def substitute_exercise(
    original_exercise: str,
    reason: str,
    equipment_available: list[str] | None = None,
    limit: int = SUBSTITUTE_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """为指定动作查找替代动作。

    流程（全程不编造）：
        1. 按名字在 MCP 中定位原动作，取其主肌群/难度/分类；
        2. 用同一肌群 + 用户可用器械反查候选；
        3. 排除原动作，按"同器械/难度相近/力学类型一致"排序。

    Raises:
        jsonschema.ValidationError: 入参不合法。
        ExerciseToolError: MCP 重试 1 次后仍失败。
    """
    equipment_available = equipment_available or []
    payload: dict[str, Any] = {
        "original_exercise": original_exercise,
        "reason": reason,
        "equipment_available": equipment_available,
        "limit": limit,
    }
    validate(payload, SUBSTITUTE_EXERCISE_INPUT_SCHEMA)

    # 1) 定位原动作
    original = await _find_original(original_exercise)

    note: str | None = None
    if original is None:
        # 原动作不在动作库：无法可靠判断训练目标，宁可不替换也不凭名字猜
        result = {
            "original_exercise": original_exercise,
            "alternatives": [],
            "total": 0,
            "source": "mcp",
            "note": "未在动作库中找到该动作，无法确定其目标肌群，故不提供替代，"
            "请核对动作名称（可使用英文名）。",
        }
        validate(result, SUBSTITUTE_EXERCISE_OUTPUT_SCHEMA)
        return result

    muscle_key = _muscle_key_from_item(original)
    if muscle_key is None:
        result = {
            "original_exercise": original_exercise,
            "alternatives": [],
            "total": 0,
            "source": "mcp",
            "note": "无法识别该动作的目标肌群，故不提供替代。",
        }
        validate(result, SUBSTITUTE_EXERCISE_OUTPUT_SCHEMA)
        return result

    # 2) 同肌群 + 各可用器械反查（去重保序）
    equipment_list = equipment_available or [None]
    candidates = await _collect_alternatives(muscle_key, equipment_list)

    # 3) 排除原动作，打分排序
    alternatives = [
        _annotate_match(item, original, equipment_available)
        for item in candidates
        if item["id"] != original["id"] and item["name"].lower() != original["name"].lower()
    ]
    alternatives.sort(key=_rank_key, reverse=True)
    alternatives = alternatives[:limit]

    if not alternatives:
        note = "未找到符合器械限制的同肌群替代动作，建议放宽器械或难度条件。"

    result = {
        "original_exercise": original["name"],
        "alternatives": alternatives,
        "total": len(alternatives),
        "source": "mcp",
    }
    if note:
        result["note"] = note

    validate(result, SUBSTITUTE_EXERCISE_OUTPUT_SCHEMA)
    return result


async def _find_original(name: str) -> dict[str, Any] | None:
    """按名字在动作库中定位原动作：精确名优先，否则取首条。"""
    raw = await _call_with_retry({"query": name, "limit": 10})
    raw_items, _ = _extract(raw)
    items = [_normalize_item(raw_item) for raw_item in raw_items]
    target = name.strip().lower()
    for item in items:
        if item["name"].lower() == target:
            return item
    return items[0] if items else None


async def _collect_alternatives(
    muscle_key: str, equipment_list: list[str | None]
) -> list[dict[str, Any]]:
    """按肌群（+每种器械）拉候选池，按 id 去重保序。"""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for equipment in equipment_list:
        search_payload: dict[str, Any] = {
            "muscle": muscle_key,
            "limit": _SUBSTITUTE_POOL_PER_EQUIPMENT,
        }
        if equipment:
            search_payload["equipment"] = equipment
        raw = await _call_with_retry(search_payload)
        raw_items, _ = _extract(raw)
        for raw_item in raw_items:
            item = _normalize_item(raw_item)
            if item["id"] not in seen and _muscle_is_primary(muscle_key, item):
                seen.add(item["id"])
                merged.append(item)
    return merged


def _annotate_match(
    item: dict[str, Any], original: dict[str, Any], equipment_available: list[str]
) -> dict[str, Any]:
    """给候选附上可读的匹配理由（不改写动作数据本身）。"""
    reasons = ["同一目标肌群"]
    if equipment_available and item["equipment"] in equipment_available:
        reasons.append(f"使用你有的器械：{item['equipment']}")
    if item["difficulty"] == original["difficulty"]:
        reasons.append("难度相近")
    if item["mechanic"] and item["mechanic"] == original["mechanic"]:
        reasons.append("力学类型一致")
    annotated = dict(item)
    annotated["match_reasons"] = reasons
    return annotated


def _rank_key(item: dict[str, Any]) -> tuple[int, int, int]:
    """排序分：复合动作优先、有明确器械优先、难度 beginner/intermediate/advanced。"""
    mechanic_score = 1 if item.get("mechanic") == "compound" else 0
    equipment_score = 1 if item.get("equipment") else 0
    difficulty_rank = {"beginner": 0, "intermediate": 1, "advanced": 2}.get(
        item.get("difficulty") or "", 1
    )
    return mechanic_score, equipment_score, -difficulty_rank


def _muscle_key_from_item(item: dict[str, Any]) -> str | None:
    """从动作的解剖学主肌群反查 MCP 使用的肌群检索词（chest/back/...）。"""
    for muscle in item["primary_muscles"]:
        lowered = muscle.lower()
        for key, aliases in _MUSCLE_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                return key
    return None


def _build_payload(**kwargs: Any) -> dict[str, Any]:
    """组装 MCP 入参：去掉 None，primary_only 是工具层开关，不下发。"""
    payload = {key: value for key, value in kwargs.items() if value is not None}
    payload.pop("primary_only", None)
    return payload


async def _call_with_retry(payload: dict[str, Any]) -> Any:
    """调用 MCP；连接失败或 JSON 解析失败时重试 1 次（CLAUDE.md 4.4）。"""
    try:
        return await exerciseapi_client.search_exercises(payload)
    except (McpConnectionError, McpProtocolError):
        try:
            return await exerciseapi_client.search_exercises(payload)
        except (McpConnectionError, McpProtocolError) as exc:
            raise ExerciseToolError(str(exc)) from exc


def _extract(raw: Any) -> tuple[list[dict[str, Any]], int | None]:
    """从 MCP 返回中提取 (动作列表, total)。

    MCP 当前返回 ``{"data": [...], "total": n}``；
    同时兼容直接返回列表的情况。
    """
    if isinstance(raw, dict):
        data = raw.get("data", [])
        total = raw.get("total")
        return list(data), total if isinstance(total, int) else None
    if isinstance(raw, list):
        return list(raw), None
    return [], None


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    """单条 MCP 原始动作 -> 内部结构。"""
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "primary_muscles": list(raw.get("primaryMuscles") or []),
        "secondary_muscles": list(raw.get("secondaryMuscles") or []),
        "equipment": raw.get("equipment"),
        "category": raw.get("category"),
        "difficulty": raw.get("level"),
        "force": raw.get("force"),
        "mechanic": raw.get("mechanic"),
    }


# 检索词（MCP muscle 入参） -> 解剖学名中的关键词。
# MCP 返回的是 "pectoralis major sternal head" 这类解剖名，
# 直接用 "chest" 做子串匹配会漏掉，因此需要别名映射。
_MUSCLE_ALIASES: dict[str, tuple[str, ...]] = {
    "chest": ("pectoralis",),
    "back": ("latissimus", "trapezius", "teres"),
    "shoulders": ("deltoid",),
    "biceps": ("biceps",),
    "triceps": ("triceps",),
    "abs": ("rectus abdominis", "oblique"),
    "core": ("rectus abdominis", "oblique"),
    "glutes": ("gluteus",),
    "quads": ("quadriceps",),
    "hamstrings": ("hamstring",),
    "calves": ("gastrocnemius", "soleus"),
    "forearms": ("forearm",),
}


def _muscle_is_primary(muscle: str, item: dict[str, Any]) -> bool:
    """目标肌群是否出现在主肌群中（按别名做小写包含匹配）。"""
    keywords = _MUSCLE_ALIASES.get(muscle.lower(), (muscle.lower(),))
    primaries = [primary.lower() for primary in item["primary_muscles"]]
    return any(any(keyword in primary for keyword in keywords) for primary in primaries)

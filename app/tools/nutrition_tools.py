"""营养检索工具：search_nutrition。

链路与 exercise_tools 一致：
    入参 JSON Schema 校验
      -> 调 nutrition-mcp（连接/JSON 异常自动重试 1 次）
      -> 规范化为内部 snake_case 结构 + 截断
      -> 出参 JSON Schema 校验

MCP 实测返回为 JSON 数组，单项示例：
    {"id": "usda_2187885", "name": "CHICKEN BREAST", "brand": "...",
     "serving_size": "284g", "basis": "per_serving", "basis_weight_g": 284,
     "per_100g": {"calories": 165, "protein": 20.4, "fat": 8.1, "carbs": 1.06},
     "calories": 469, "protein": 57.9, "fat": 23, "carbs": 3}
"""

from typing import Any

from jsonschema import validate

from app.mcp import nutrition_client
from app.mcp.http_client import McpConnectionError, McpProtocolError
from app.tools.schemas import SEARCH_NUTRITION_INPUT_SCHEMA, SEARCH_NUTRITION_OUTPUT_SCHEMA
from app.utils.validators import partition_valid

DEFAULT_LIMIT = 10

# 宏量营养素字段（per_100g 与单条顶层共用）
_MACRO_KEYS = ("calories", "protein", "fat", "carbs", "fiber", "sugar", "sodium")


class NutritionToolError(RuntimeError):
    """营养工具重试后仍失败时抛出，由上层节点决定是否降级。"""


async def search_nutrition(query: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """查询食物营养数据。

    Args:
        query: 食物名称（必填，不能为空串）。
        limit: 返回条数（1-50）。

    Returns:
        ``{"items": [...], "total": int, "source": "mcp", "note"?: str}``

    Raises:
        jsonschema.ValidationError: 入参不合法（如 query 缺失）。
        NutritionToolError: MCP 重试 1 次后仍失败。
    """
    payload = {"query": query, "limit": limit}
    validate(payload, SEARCH_NUTRITION_INPUT_SCHEMA)

    raw = await _call_with_retry(payload)

    raw_items = _extract(raw)
    items = [_normalize_item(raw_item) for raw_item in raw_items if isinstance(raw_item, dict)]
    items = items[:limit]

    item_schema = SEARCH_NUTRITION_OUTPUT_SCHEMA["properties"]["items"]["items"]
    items, dropped = partition_valid(items, item_schema)

    note: str | None = None
    if not items:
        note = "未找到匹配的食物，建议换一个食物名称或放宽筛选条件。"
    elif dropped:
        note = f"有 {dropped} 条返回数据格式异常，已忽略。"

    result: dict[str, Any] = {
        "items": items,
        "total": len(items),
        "source": "mcp",
    }
    if note:
        result["note"] = note

    validate(result, SEARCH_NUTRITION_OUTPUT_SCHEMA)
    return result


async def _call_with_retry(payload: dict[str, Any]) -> Any:
    """调用 MCP；连接失败或 JSON 解析失败时重试 1 次（CLAUDE.md 4.4）。"""
    try:
        return await nutrition_client.search_nutrition(payload)
    except (McpConnectionError, McpProtocolError):
        try:
            return await nutrition_client.search_nutrition(payload)
        except (McpConnectionError, McpProtocolError) as exc:
            raise NutritionToolError(str(exc)) from exc


def _extract(raw: Any) -> list[dict[str, Any]]:
    """从 MCP 返回中提取食物列表。

    MCP 当前直接返回数组；同时兼容 {"data": [...]} 的信封格式。
    """
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        return list(raw["data"])
    return []


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    """单条 MCP 原始食物 -> 内部结构。

    分量相关宏量素取顶层（已按 basis 缩放），缺失字段补 None；
    per_100g 始终保留，供节点按自定义克数重算。
    """
    raw_per_100g = raw.get("per_100g") if isinstance(raw.get("per_100g"), dict) else {}
    # 缺失的宏量素补 None，保证 per_100g 结构固定、可直接取用
    per_100g = {key: raw_per_100g.get(key) for key in _MACRO_KEYS}

    item: dict[str, Any] = {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "brand": raw.get("brand"),
        "basis": raw.get("basis"),
        "serving_size": raw.get("serving_size"),
        "serving_weight_g": raw.get("basis_weight_g", raw.get("serving_weight_g")),
        "per_100g": per_100g,
    }
    for key in _MACRO_KEYS:
        item[key] = raw.get(key)
    return item

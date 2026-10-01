"""节点 3：按用户饮食偏好/目标检索多样化的候选食物，按过敏原过滤。

相比写死 8 个 STAPLE_QUERIES，这里把"偏好/目标 → 查询词"做成映射：素食者
检索豆腐/扁豆/鹰嘴豆等植物蛋白，低碳偏好减少谷物、多检索蔬菜与优质脂肪。
候选池覆盖蛋白质 / 主食 / 蔬果三大类各多源，解决此前食物种类单一的问题。
"""

from __future__ import annotations

import asyncio

from app.agent.state import AgentState
from app.tools.nutrition_tools import search_nutrition
from app.utils.performance_logger import log_performance

# 荤食蛋白质来源（默认画像）
_OMNIVORE_PROTEIN = [
    "chicken breast", "egg", "beef", "salmon", "shrimp",
    "greek yogurt", "cottage cheese",
]

# 植物蛋白来源（素食/纯素画像：不含肉蛋奶，希腊酸奶为蛋奶素可选）
_VEGETARIAN_PROTEIN = [
    "tofu", "lentil", "chickpea", "edamame", "tempeh", "black bean",
]

# 主食 / 碳水
_GRAINS = ["oatmeal", "brown rice", "quinoa", "sweet potato", "whole wheat bread"]

# 蔬菜与水果
_VEG_FRUIT = [
    "broccoli", "spinach", "tomato", "carrot", "banana", "apple", "blueberry",
]

# 低碳水偏好：替换谷物为更多蔬菜与优质脂肪来源
_LOW_CARB_EXTRAS = ["cauliflower", "avocado", "zucchini", "bell pepper"]

# 素食判定关键词（针对中文自由文本偏好做归一化）
_VEGETARIAN_KEYWORDS = (
    "素食", "纯素", "蛋奶素", "植物基", "vegetarian", "vegan", "plant-based", "不吃肉",
)
_LOW_CARB_KEYWORDS = ("低碳", "低碳水", "生酮", "keto", "ketogenic", "低碳饮食")


def build_queries(preferences: list[str]) -> list[str]:
    """按饮食偏好生成候选食物的检索词表（去重保序）。"""
    prefs = " ".join(preferences).lower()

    vegetarian = any(k in prefs for k in _VEGETARIAN_KEYWORDS)
    protein = _VEGETARIAN_PROTEIN if vegetarian else _OMNIVORE_PROTEIN

    low_carb = any(k in prefs for k in _LOW_CARB_KEYWORDS)
    grains = _GRAINS[:1] if low_carb else _GRAINS
    extras = _LOW_CARB_EXTRAS if low_carb else []

    queries = protein + grains + _VEG_FRUIT + extras

    # 去重保序（防止未来关键词重叠导致重复检索）
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


PER_FOOD_LIMIT = 2

# nutrition-mcp 经 stateless 桥接时 stdio 启动较脆（SSE stream ended），
# 顺序执行最稳；候选池扩充后单次生成计划检索时间会相应增加。
MAX_CONCURRENCY = 1


@log_performance("search_nutrition")
async def search_nutrition_node(state: AgentState) -> AgentState:
    profile = state["profile"]
    allergies = [a.lower() for a in profile.get("allergies", [])]
    queries = build_queries(profile.get("dietary_preferences", []))
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def for_food(query: str) -> list[dict] | str:
        async with semaphore:
            try:
                result = await search_nutrition(query, limit=PER_FOOD_LIMIT)
            except Exception as exc:
                return f"{query}: {exc}"
            return result.get("items", [])

    results = await asyncio.gather(*(for_food(q) for q in queries))

    candidates: dict[str, dict] = {}
    errors: list[str] = []
    for result in results:
        if isinstance(result, str):
            errors.append(result)
            continue
        for item in result:
            name = item.get("name", "")
            haystack = f"{name} {item.get('brand') or ''}".lower()
            if any(allergen and allergen in haystack for allergen in allergies):
                continue
            # 同名取第一条
            candidates.setdefault(name, item)

    return AgentState(
        nutrition_candidates=list(candidates.values()),
        errors=errors,
    )
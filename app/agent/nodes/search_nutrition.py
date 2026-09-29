"""节点 3：并行检索常见高蛋白/主食/蔬果候选食物，按过敏原过滤。"""

from __future__ import annotations

import asyncio

from app.agent.state import AgentState
from app.tools.nutrition_tools import search_nutrition

# 覆盖增肌/减脂餐单常见食材（中文库命中率高的基础食物）。
# 经 stateless 桥接每次查询都要拉起一个 stdio 子进程，故保持精简。
# 本地种子库为英文库；中文词命中率为 0。
STAPLE_QUERIES = [
    "chicken breast", "egg", "milk", "oatmeal", "brown rice",
    "broccoli", "banana", "salmon",
]

PER_FOOD_LIMIT = 2

# nutrition-mcp 经 stateless 桥接时 stdio 启动较脆（SSE stream ended），
# 顺序执行最稳；8 次查询约 40s。
MAX_CONCURRENCY = 1


async def search_nutrition_node(state: AgentState) -> AgentState:
    profile = state["profile"]
    allergies = [a.lower() for a in profile.get("allergies", [])]
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def for_food(query: str) -> list[dict] | str:
        async with semaphore:
            try:
                result = await search_nutrition(query, limit=PER_FOOD_LIMIT)
            except Exception as exc:
                return f"{query}: {exc}"
            return result.get("items", [])

    results = await asyncio.gather(*(for_food(q) for q in STAPLE_QUERIES))

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

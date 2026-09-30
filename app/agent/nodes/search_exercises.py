"""节点 2：按主要肌群并行检索候选动作，并按用户器械过滤。"""

from __future__ import annotations

import asyncio

from app.agent.state import AgentState
from app.tools.exercise_tools import search_exercises
from app.tools.profile_tools import GYM_EQUIPMENT

# 一周分化需要覆盖的大肌群（使用 tools 层支持的别名）
MUSCLE_GROUPS = [
    "chest", "back", "shoulders", "biceps", "triceps",
    "quads", "hamstrings", "glutes", "abs",
]

# MCP 数据中自重动作的 equipment 取值
BODYWEIGHT = "body only"

PER_GROUP_LIMIT = 12

# supergateway stateless 模式每次调用都拉起一个 npx stdio 子进程，
# 并发过高会产生大量 node 进程并互相争抢，必须限流。
MAX_CONCURRENCY = 3


async def search_exercises_node(state: AgentState) -> AgentState:
    profile = state["profile"]
    profile_equipment = profile.get("equipment", [])
    # 健身房：全部器械可用，跳过器械过滤
    full_gym = GYM_EQUIPMENT in profile_equipment
    allowed_equipment = set(profile_equipment) | {BODYWEIGHT}
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def for_group(muscle: str) -> list[dict]:
        async with semaphore:
            try:
                result = await search_exercises(muscle=muscle, limit=PER_GROUP_LIMIT)
            except Exception as exc:  # 单肌群失败不应拖垮整体
                return [{"__error__": f"{muscle}: {exc}"}]
            return result.get("items", [])

    groups = await asyncio.gather(*(for_group(m) for m in MUSCLE_GROUPS))

    candidates: dict[str, dict] = {}
    errors: list[str] = []
    for items in groups:
        for item in items:
            if "__error__" in item:
                errors.append(item["__error__"])
                continue
            if full_gym or item.get("equipment") in allowed_equipment:
                candidates[item["name"]] = item

    return AgentState(
        exercise_candidates=list(candidates.values()),
        errors=errors,
    )

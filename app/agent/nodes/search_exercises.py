"""节点 2：按主要肌群并行检索候选动作，并按用户器械过滤。"""

from __future__ import annotations

import asyncio

from app.agent.state import AgentState
from app.tools.exercise_tools import search_exercises
from app.tools.profile_tools import GYM_EQUIPMENT
from app.utils.performance_logger import log_performance

# 一周分化需要覆盖的大肌群（使用 tools 层支持的别名）
MUSCLE_GROUPS = [
    "chest", "back", "shoulders", "biceps", "triceps",
    "quads", "hamstrings", "glutes", "abs",
]

# 全身分化（每周训练 ≤2 天）只需覆盖的主要复合肌群：
# 孤立肌（二头/三头/臀）靠推/拉/蹲/硬拉等复合动作顺带训练，不再单独检索。
FULL_BODY_GROUPS = [
    "chest", "back", "shoulders", "quads", "hamstrings", "abs",
]


def muscle_groups_for(days_per_week: int) -> list[str]:
    """按周训练天数决定检索肌群子集。

    ≤2 天走全身分化，只查复合肌群（省 MCP 调用与 prompt token）；
    ≥3 天（推拉腿 / 上下 / 更细分）需覆盖全部大肌群，维持全量检索。
    """
    if days_per_week <= 2:
        return FULL_BODY_GROUPS
    return MUSCLE_GROUPS

# MCP 数据中自重动作的 equipment 取值
BODYWEIGHT = "body only"

PER_GROUP_LIMIT = 12

# supergateway stateless 模式每次调用都拉起一个 npx stdio 子进程，
# 并发过高会产生大量 node 进程并互相争抢，必须限流。
MAX_CONCURRENCY = 3


@log_performance("search_exercises")
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

    groups = await asyncio.gather(
        *(for_group(m) for m in muscle_groups_for(profile.get("days_per_week", 3)))
    )

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

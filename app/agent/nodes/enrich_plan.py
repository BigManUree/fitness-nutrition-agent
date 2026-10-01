"""节点 6：为通过校验的计划注入 MCP 动作指导（确定性节点，不调用 LLM）。

计划通过 validate_output 后执行：把入选动作在候选库中对应的
分步教学、简介、动作要领、常见错误、变化动作、别名、示范图、演示视频
原样贴到计划上，并统一附上重量选择与进退阶指引。

图片说明：MCP 的 images 为相对路径，官方不提供固定前缀，
因此完整 URL = EXERCISEAPI_IMAGE_BASE + 相对路径；未配置该环境变量时
image_urls 为空，前端用视频或占位图兜底。视频 url 为绝对地址，可直接播放。
所有内容均来自 MCP 原文，本节点不编写内容。
"""

from __future__ import annotations

import os

from app.agent.nutrition_planning import (
    ESTIMATED_WEIGHT_SOURCES,
    can_compute_targets,
    compute_meal_totals,
    compute_targets,
)
from app.agent.state import AgentState

# 统一附在计划上的重量试做与安全进退阶指引
WEIGHT_ADJUST_GUIDANCE = (
    "第一次练习请从建议重量区间的下限试做一组，能以标准动作完成目标次数"
    "（达到目标 RPE）后再逐步加重；一旦动作变形、失控或出现疼痛，"
    "立即减重或停止，不要硬撑。"
)

# 渐进负荷（第 1-4 周）总指引：确定性文案，说明如何逐周加重量/加次数
PROGRESSION_GUIDANCE = (
    "渐进负荷（第 1-4 周）：第 1 周用建议重量区间完成目标组次；"
    "之后每周只要能以标准动作完成上限次数，负重动作就加重 2.5-5%"
    "（或加 1-2 次），自重动作增加次数、放慢离心或升级变化动作；"
    "每 2 周校验一次动作标准度，一旦变形或疼痛立即回退重量。"
)

# 自重动作的渐进提示（无法按公斤数递增）
_BODYWEIGHT_WEIGHTS = ("", "自重", "bodyweight")

# 相对图片路径此前缀（官方未固定，按需在 .env 配置）；末尾统一补 "/"
_COPY_FIELDS = (
    "instructions",
    "overview",
    "form_tips",
    "common_mistakes",
    "safety",
    "variations",
    "keywords",
    "videos",
)


def _image_base() -> str:
    base = os.getenv("EXERCISEAPI_IMAGE_BASE", "").strip()
    return f"{base.rstrip('/')}/" if base else ""


def enrich_plan(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    base = _image_base()
    by_name = {
        item.get("name", ""): item for item in state.get("exercise_candidates", [])
    }

    for day in plan.get("weekly_plan", []) or []:
        for ex in day.get("exercises", []) or []:
            candidate = by_name.get(ex.get("name", ""))
            ex["progression"] = _progression_for(ex)
            if candidate is None:
                continue
            for field in _COPY_FIELDS:
                ex[field] = candidate.get(field)
            # 相对路径 -> 完整 URL；未配置前缀时留空，前端以视频/占位兜底
            ex["image_urls"] = [base + rel for rel in candidate.get("images", [])] if base else []

    plan["weight_guidance"] = WEIGHT_ADJUST_GUIDANCE
    plan["progression_guide"] = PROGRESSION_GUIDANCE

    _attach_nutrition(plan, state)
    return AgentState(plan=plan)


def _progression_for(ex: dict) -> str:
    """按动作类型给出第 1-4 周的渐进负荷提示（确定性文案）。"""
    weight = str(ex.get("weight", "")).strip().lower()
    if weight in _BODYWEIGHT_WEIGHTS:
        return "逐周增加次数、放慢离心或升级变化动作（见变化动作），无负重不宜盲目加次。"
    return "每周能标准完成上限次数后加重 2.5-5%（或 +1-2 次），次数回落区间下限重新递增。"


def _attach_nutrition(plan: dict, state: AgentState) -> None:
    """把热量/蛋白质目标与三餐实际核算结果写入计划，供前端展示闭环。"""
    profile = state.get("profile") or {}
    if can_compute_targets(profile):
        plan["nutrition_targets"] = compute_targets(profile)

    meals = plan.get("daily_meals") or {}
    food_by_name = {
        it["name"]: it for it in state.get("nutrition_candidates", [])
    }

    # 按食物可信度给餐单条目打标：分量为体积估算（parsed_volume）的条目标记
    # estimated_portion，前端在餐单上提示"分量(估算)"（宁可不给，不可错给）
    for course_items in meals.values():
        for item in course_items or []:
            food = food_by_name.get(item.get("food", "")) or {}
            if food.get("weight_source") in ESTIMATED_WEIGHT_SOURCES:
                item["estimated_portion"] = True

    totals = compute_meal_totals(meals, food_by_name)
    # 有任一可核算热量时才展示，避免全缺数据时误导
    if totals["calories"] > 0 or totals["protein_g"] > 0:
        plan["nutrition_totals"] = totals

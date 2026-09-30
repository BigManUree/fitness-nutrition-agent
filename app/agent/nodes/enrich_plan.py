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

from app.agent.state import AgentState

# 统一附在计划上的重量试做与安全进退阶指引
WEIGHT_ADJUST_GUIDANCE = (
    "第一次练习请从建议重量区间的下限试做一组，能以标准动作完成目标次数"
    "（达到目标 RPE）后再逐步加重；一旦动作变形、失控或出现疼痛，"
    "立即减重或停止，不要硬撑。"
)

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
            if candidate is None:
                continue
            for field in _COPY_FIELDS:
                ex[field] = candidate.get(field)
            # 相对路径 -> 完整 URL；未配置前缀时留空，前端以视频/占位兜底
            ex["image_urls"] = [base + rel for rel in candidate.get("images", [])] if base else []

    plan["weight_guidance"] = WEIGHT_ADJUST_GUIDANCE
    return AgentState(plan=plan)

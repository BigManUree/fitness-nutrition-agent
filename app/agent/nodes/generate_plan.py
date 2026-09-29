"""节点 4：基于候选数据让 LLM 组装一周训练计划 + 一日三餐。"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import get_llm
from app.agent.prompts import GENERATE_PLAN_SYSTEM, GENERATE_PLAN_USER
from app.agent.state import AgentState


def _parse_json(raw: str) -> dict:
    """容错解析：剥离 ```json 代码块包裹。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def _format_exercises(items: list[dict]) -> str:
    lines = []
    for it in items:
        muscles = ",".join(it.get("primary_muscles", [])[:3])
        lines.append(
            f"- {it['name']} | {muscles} | {it.get('equipment')} | {it.get('difficulty')}"
        )
    return "\n".join(lines) or "（无候选动作）"


def _format_foods(items: list[dict]) -> str:
    lines = []
    for it in items:
        p = it.get("per_100g") or {}
        lines.append(
            f"- {it['name']} | {p.get('calories')}千卡 / "
            f"蛋白{p.get('protein')}g / 碳水{p.get('carbs')}g / 脂肪{p.get('fat')}g"
        )
    return "\n".join(lines) or "（无候选食物）"


async def generate_plan(state: AgentState) -> AgentState:
    profile = state["profile"]
    messages = [
        SystemMessage(content=GENERATE_PLAN_SYSTEM),
        HumanMessage(
            content=GENERATE_PLAN_USER.format(
                profile=json.dumps(profile, ensure_ascii=False),
                exercises=_format_exercises(state.get("exercise_candidates", [])),
                foods=_format_foods(state.get("nutrition_candidates", [])),
            )
        ),
    ]

    llm = get_llm()
    errors = list(state.get("errors", []))
    try:
        response = await llm.ainvoke(messages)
        plan = _parse_json(response.content)
    except Exception as exc:
        errors.append(f"计划生成/解析失败：{exc}")
        return AgentState(plan={}, errors=errors, retries=state.get("retries", 0) + 1)

    return AgentState(plan=plan, errors=errors)

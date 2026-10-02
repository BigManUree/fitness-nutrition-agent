"""节点 4：基于候选数据让 LLM 组装一周训练计划 + 一日三餐。"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import get_llm
from app.agent.nutrition_planning import can_compute_targets, compute_targets
from app.agent.prompts import GENERATE_PLAN_SYSTEM, GENERATE_PLAN_USER
from app.agent.state import AgentState
from app.utils.performance_logger import USAGE_KEY, extract_llm_usage, log_performance


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
            f"- {it['name']} | {muscles} | {it.get('equipment')} | "
            f"{it.get('difficulty')} | {it.get('mechanic')} | {it.get('force')} | "
            f"{it.get('category')}"
        )
    return "\n".join(lines) or "（无候选动作）"


def _format_foods(items: list[dict]) -> str:
    lines = []
    for it in items:
        p = it.get("per_100g") or {}
        lines.append(
            f"- {it['name']} | {p.get('calories')}千卡 / "
            f"蛋白{p.get('protein')}g / 碳水{p.get('carbs')}g / 脂肪{p.get('fat')}g / "
            f"纤维{p.get('fiber')}g / 钠{p.get('sodium')}mg"
        )
    return "\n".join(lines) or "（无候选食物）"


@log_performance("generate_plan")
async def generate_plan(state: AgentState) -> AgentState:
    profile = state["profile"]

    # 是否为校验失败后的重试：把上轮 violations 回传给模型定向修正
    prior_validation = state.get("validation") or {}
    is_retry = not prior_validation.get("valid", True)
    retry_feedback = ""
    if is_retry:
        violations_text = "\n".join(
            f"- {item}" for item in prior_validation.get("violations", [])
        )
        retry_feedback = (
            "\n\n【上一次生成未通过校验，存在以下问题，本次必须全部修正】\n"
            f"{violations_text}\n"
            "只能使用下面候选列表中的动作和食物，禁止使用列表外的任何名称。"
        )

    if can_compute_targets(profile):
        targets_json = json.dumps(compute_targets(profile), ensure_ascii=False)
    else:
        targets_json = "（画像信息不完整，无法计算，按常规增肌/减脂经验配餐）"

    messages = [
        SystemMessage(content=GENERATE_PLAN_SYSTEM),
        HumanMessage(
            content=GENERATE_PLAN_USER.format(
                profile=json.dumps(profile, ensure_ascii=False),
                targets=targets_json,
                exercises=_format_exercises(state.get("exercise_candidates", [])),
                foods=_format_foods(state.get("nutrition_candidates", [])),
            )
            + retry_feedback
        ),
    ]

    llm = get_llm()
    errors = list(state.get("errors", []))
    # 重试一次：校验回炉与生成异常都计入 retries（图路由据此限制最多 1 次）
    retries = state.get("retries", 0) + (1 if is_retry else 0)
    usage: tuple[int | None, int | None] = (None, None)
    try:
        response = await llm.ainvoke(messages)
        usage = extract_llm_usage(response)
        plan = _parse_json(response.content)
    except Exception as exc:
        errors.append(f"计划生成/解析失败：{exc}")
        result = AgentState(
            plan={}, errors=errors, retries=retries + 1
        )
        result[USAGE_KEY] = usage  # 模型已返回时即使解析失败也有 token 用量
        return result

    result = AgentState(plan=plan, errors=errors, retries=retries)
    result[USAGE_KEY] = usage
    return result

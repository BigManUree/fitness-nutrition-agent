"""节点 7：把计划中的英文内容批量翻译为中文。

在 enrich_plan 之后执行：动作名、动作要领、分步教学、简介、常见错误、
安全提示、变化动作、关键词，以及三餐食物名，均通过一次 LLM 批量调用翻译，
译文写入并列的 *_zh / food_zh 字段——英文原字段保持不动（仍是校验与
动作替换的匹配键）。翻译结果以 SQLite translation_cache 缓存复用。

失败策略：模型调用/JSON 解析重试 1 次；仍失败或个别条目缺失时，该条目
保留英文原文并在计划上置 translation_warning，翻译是展示层，不拖垮计划。
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import get_llm
from app.agent.prompts import TRANSLATE_SYSTEM, TRANSLATE_USER
from app.agent.state import AgentState
from app.db.translations import get_cached_translations, save_translations
from app.utils.logger import get_logger
from app.utils.performance_logger import USAGE_KEY, extract_llm_usage, log_performance

logger = get_logger(__name__)

# 动作上需要翻译的字段：标量字段与列表字段分开处理
_SCALAR_FIELDS = ("name", "overview", "safety")
_LIST_FIELDS = (
    "form_tips", "instructions", "common_mistakes", "variations", "keywords",
)
_COURSES = ("breakfast", "lunch", "dinner")


def _collect_refs(plan: dict) -> tuple[list[dict], list[dict]]:
    """收集动作引用与餐单引用（容器 + 字段/键），供收集原文与回填译文共用。"""
    exercise_refs: list[dict] = []
    for day in plan.get("weekly_plan", []) or []:
        for ex in day.get("exercises", []) or []:
            exercise_refs.append({"ex": ex})

    meal_refs: list[dict] = []
    meals = plan.get("daily_meals") or {}
    for course in _COURSES:
        for item in meals.get(course, []) or []:
            meal_refs.append({"item": item})
    return exercise_refs, meal_refs


def _collect_texts(exercise_refs: list[dict], meal_refs: list[dict]) -> list[str]:
    """收集所有非空英文原文（去重保序）。"""
    texts: list[str] = []
    seen: set[str] = set()

    def add(text: str | None) -> None:
        if text and text not in seen:
            seen.add(text)
            texts.append(text)

    for ref in exercise_refs:
        ex = ref["ex"]
        for field in _SCALAR_FIELDS:
            add(ex.get(field))
        for field in _LIST_FIELDS:
            for text in ex.get(field, []) or []:
                add(text)
    for ref in meal_refs:
        add(ref["item"].get("food"))
    return texts


# 每批原文的字符预算：DeepSeek 单次输出上限 8192 token，中文译文约
# "一字一 token"，加上 JSON 结构开销，取 3000 字符可稳妥不超限。
_BATCH_CHAR_BUDGET = 3000


def _chunk_texts(texts: list[str]) -> list[list[str]]:
    """按字符预算把待译文本拆成多批；单条超长也独占一批。"""
    chunks: list[list[str]] = []
    current: list[str] = []
    used = 0
    for text in texts:
        if current and used + len(text) > _BATCH_CHAR_BUDGET:
            chunks.append(current)
            current, used = [], 0
        current.append(text)
        used += len(text)
    if current:
        chunks.append(current)
    return chunks


async def _translate_batch(texts: list[str]) -> dict[str, str] | None:
    """一次批量调用翻译一批文本；失败重试 1 次，仍失败返回 None。"""
    items = [{"id": idx, "text": text} for idx, text in enumerate(texts, 1)]
    payload = json.dumps(items, ensure_ascii=False, indent=1)
    messages = [
        SystemMessage(content=TRANSLATE_SYSTEM),
        HumanMessage(content=TRANSLATE_USER.format(n=len(texts), items=payload)),
    ]

    llm = get_llm()
    usage: tuple[int | None, int | None] = (None, None)
    for attempt in (1, 2):
        try:
            response = await llm.ainvoke(messages)
            usage = extract_llm_usage(response)
            data = json.loads(response.content)
            rows = data.get("translations", [])
            by_id = {int(r["id"]): str(r["zh"]) for r in rows if r.get("zh")}
            result = {texts[idx - 1]: zh for idx, zh in by_id.items() if 1 <= idx <= len(texts)}
            return result, usage
        except Exception as exc:  # noqa: BLE001 - 重试后放弃
            logger.warning("翻译批次第 %s 次尝试失败：%s", attempt, exc)
    return None, usage


def _apply_translations(
    exercise_refs: list[dict], meal_refs: list[dict], translated: dict[str, str]
) -> int:
    """把译文按位置确定性回填；未译条目保留英文。返回未译条目数。"""
    missing = 0

    def zh(text: str | None) -> str:
        nonlocal missing
        if not text:
            return ""
        target = translated.get(text)
        if not target:
            missing += 1
            return text
        return target

    for ref in exercise_refs:
        ex = ref["ex"]
        for field in _SCALAR_FIELDS:
            if ex.get(field):
                ex[f"{field}_zh"] = zh(ex[field])
        for field in _LIST_FIELDS:
            if ex.get(field):
                ex[f"{field}_zh"] = [zh(text) for text in ex[field]]
    for ref in meal_refs:
        item = ref["item"]
        if item.get("food"):
            item["food_zh"] = zh(item["food"])
    return missing


@log_performance("translate_plan")
async def translate_plan(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    exercise_refs, meal_refs = _collect_refs(plan)
    texts = _collect_texts(exercise_refs, meal_refs)

    translated = get_cached_translations(texts)
    uncached = [text for text in texts if text not in translated]

    in_tokens = out_tokens = 0
    warning = False
    if uncached:
        # 文本量大时自动拆批，避免单次输出超过模型上限导致 JSON 截断
        for idx, chunk in enumerate(_chunk_texts(uncached), 1):
            batch, usage = await _translate_batch(chunk)
            if usage[0]:
                in_tokens += usage[0]
            if usage[1]:
                out_tokens += usage[1]
            if batch is None:
                # 该批失败：对应条目保留英文，其余批次继续，计划仍可用
                warning = True
                logger.warning("第 %s 批翻译重试后仍失败，该批保留英文原文", idx)
            else:
                translated.update(batch)
                save_translations(batch)

    missing = _apply_translations(exercise_refs, meal_refs, translated)
    if missing:
        warning = True

    if warning:
        plan["translation_warning"] = (
            "部分内容暂时无法翻译，已保留英文原文，可稍后重新生成计划。"
        )

    result = AgentState(plan=plan)
    result[USAGE_KEY] = (in_tokens or None, out_tokens or None)
    return result

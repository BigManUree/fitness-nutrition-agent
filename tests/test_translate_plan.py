"""translate_plan 节点测试：批量翻译、缓存复用、失败回退英文。"""

from __future__ import annotations

import json
import re

import pytest
from app.agent.nodes import translate_plan as node


def _state() -> dict:
    plan = {
        "weekly_plan": [
            {
                "day": 1,
                "exercises": [
                    {
                        "name": "Barbell Back Squat",
                        "overview": "A compound lower body exercise.",
                        "safety": "Use safety bars.",
                        "form_tips": ["Keep chest up", "Drive through heels"],
                        "instructions": ["Set your feet", "Squat down"],
                        "common_mistakes": ["Knees cave in"],
                        "variations": ["Front Squat"],
                        "keywords": ["squat"],
                    }
                ],
            }
        ],
        "daily_meals": {
            "breakfast": [{"food": "Egg, whole, raw, fresh", "amount": "2个"}],
            "lunch": [],
            "dinner": [],
        },
    }
    return {"plan": plan}


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """把输入条目逐条伪翻译为 "译:<原文>"，便于断言一一对应。"""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, messages) -> _FakeResponse:
        self.calls += 1
        user_text = messages[-1].content
        match = re.search(r"\[.*\]", user_text, re.S)
        items = json.loads(match.group(0))
        rows = [{"id": it["id"], "zh": "译:" + it["text"]} for it in items]
        return _FakeResponse(json.dumps({"translations": rows}, ensure_ascii=False))


class _FailingLLM:
    async def ainvoke(self, messages):
        raise RuntimeError("llm unavailable")


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test.db"))


@pytest.mark.asyncio
async def test_translates_all_fields_keeps_english(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(node, "get_llm", lambda *a, **k: fake)

    result = await node.translate_plan(_state())
    plan = result["plan"]
    ex = plan["weekly_plan"][0]["exercises"][0]

    # 英文原字段不动
    assert ex["name"] == "Barbell Back Squat"
    assert ex["form_tips"] == ["Keep chest up", "Drive through heels"]

    # 译文写入并列字段
    assert ex["name_zh"] == "译:Barbell Back Squat"
    assert ex["form_tips_zh"] == ["译:Keep chest up", "译:Drive through heels"]
    assert ex["instructions_zh"] == ["译:Set your feet", "译:Squat down"]
    assert ex["overview_zh"] == "译:A compound lower body exercise."
    assert ex["safety_zh"] == "译:Use safety bars."
    assert ex["common_mistakes_zh"] == ["译:Knees cave in"]
    assert ex["variations_zh"] == ["译:Front Squat"]
    assert ex["keywords_zh"] == ["译:squat"]

    food = plan["daily_meals"]["breakfast"][0]
    assert food["food"] == "Egg, whole, raw, fresh"
    assert food["food_zh"] == "译:Egg, whole, raw, fresh"

    assert "translation_warning" not in plan
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_cache_hit_skips_llm(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(node, "get_llm", lambda *a, **k: fake)
    await node.translate_plan(_state())
    assert fake.calls == 1

    # 第二次相同文本：全部命中缓存，不应再调用模型
    def _no_llm(*a, **k):
        raise AssertionError("缓存命中时不应调用 LLM")

    monkeypatch.setattr(node, "get_llm", _no_llm)
    result = await node.translate_plan(_state())
    ex = result["plan"]["weekly_plan"][0]["exercises"][0]
    assert ex["name_zh"] == "译:Barbell Back Squat"


@pytest.mark.asyncio
async def test_large_volume_split_into_chunks(monkeypatch):
    """文本总量超预算时自动拆批，全部条目都能译出。"""
    from app.agent.nodes.translate_plan import _BATCH_CHAR_BUDGET

    fake = _FakeLLM()
    monkeypatch.setattr(node, "get_llm", lambda *a, **k: fake)

    state = _state()
    ex = state["plan"]["weekly_plan"][0]["exercises"][0]
    # 塞入足以触发两批的额外文本
    ex["form_tips"] = [f"Tip number {i} " + "x" * 400 for i in range(_BATCH_CHAR_BUDGET // 300 + 2)]

    result = await node.translate_plan(state)
    translated_ex = result["plan"]["weekly_plan"][0]["exercises"][0]
    assert fake.calls >= 2
    assert len(translated_ex["form_tips_zh"]) == len(ex["form_tips"])
    assert all(zh.startswith("译:") for zh in translated_ex["form_tips_zh"])


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(node, "get_llm", lambda *a, **k: _FailingLLM())

    result = await node.translate_plan(_state())
    plan = result["plan"]
    ex = plan["weekly_plan"][0]["exercises"][0]

    # 无 zh 字段或回填英文原文，计划仍可用
    assert ex.get("name_zh", ex["name"]) == "Barbell Back Squat"
    assert "translation_warning" in plan

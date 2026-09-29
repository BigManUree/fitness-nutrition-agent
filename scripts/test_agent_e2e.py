"""端到端验证：画像 → 检索 → 生成 → 校验，打印生成的计划。

用法：uv run python scripts/test_agent_e2e.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.graph import agent_graph  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SAMPLE_PROFILE = {
    "sex": "male",
    "age": 28,
    "height_cm": 175,
    "weight_kg": 72,
    "goal": "muscle_gain",
    "days_per_week": 4,
    "equipment": ["dumbbell", "barbell"],
    "dietary_preferences": [],
    "allergies": [],
}


async def main() -> None:
    print("[1/4] 启动工作流…", flush=True)
    result = await agent_graph.ainvoke(
        {"user_id": "e2e-001", "profile": SAMPLE_PROFILE},
        config={"configurable": {"thread_id": "e2e-001"}},
    )

    print(f"[2/4] 候选动作 {len(result.get('exercise_candidates', []))} 个", flush=True)
    print(f"      候选食物 {len(result.get('nutrition_candidates', []))} 个", flush=True)

    validation = result.get("validation", {})
    print(f"[3/4] 校验 valid={validation.get('valid')} "
          f"violations={validation.get('violations')}", flush=True)
    if result.get("errors"):
        print("      过程错误（前 3 条）:", result["errors"][:3], flush=True)

    plan = result.get("plan") or {}
    print(f"[4/4] 训练天数 {len(plan.get('weekly_plan', []))}，"
          f"动作 {validation.get('exercise_count')} 个\n", flush=True)

    if not validation.get("valid"):
        sys.exit(1)

    for day in plan.get("weekly_plan", []):
        print(f"Day {day['day']} · {day.get('focus','')}")
        for ex in day.get("exercises", []):
            print(f"  - {ex['name']} | {ex['sets']}组×{ex['reps']} | 休息{ex['rest']}")
        print()

    meals = plan.get("daily_meals", {})
    for course, label in (
        ("breakfast", "早餐"),
        ("lunch", "午餐"),
        ("dinner", "晚餐"),
    ):
        print(label)
        for item in meals.get(course, []):
            print(f"  - {item['food']} {item['amount']}（{item.get('note','')}）")
        print()

    print("为什么这样安排：", plan.get("rationale", ""))


if __name__ == "__main__":
    asyncio.run(main())

"""营养餐单表格渲染组件。"""

from __future__ import annotations

import streamlit as st

_COURSES = (
    ("breakfast", "🌅 早餐"),
    ("lunch", "☀️ 午餐"),
    ("dinner", "🌙 晚餐"),
)


def render_meals(
    daily_meals: dict, targets: dict | None = None, totals: dict | None = None
) -> None:
    if targets:
        st.info(_targets_summary(targets, totals))

    for key, label in _COURSES:
        st.subheader(label)
        rows = [
            {
                "食物": _food_label(item),
                "分量": item.get("amount", ""),
                "说明": item.get("note", ""),
            }
            for item in daily_meals.get(key, [])
        ]
        st.table(rows)


def _food_label(item: dict) -> str:
    """食物名，分量为体积估算（parsed_volume）时追加提示。"""
    label = item.get("food_zh") or item.get("food", "")
    if item.get("estimated_portion"):
        label = f"{label}（分量估算）"
    return label


def _targets_summary(targets: dict, totals: dict | None) -> str:
    """营养目标与（若有）三餐核算结果的一句话摘要。"""
    delta = targets.get("calorie_delta", 0)
    if delta < 0:
        goal_note = f"减脂缺口 {abs(delta)} 千卡"
    elif delta > 0:
        goal_note = f"增肌盈余 {delta} 千卡"
    else:
        goal_note = "维持热量"

    lines = [
        f"🎯 营养目标：每日约 {targets['target_calories']} 千卡、"
        f"蛋白质 {targets['target_protein_g']}g"
        f"（TDEE {targets['tdee']} 千卡，{goal_note}）"
    ]

    if totals and totals.get("calories", 0) > 0:
        lines.append(
            f"本次三餐合计：约 {totals['calories']} 千卡、蛋白质 {totals['protein_g']}g"
        )

        target_cal = targets.get("target_calories")
        target_protein = targets.get("target_protein_g")
        ok_cal = target_cal and abs(
            (totals["calories"] - target_cal) / target_cal * 100
        ) <= 10.0
        ok_protein = (
            target_protein
            and totals.get("protein_g", 0) >= 0.9 * target_protein
        )
        if ok_cal and ok_protein:
            lines.append("✅ 热量与蛋白质均达标")
        else:
            flags = []
            if not ok_cal:
                flags.append("热量偏差超 ±10%")
            if not ok_protein:
                flags.append("蛋白质未达目标的 90%")
            lines.append("⚠️ " + "、".join(flags) + "，请注意调整")

        if totals.get("estimated"):
            lines.append(
                f"ℹ️ 其中 {totals['estimated']} 项食物分量为体积估算（按水密度推算），"
                "实际热量可能偏离，以上判断仅供参考"
            )

    return "\n".join(lines)
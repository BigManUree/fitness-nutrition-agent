"""营养餐单表格渲染组件。"""

from __future__ import annotations

import streamlit as st

_COURSES = (
    ("breakfast", "🌅 早餐"),
    ("lunch", "☀️ 午餐"),
    ("dinner", "🌙 晚餐"),
)


def render_meals(daily_meals: dict) -> None:
    for key, label in _COURSES:
        st.subheader(label)
        rows = [
            {
                "食物": item.get("food", ""),
                "分量": item.get("amount", ""),
                "说明": item.get("note", ""),
            }
            for item in daily_meals.get(key, [])
        ]
        st.table(rows)

"""训练计划表格渲染组件。"""

from __future__ import annotations

import streamlit as st


def render_weekly_plan(weekly_plan: list[dict]) -> None:
    for day in weekly_plan:
        st.subheader(f"Day {day.get('day')} · {day.get('focus', '')}")
        rows = [
            {
                "动作": ex.get("name", ""),
                "组数": ex.get("sets", ""),
                "次数": ex.get("reps", ""),
                "休息": ex.get("rest", ""),
                "说明": ex.get("note", ""),
            }
            for ex in day.get("exercises", [])
        ]
        st.table(rows)

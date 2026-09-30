"""用户画像表单组件。"""

from __future__ import annotations

import streamlit as st

# (内部值, 展示名)
EQUIPMENT_OPTIONS = [
    ("gym", "健身房（全部器械都有）"),
    ("barbell", "杠铃"),
    ("dumbbell", "哑铃"),
    ("kettlebell", "壶铃"),
    ("bench", "训练凳"),
    ("pull-up bar", "引体向上杆"),
    ("cable", "龙门架/绳索"),
    ("machine", "固定器械"),
    ("band", "弹力带"),
]

GOAL_OPTIONS = [
    ("fat_loss", "减脂"),
    ("muscle_gain", "增肌"),
    ("recomp", "塑形（减脂+增肌）"),
    ("general_fitness", "综合体能与健康"),
]


def profile_form(initial: dict | None = None) -> dict | None:
    """渲染表单，点击提交后返回画像 dict；未提交返回 None。

    initial 非空时（如从 SQLite 恢复的画像），各字段按其值预填。
    """
    initial = initial or {}
    with st.form("profile_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            sex = st.selectbox(
                "性别", ["male", "female"],
                index=["male", "female"].index(initial.get("sex", "male")),
                format_func=lambda x: "男" if x == "male" else "女",
            )
            age = st.number_input("年龄", min_value=14, max_value=80,
                                  value=int(initial.get("age", 28)), step=1)
            height_cm = st.number_input(
                "身高（cm）", min_value=100.0, max_value=250.0,
                value=float(initial.get("height_cm", 175.0)), step=1.0)
        with col2:
            weight_kg = st.number_input(
                "体重（kg）", min_value=30.0, max_value=200.0,
                value=float(initial.get("weight_kg", 72.0)), step=0.5)
            goal = st.selectbox(
                "目标", [v for v, _ in GOAL_OPTIONS],
                index=[v for v, _ in GOAL_OPTIONS].index(
                    initial.get("goal", "fat_loss")),
                format_func=lambda x: dict(GOAL_OPTIONS)[x])
            days_per_week = st.slider(
                "每周可训练天数", 1, 7,
                value=int(initial.get("days_per_week", 4)))

        equipment = st.multiselect(
            "可用器械（自重动作默认可用，无需选择）",
            options=[v for v, _ in EQUIPMENT_OPTIONS],
            default=initial.get("equipment", ["barbell", "dumbbell"]),
            format_func=lambda x: dict(EQUIPMENT_OPTIONS)[x],
            help="选择「健身房（全部器械都有）」后，其他器械无需再选，系统会自动按全器械处理。",
        )

        col3, col4 = st.columns(2)
        with col3:
            prefs_text = st.text_input(
                "饮食偏好（逗号分隔，可选）",
                value=", ".join(initial.get("dietary_preferences", [])),
                placeholder="如：清淡, 不吃辣")
        with col4:
            allergy_text = st.text_input(
                "食物过敏（逗号分隔，可选）",
                value=", ".join(initial.get("allergies", [])),
                placeholder="如：花生, 海鲜")

        submitted = st.form_submit_button("保存画像", type="primary")

    if not submitted:
        return None

    return {
        "sex": sex,
        "age": int(age),
        "height_cm": float(height_cm),
        "weight_kg": float(weight_kg),
        "goal": goal,
        "days_per_week": int(days_per_week),
        "equipment": equipment,
        "dietary_preferences": [s.strip() for s in prefs_text.split(",") if s.strip()],
        "allergies": [s.strip() for s in allergy_text.split(",") if s.strip()],
    }

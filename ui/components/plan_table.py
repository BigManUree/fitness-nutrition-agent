"""训练计划表格渲染组件。"""

from __future__ import annotations

import streamlit as st


def render_weekly_plan(weekly_plan: list[dict]) -> None:
    for day in weekly_plan:
        st.subheader(f"第 {day.get('day')} 天 · {day.get('focus', '')}")
        rows = [
            {
                "动作": _name_cell(ex),
                "建议重量": _weight_cell(ex),
                "组数": ex.get("sets", ""),
                "次数": ex.get("reps", ""),
                "休息": ex.get("rest", ""),
                "动作要领": "\n".join(f"· {t}" for t in ex.get("form_tips_zh") or ex.get("form_tips", [])),
                "说明": ex.get("note", ""),
            }
            for ex in day.get("exercises", [])
        ]
        st.table(rows)

        for ex in day.get("exercises", []) or []:
            _render_exercise_detail(ex)

        # 常见错误与安全提示收进展开区，避免表格信息过载
        cautions = [
            (ex, ex.get("common_mistakes_zh") or ex.get("common_mistakes", []),
             ex.get("safety_zh") or ex.get("safety"))
            for ex in day.get("exercises", [])
            if ex.get("common_mistakes") or ex.get("safety")
        ]
        if cautions:
            with st.expander("⚠️ 常见错误与安全提示"):
                for ex, mistakes, safety in cautions:
                    st.markdown(f"**{_display_name(ex)}**")
                    for mistake in mistakes:
                        st.write(f"- 易犯：{mistake}")
                    if safety:
                        st.write(f"- 安全：{safety}")


def _display_name(ex: dict) -> str:
    """展示名：优先中文译文，回退英文原文。"""
    return ex.get("name_zh") or ex.get("name", "")


def _name_cell(ex: dict) -> str:
    """表格动作文案：中文为主，英文原文另起一行小字（表格内用换行表示）。"""
    name_zh = ex.get("name_zh")
    name_en = ex.get("name", "")
    if name_zh and name_zh != name_en:
        return f"{name_zh}\n（{name_en}）"
    return name_zh or name_en


def _render_exercise_detail(ex: dict) -> None:
    """单个动作的详细展开区：演示图/视频、简介、分步教学、变化动作、别名。"""
    name = _display_name(ex)
    videos = ex.get("videos", []) or []
    image_urls = ex.get("image_urls", []) or []
    overview = ex.get("overview_zh") or ex.get("overview")
    instructions = ex.get("instructions_zh") or ex.get("instructions", []) or []
    variations = ex.get("variations_zh") or ex.get("variations", []) or []
    keywords = ex.get("keywords_zh") or ex.get("keywords", []) or []
    progression = ex.get("progression", "")

    if not (videos or image_urls or overview or instructions or variations or keywords or progression):
        return

    with st.expander(f"📖 {name} · 动作详解（演示图/视频 + 分步教学）"):
        if ex.get("name_zh") and ex.get("name") and ex["name_zh"] != ex["name"]:
            st.caption(f"英文名：{ex['name']}")

        media_cols = st.columns(2)
        with media_cols[0]:
            if videos:
                st.caption("演示视频（无声循环，仅作动作示范）")
                st.video(videos[0].get("url", ""))
            else:
                st.caption("该动作暂无演示视频")
        with media_cols[1]:
            if image_urls:
                st.caption("示范图")
                st.image(image_urls[:2])
            else:
                st.caption("未配置示范图（设置 EXERCISEAPI_IMAGE_BASE 后显示）")

        if progression:
            st.markdown(f"**📈 渐进负荷（第 1-4 周）**：{progression}")

        if overview:
            st.markdown(f"**动作简介**：{overview}")

        if instructions:
            st.markdown("**分步教学**")
            for idx, step in enumerate(instructions, 1):
                st.write(f"{idx}. {step}")

        if variations:
            st.markdown("**可替换/进阶变化动作**：" + "、".join(variations))
        if keywords:
            st.caption("别名/关键词：" + "、".join(keywords))


def _weight_cell(ex: dict) -> str:
    """合并重量区间与 RPE，如 "20-40kg（RPE 7-8）"。"""
    weight = ex.get("weight", "")
    rpe = ex.get("rpe", "")
    if weight and rpe:
        return f"{weight}（{rpe}）"
    return weight or rpe or ""

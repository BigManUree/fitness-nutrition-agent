"""页面 2：运行 Agent 生成计划并渲染。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from components.meal_table import render_meals  # noqa: E402
from components.plan_table import render_weekly_plan  # noqa: E402

st.title("📅 生成计划")

profile = st.session_state.get("profile")
if not profile:
    st.info("请先在「用户画像」页面填写并保存画像。")
    st.stop()

st.json(profile, expanded=False)

@st.cache_resource
def _get_event_loop() -> asyncio.AbstractEventLoop:
    """常驻事件循环：跨 rerun/多次点击复用，避免 Windows 下 asyncio.run
    关闭循环后异步资源报 "Event loop is closed"。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


if st.button("🚀 生成一周训练 + 一日三餐", type="primary"):
    # 确保 MCP 桥接可用，给出可读提示
    with st.spinner("正在检索动作/食物并由模型编排，约需 1-3 分钟…"):
        try:
            from app.agent.graph import agent_graph

            user_id = st.session_state.current_user
            loop = _get_event_loop()
            result = loop.run_until_complete(
                agent_graph.ainvoke(
                    {"user_id": user_id, "profile": profile},
                    config={"configurable": {"thread_id": user_id}},
                )
            )
        except Exception as exc:
            st.error(f"生成失败：{exc}")
            st.info("请确认 MCP 桥接已启动（make mcp-up）后重试。")
            st.stop()

    st.session_state.plan = result.get("plan")
    st.session_state.validation = result.get("validation")
    if result.get("errors"):
        with st.expander(f"过程中有 {len(result['errors'])} 条提示，点击查看"):
            for err in result["errors"]:
                st.code(err)
    if not result.get("plan"):
        st.error("本次未生成计划，请根据上方提示调整后重试。")
        st.stop()

plan = st.session_state.get("plan")
validation = st.session_state.get("validation")

if plan:
    if validation and not validation.get("valid"):
        st.warning(
            "计划未通过校验：" + "；".join(validation.get("violations", []))
        )

    if plan.get("translation_warning"):
        st.warning(plan["translation_warning"])

    tab1, tab2 = st.tabs(["🏋️ 一周训练计划", "🍱 一日三餐"])
    with tab1:
        if plan.get("weight_guidance"):
            st.info(plan["weight_guidance"])
        if plan.get("progression_guide"):
            st.info(plan["progression_guide"])
        render_weekly_plan(plan.get("weekly_plan", []))
    with tab2:
        render_meals(
            plan.get("daily_meals", {}),
            plan.get("nutrition_targets"),
            plan.get("nutrition_totals"),
        )

    st.divider()
    st.subheader("💡 为什么这样安排")
    st.write(plan.get("rationale", ""))

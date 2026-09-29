"""Streamlit 多页面入口（st.navigation 模式）。

启动：streamlit run ui/app.py（或 make dev）
页面：画像表单 → 计划生成 → 对话调整
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit 只把主脚本所在目录（ui/）加入 sys.path，
# 这里补项目根，使各页面能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="健身营养 Agent",
    page_icon="🏋️",
    layout="wide",
)

pages = [
    st.Page("pages/1_profile.py", title="用户画像", icon="📋"),
    st.Page("pages/2_plan.py", title="生成计划", icon="📅"),
    st.Page("pages/3_chat.py", title="对话调整", icon="💬"),
]

st.sidebar.title("🏋️ 健身营养 Agent")
st.sidebar.caption("根据身体条件、目标与器械，生成一周训练计划与一日三餐")

nav = st.navigation(pages, position="sidebar")

# 跨页面共享状态的默认值
st.session_state.setdefault("profile", None)
st.session_state.setdefault("plan", None)
st.session_state.setdefault("validation", None)
st.session_state.setdefault("chat_history", [])

if st.session_state.get("profile"):
    st.sidebar.success("画像已保存 ✅")
if st.session_state.get("plan"):
    st.sidebar.success("计划已生成 ✅")

nav.run()

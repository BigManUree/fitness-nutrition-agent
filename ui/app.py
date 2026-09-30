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


def check_password() -> bool:
    """密码校验：密码存于 st.secrets["APP_PASSWORD"]，不写入代码。

    返回 True 表示已认证；未认证时渲染登录框并 st.stop() 中断页面。
    """
    if st.session_state.get("authenticated"):
        return True

    # 未配置密码时 fail closed：拒绝放行并提示部署者补配置
    expected_password = st.secrets.get("APP_PASSWORD") if hasattr(st, "secrets") else None
    if not expected_password or expected_password == "your_password_here":
        st.error("未配置访问密码（.streamlit/secrets.toml 中的 APP_PASSWORD），拒绝访问。")
        st.stop()

    st.title("🔒 请输入访问密码")

    with st.form("login_form"):
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("登录")

    if submitted:
        if password == expected_password:
            st.session_state.authenticated = True
            st.rerun()
        st.error("密码错误，请重试。")

    # 未认证：阻断后续页面渲染
    st.stop()


check_password()

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

if st.sidebar.button("退出登录"):
    st.session_state.authenticated = False
    st.rerun()

nav.run()

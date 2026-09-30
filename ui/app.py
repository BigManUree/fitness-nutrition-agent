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


# 切换账号时需要清空的会话键，避免上一个用户的数据残留
_SESSION_DATA_KEYS = (
    "profile",
    "plan",
    "validation",
    "chat_history",
    "db_loaded",
    "user_id",
    "pending_substitution",
)


def account_gate() -> None:
    """账号门禁：未登录时提供「登录 / 注册」；通过后以用户名作为 user_id。

    账号与密码哈希存于本地 SQLite（app.db.users）；本函数不依赖 st.secrets。
    未通过统一 st.stop()，阻断后续页面渲染。
    """
    if st.session_state.get("current_user"):
        # 登录后以用户名作为全链路主键（画像/计划/向量/会话隔离）
        st.session_state.user_id = st.session_state.current_user
        return

    from app.db.users import UserExistsError, create_user, verify_user

    st.title("🔐 健身营养 Agent")

    tab_login, tab_register = st.tabs(["登录", "注册新账号"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="3-20 位字母/数字/下划线")
            password = st.text_input("密码", type="password")
            login_clicked = st.form_submit_button("登录")
        if login_clicked:
            if username and verify_user(username, password):
                st.session_state.current_user = username
                st.rerun()
            st.error("用户名或密码错误。")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("用户名", key="reg_username")
            new_password = st.text_input("密码", type="password", key="reg_password")
            confirm = st.text_input("确认密码", type="password", key="reg_confirm")
            register_clicked = st.form_submit_button("注册并登录")
        if register_clicked:
            if new_password != confirm:
                st.error("两次输入的密码不一致。")
            else:
                try:
                    create_user(new_username, new_password)
                except UserExistsError as exc:
                    st.error(str(exc))
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.current_user = new_username
                    st.rerun()

    st.caption("开放自助注册：新用户注册后即可使用，各账号数据相互隔离。")
    st.stop()


account_gate()

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

st.sidebar.success(f"当前用户：{st.session_state.current_user}")
if st.session_state.get("profile"):
    st.sidebar.success("画像已保存 ✅")
if st.session_state.get("plan"):
    st.sidebar.success("计划已生成 ✅")

if st.sidebar.button("退出登录"):
    st.session_state.current_user = None
    for key in _SESSION_DATA_KEYS:
        st.session_state.pop(key, None)
    st.rerun()

nav.run()

"""页面 1：用户画像表单。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402
from app.db.models import Profile  # noqa: E402
from app.db.sqlite_client import load_profile, save_profile  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from components.profile_form import profile_form  # noqa: E402

st.title("📋 用户画像")
st.caption("信息会用于生成训练与饮食计划，请如实填写；信息不全时无法生成。")

# 跨会话预填：会话里没有画像时，只从 SQLite 恢复“当前账号”的画像（只查一次）
current_user = st.session_state.current_user
if st.session_state.get("profile") is None and not st.session_state.get("db_loaded"):
    try:
        saved_profile = load_profile(current_user)
    except Exception as exc:
        st.warning(f"读取已存画像失败（{exc}），将使用空白表单。")
    else:
        if saved_profile is not None:
            st.session_state.user_id = current_user
            st.session_state.profile = saved_profile.model_dump()
            st.info("已恢复你的画像，可直接修改后保存。")
    st.session_state.db_loaded = True

raw = profile_form(initial=st.session_state.get("profile"))

if raw is not None:
    try:
        # 入库存前规整列表字段：去空白/去重，器械统一小写
        from app.tools.profile_tools import normalize_equipment, normalize_text_list

        raw["equipment"] = normalize_equipment(raw.get("equipment", []))
        raw["dietary_preferences"] = normalize_text_list(raw.get("dietary_preferences", []))
        raw["allergies"] = normalize_text_list(raw.get("allergies", []))
        profile = Profile(**raw)
    except ValidationError as exc:
        for err in exc.errors():
            st.error(f"「{err['loc'][0]}」{err['msg']}")
    else:
        data = profile.model_dump()
        # 以登录用户名作为主键：SQLite 画像/计划与 Chroma 向量都按账号隔离
        user_id = current_user
        st.session_state.profile = data
        st.session_state.user_id = user_id
        # 画像变更后，旧计划失效
        st.session_state.plan = None
        st.session_state.validation = None

        # 持久化到 SQLite（重启 / 换会话后可恢复）
        sqlite_ok = True
        try:
            save_profile(profile, user_id)
        except Exception as exc:
            sqlite_ok = False
            st.error(f"画像保存到本地数据库失败（{exc}），本次仅保留在当前会话。")

        # 画像入库 Chroma（依赖嵌入服务，失败只警告不阻塞）
        try:
            from app.rag.profile_indexer import index_profile

            index_profile(profile, user_id)
            if sqlite_ok:
                st.success("画像已保存（本地数据库 + 向量库）✅ 可前往「生成计划」页面。")
        except Exception as exc:  # 嵌入服务未启动等
            st.warning(
                f"画像已存入本地数据库，但向量入库失败（{exc}）。"
                "不影响生成计划；如需画像检索，请先启动嵌入服务。"
            )

if st.session_state.get("profile"):
    with st.expander("查看当前画像"):
        st.json(st.session_state.profile)

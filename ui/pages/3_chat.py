"""页面 3：对话调整计划（支持调用 substitute_exercise 替换动作）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

st.title("💬 对话调整")

plan = st.session_state.get("plan")
if not plan:
    st.info("请先在「生成计划」页面生成计划，再来这里调整。")
    st.stop()

profile = st.session_state.get("profile", {})

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

CHAT_SYSTEM = """你是健身营养 Agent 的对话助手，帮助用户理解和微调"已生成的计划"。

规则：
1. 普通问答只能围绕下方计划内容；不要编造计划之外的新动作或新食物。
2. 当用户要求"替换/换掉某个动作"时，必须调用 substitute_exercise 工具，
   并根据工具返回的真实候选回答；工具返回为空时如实转述，不要自己编候选。
3. 不做医疗诊断，不推荐极端节食或危险动作。
4. 如果用户描述胸痛、头晕、严重关节疼痛、心悸等症状，回复：
   "我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。该症状属于需要重视的症状，建议你暂停训练，尽快咨询医生，由专业医师评估后再决定是否运动。"
5. 用简洁中文回答；列出候选动作时保留动作原名（英文）。

当前计划：
""" + json.dumps(plan, ensure_ascii=False)


def _apply_substitution(original_name: str, new_name: str) -> bool:
    """把计划中的原动作改名为替代动作，组数/次数/休息保持不变。"""
    changed = False
    target = original_name.strip().lower()
    for day in plan.get("weekly_plan", []):
        for ex in day.get("exercises", []):
            if ex.get("name", "").strip().lower() == target:
                ex["name"] = new_name
                changed = True
    return changed


# 渲染历史消息
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 上一轮工具返回的候选：提供"应用到计划"操作
pending = st.session_state.get("pending_substitution")
if pending and pending.get("alternatives"):
    with st.container(border=True):
        st.caption(
            f"将「{pending['original_exercise']}」替换为："
        )
        names = [alt["name"] for alt in pending["alternatives"]]
        chosen = st.selectbox("选择替代动作", names, key="pending_choose")
        if st.button("✅ 应用到当前计划", key="pending_apply"):
            if _apply_substitution(pending["original_exercise"], chosen):
                st.success(f"已替换为 {chosen}（组数/次数/休息不变）。")
                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "content": f"已将计划中的「{pending['original_exercise']}」"
                        f"替换为「{chosen}」。",
                    }
                )
                st.session_state.pending_substitution = None
                st.rerun()
            else:
                st.warning("当前计划中未找到该原动作（可能已替换过）。")
                st.session_state.pending_substitution = None

if prompt := st.chat_input("说说你想怎么调整，如：把卧推换成哑铃能做的"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    from app.agent.chat_adjust import resolve_with_tools
    from app.agent.llm import get_llm
    from app.agent.safety import pre_check_message
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    history = st.session_state.chat_history
    messages: list = [SystemMessage(content=CHAT_SYSTEM)]
    for msg in history:
        cls = HumanMessage if msg["role"] == "user" else AIMessage
        messages.append(cls(content=msg["content"]))

    with st.chat_message("assistant"):
        with st.spinner("思考中…"):
            # 代码层安全守卫：医疗症状/极端节食/编造动作命中即固定话术，不调模型
            guard_reply = pre_check_message(prompt)
            if guard_reply is not None:
                answer, tool_results = guard_reply, []
            else:
                try:
                    llm = get_llm(json_mode=False, temperature=0.4)
                    answer, tool_results = resolve_with_tools(llm, messages, profile)
                except Exception as exc:
                    answer, tool_results = f"调用模型失败：{exc}", []
        st.markdown(answer)

    st.session_state.chat_history.append({"role": "assistant", "content": answer})

    # 记录最后一次有候选的替换，供下方"应用到计划"
    latest = next(
        (r for r in reversed(tool_results) if r.get("alternatives")), None
    )
    if latest is not None:
        st.session_state.pending_substitution = latest
        st.rerun()

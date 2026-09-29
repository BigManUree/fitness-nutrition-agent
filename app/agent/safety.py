"""安全边界：需要医学评估的症状强制固定话术（代码层守卫，不依赖模型遵守）。

设计原因：把规则写在 system prompt 里属于概率性防御，模型可能被越狱提示
绕过；而在调用模型之前用本模块拦截，可以确定性地保证：只要用户描述了
胸痛/头晕/严重关节疼痛/心悸等症状，就一定得到固定回复，且不会把症状
送去模型做任何诊断性推理。
"""

from __future__ import annotations

# 触发词按特异性排序：短词（如"胸痛"）直接命中，
# "严重关节疼痛"要求带"严重"修饰，普通关节酸痛不触发
MEDICAL_SYMPTOM_KEYWORDS: tuple[str, ...] = (
    "胸痛",
    "胸闷",
    "心悸",
    "头晕",
    "严重关节疼痛",
    "心脏疼",
    "心绞痛",
)

MEDICAL_REPLY_TEMPLATE = (
    "我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。"
    "{symptom}属于需要重视的症状，建议你暂停训练，尽快咨询医生，"
    "由专业医师评估后再决定是否运动。"
)


def detect_medical_symptom(text: str) -> str | None:
    """检测文本中是否出现需要医学评估的症状，返回命中的症状词。

    Args:
        text: 用户输入（通常是聊天消息）。

    Returns:
        首个命中的症状词；未命中返回 None。
    """
    if not text:
        return None
    for keyword in MEDICAL_SYMPTOM_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def check_medical_risk(text: str) -> str | None:
    """命中症状时返回固定建议回复，否则返回 None。

    回复措辞与 CLAUDE.md 4.2 节逐字一致，{symptom} 替换为实际命中词。
    """
    symptom = detect_medical_symptom(text)
    if symptom is None:
        return None
    return MEDICAL_REPLY_TEMPLATE.format(symptom=symptom)

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


# ============================================================
# 极端节食拦截（CLAUDE.md 4.2：不推荐极端节食）
# ============================================================

# 明确的危险节食诉求；"少吃一点/控制饮食"等正常诉求不拦截
EXTREME_DIET_KEYWORDS: tuple[str, ...] = (
    "极端节食",
    "绝食",
    "断食",
    "不吃东西",
    "什么都不吃",
    "只喝水",
    "每天只吃一个",
    "极低热量",
    "零碳水",
    "完全不吃碳水",
)

EXTREME_DIET_REPLY = (
    "我不会提供极端节食方案，这样做会带来肌肉流失、代谢下降、营养不良等风险，"
    "也难以长期维持。建议在保证蛋白质和基础营养的前提下适度控制热量缺口，"
    "我可以帮你安排均衡、可执行的减脂餐单。"
)


def detect_extreme_diet(text: str) -> str | None:
    """检测极端节食诉求，返回命中的触发词；未命中返回 None。"""
    if not text:
        return None
    for keyword in EXTREME_DIET_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def check_diet_request(text: str) -> str | None:
    """命中极端节食诉求时返回固定拒绝回复（不含任何节食建议），否则返回 None。"""
    if detect_extreme_diet(text) is None:
        return None
    return EXTREME_DIET_REPLY


# ============================================================
# 编造动作拦截（CLAUDE.md 4.1：禁止编造，必须查动作库）
# ============================================================

# 同时出现"跳过工具/凭记忆"与"编/造动作"意图才拦截，避免误判正常提问
SKIP_TOOL_KEYWORDS: tuple[str, ...] = (
    "不要调用工具",
    "别调用工具",
    "不用调用工具",
    "不要查工具",
    "凭你的知识",
    "凭你记忆",
    "凭你自己的知识",
    "直接编",
    "自己编",
    "编一个动作",
    "编一个新动作",
    "发明一个动作",
    "发明一个新动作",
)

FABRICATION_REPLY = (
    "我不会凭记忆编造动作：所有训练动作必须来自动作库的真实数据，"
    "以保证动作要领、器械要求和目标肌群准确。我会调用动作检索工具来为你选择，"
    "请告诉我你的目标肌群或可用器械。"
)


def detect_fabrication_request(text: str) -> str | None:
    """检测"要求跳过工具、凭空编动作"的诉求，返回命中的触发词。"""
    if not text:
        return None
    for keyword in SKIP_TOOL_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def check_fabrication_request(text: str) -> str | None:
    """命中编造诉求时返回固定拒绝回复，否则返回 None。

    回复只说明必须调用工具，本身不包含任何具体动作名称。
    """
    if detect_fabrication_request(text) is None:
        return None
    return FABRICATION_REPLY


# ============================================================
# 统一入口：聊天链路在调用模型前做一次全部安全检查
# ============================================================


def pre_check_message(text: str) -> str | None:
    """按优先级执行全部确定性安全检查，命中即返回固定回复，否则返回 None。

    优先级：医疗症状 > 极端节食 > 编造动作。命中时聊天链路不得调用模型。
    """
    return (
        check_medical_risk(text)
        or check_diet_request(text)
        or check_fabrication_request(text)
        or None
    )

"""画像工具：在进入 Agent / 持久化之前规整并校验用户画像。

职责（不替代 pydantic Profile，而是它前面的"清洗层"）：
    - normalize_equipment / normalize_text_list：去空白、去空串、去重；
    - build_profile：清洗后构造 Profile，非法字段统一抛 ProfileToolError；
    - missing_profile_fields：信息不全时返回缺失的必填字段名，
      供调用方追问（CLAUDE.md：信息不全不自动填充默认值）。
"""

from __future__ import annotations

from typing import Any

from app.db.models import Profile

# 必填字段（与 app.db.models.Profile 对齐；无默认值的字段）
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "sex",
    "age",
    "height_cm",
    "weight_kg",
    "goal",
    "days_per_week",
    "equipment",
)


class ProfileToolError(Exception):
    """画像规整/校验失败。"""


def normalize_text_list(items: Any) -> list[str]:
    """规整字符串列表：逐项 strip、丢弃空串、保持顺序去重。

    Raises:
        ProfileToolError: 入参不是 list 或包含非字符串元素。
    """
    if items is None:
        return []
    if not isinstance(items, list):
        raise ProfileToolError("期望列表类型，实际为：" + type(items).__name__)
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ProfileToolError("列表中存在非字符串元素：" + repr(item))
        text = item.strip()
        if text and text not in result:
            result.append(text)
    return result


def normalize_equipment(items: Any) -> list[str]:
    """规整器械列表：逐项 strip + 小写后去重保序。

    器械名在 MCP 中是枚举式英文标识（dumbbell/barbell/bodyweight）。
    注意小写化必须在去重之前，否则 "Dumbbell" 和 "dumbbell" 都会保留。

    Raises:
        ProfileToolError: 入参不是 list 或包含非字符串元素。
    """
    if items is None:
        return []
    if not isinstance(items, list):
        raise ProfileToolError("期望列表类型，实际为：" + type(items).__name__)
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ProfileToolError("列表中存在非字符串元素：" + repr(item))
        text = item.strip().lower()
        if text and text not in result:
            result.append(text)
    return result


def build_profile(raw: dict[str, Any]) -> Profile:
    """清洗列表字段后构造 Profile；任何校验错误统一包成 ProfileToolError。

    非列表字段不做猜测性补全，直接交给 pydantic 判定（含枚举/范围约束）。
    """
    if not isinstance(raw, dict):
        raise ProfileToolError("画像必须是对象（dict）")
    data = dict(raw)
    try:
        data["equipment"] = normalize_equipment(data.get("equipment"))
        data["dietary_preferences"] = normalize_text_list(data.get("dietary_preferences"))
        data["allergies"] = normalize_text_list(data.get("allergies"))
        return Profile(**data)
    except ProfileToolError:
        raise
    except Exception as exc:
        raise ProfileToolError(str(exc)) from exc


def missing_profile_fields(raw: dict[str, Any]) -> list[str]:
    """返回缺失（None/空串/空列表）的必填字段名，按固定顺序。

    仅做"是否提供"的判断；字段合法性由 build_profile 负责。
    """
    if not isinstance(raw, dict):
        return list(REQUIRED_PROFILE_FIELDS)
    missing: list[str] = []
    for field in REQUIRED_PROFILE_FIELDS:
        value = raw.get(field)
        if (
            value is None
            or (isinstance(value, str) and not value.strip())
            or (isinstance(value, list) and not value)
        ):
            missing.append(field)
    return missing

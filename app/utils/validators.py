"""JSON Schema 校验工具。"""

from collections.abc import Iterable
from typing import Any

from jsonschema import Draft7Validator


def validate(instance: Any, schema: dict[str, Any]) -> None:
    """按 schema 校验 instance；不合法时抛出 jsonschema.ValidationError。

    Raises:
        jsonschema.ValidationError: 第一个校验错误。
    """
    Draft7Validator(schema).validate(instance)


def is_valid(instance: Any, schema: dict[str, Any]) -> bool:
    """instance 是否符合 schema。"""
    return Draft7Validator(schema).is_valid(instance)


def partition_valid(
    items: Iterable[dict[str, Any]], item_schema: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    """把列表项按 item_schema 拆成（合法项, 非法项数量）。

    用于出参校验：丢弃 MCP 返回中的畸形条目而不是让整条计划失败。
    """
    validator = Draft7Validator(item_schema)
    valid: list[dict[str, Any]] = []
    invalid_count = 0
    for item in items:
        if validator.is_valid(item):
            valid.append(item)
        else:
            invalid_count += 1
    return valid, invalid_count

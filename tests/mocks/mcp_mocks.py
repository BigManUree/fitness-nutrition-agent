"""MCP 故障 mock：供 monkeypatch 替换 app/mcp 下的客户端函数。

用法::

    from tests.mocks.mcp_mocks import mock_search_exercises_timeout
    from app.mcp import exerciseapi_client

    failure = mock_search_exercises_timeout()
    monkeypatch.setattr(exerciseapi_client, "search_exercises", failure)
    ...
    assert failure.calls == 2  # 首次调用 + 重试 1 次

每个工厂返回的 async 函数都带 calls 计数，便于断言重试次数。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.mcp.http_client import McpConnectionError, McpProtocolError


def _counted(func: Callable[..., Awaitable[Any]]):
    """给 async mock 挂上 calls 计数。"""

    async def wrapper(arguments: dict[str, Any]) -> Any:
        wrapper.calls += 1
        return await func(arguments)

    wrapper.calls = 0
    return wrapper


def mock_search_exercises_timeout():
    """模拟 exerciseapi 超时。

    真实链路中 http_client 会把 asyncio.TimeoutError 转换为
    McpConnectionError（工具层据此触发重试）。
    """

    async def timeout(arguments: dict[str, Any]) -> Any:
        raise McpConnectionError(
            "调用 MCP 工具 'search_exercises' 失败："
            "TimeoutError: 请求超时（30.0 秒）"
        )

    return _counted(timeout)


def mock_search_exercises_timeout_then_success():
    """模拟首次超时、重试成功（验证重试有效时只调 2 次且拿到数据）。"""
    state = {"failed": False}

    async def timeout_then_success(arguments: dict[str, Any]) -> Any:
        if not state["failed"]:  # 第一次调用：超时
            state["failed"] = True
            raise McpConnectionError(
                "调用 MCP 工具 'search_exercises' 失败：TimeoutError: 请求超时"
            )
        return {
            "data": [
                {
                    "id": "ex-1",
                    "name": "Barbell Bench Press",
                    "primaryMuscles": ["pectoralis major"],
                    "secondaryMuscles": [],
                    "equipment": "barbell",
                    "category": "strength",
                    "level": "intermediate",
                    "force": "push",
                    "mechanic": "compound",
                }
            ],
            "total": 1,
        }

    return _counted(timeout_then_success)


def mock_search_exercises_error():
    """模拟 exerciseapi 返回 500 错误。

    真实链路中 MCP result.is_error 会被 http_client 转换为
    McpProtocolError（同样触发重试 1 次）。
    """

    async def server_error(arguments: dict[str, Any]) -> Any:
        raise McpProtocolError(
            "MCP 工具 'search_exercises' 返回错误："
            "500 Internal Server Error: 动作服务暂时不可用"
        )

    return _counted(server_error)


def mock_search_nutrition_empty():
    """模拟 nutrition-mcp 成功响应但无匹配结果（返回空数组）。"""

    async def empty(arguments: dict[str, Any]) -> Any:
        return []

    return _counted(empty)

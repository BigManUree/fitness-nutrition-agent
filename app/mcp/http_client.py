"""MCP Streamable HTTP 传输层共享助手。

职责（仅传输，不含业务逻辑）：
    1. 与 MCP 服务完成 initialize 握手；
    2. 调用指定工具；
    3. 把返回内容块中的 JSON 文本解析为 dict/list。

业务层（app/tools/）通过本模块调用 MCP，不直接依赖 mcp SDK，
便于在测试中 mock，也便于异常的统一拆组（见 _flatten）。
"""

import asyncio
import json
import os
from collections.abc import Sequence
from typing import Any

from mcp.client.streamable_http import streamable_http_client

from mcp import ClientSession

# 默认调用超时（秒）
DEFAULT_TIMEOUT = float(os.getenv("MCP_TIMEOUT_SECONDS", "30"))


class McpConnectionError(RuntimeError):
    """MCP 连接/握手失败（重试 1 次后仍失败时抛出）。"""


class McpProtocolError(RuntimeError):
    """MCP 返回了错误内容，或返回内容无法解析为 JSON。"""


def _flatten(exc: BaseException) -> list[BaseException]:
    """递归展开 ExceptionGroup，返回叶子异常列表。

    anyio 常把连接阶段的 ConnectError 包成 ExceptionGroup，
    不拆组会看不到根因（与 scripts/test_mcp.py 保持一致）。
    """
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for sub in exc.exceptions:
            leaves.extend(_flatten(sub))
        return leaves
    return [exc]


def _root_cause(exc: BaseException) -> str:
    causes = _flatten(exc)
    return "; ".join(f"{type(c).__name__}: {c}" for c in causes)


async def call_tool(
    base_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """调用 MCP 工具并返回解析后的 JSON。

    Args:
        base_url: MCP 服务端点，如 http://localhost:8010/mcp。
        tool_name: MCP 工具名。
        arguments: 工具入参（已通过 JSON Schema 校验）。
        timeout: 单次调用超时秒数。

    Returns:
        TextContent 中 JSON 文本解析后的 dict/list。

    Raises:
        McpConnectionError: 连接/握手失败。
        McpProtocolError: 工具返回错误、无文本内容或 JSON 解析失败。
    """
    try:
        # asyncio.timeout 对整个握手+调用生效；call_tool 本身不支持 timeout 参数
        async with asyncio.timeout(timeout):
            async with streamable_http_client(base_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
    except Exception as exc:  # noqa: BLE001 - 传输层统一转换为 McpConnectionError
        raise McpConnectionError(
            f"调用 MCP 工具 {tool_name!r} 失败：{_root_cause(exc)}"
        ) from exc

    if result.is_error:
        text = _first_text(result.content)
        raise McpProtocolError(f"MCP 工具 {tool_name!r} 返回错误：{text}")

    text = _first_text(result.content)
    if text is None:
        raise McpProtocolError(f"MCP 工具 {tool_name!r} 未返回文本内容")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpProtocolError(
            f"MCP 工具 {tool_name!r} 返回内容不是合法 JSON：{exc}"
        ) from exc


def _first_text(content: Sequence[Any]) -> str | None:
    """提取内容块列表中的第一段 TextContent.text。"""
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return None

"""exerciseapi MCP 客户端（动作库）。

只做端点与工具名的封装，入参由 app/tools/exercise_tools.py 校验。
服务地址通过环境变量配置，默认 http://localhost:8010/mcp。
"""

import os
from typing import Any

from app.mcp.http_client import call_tool

EXERCISEAPI_MCP_URL = os.getenv("EXERCISEAPI_MCP_URL", "http://localhost:8010/mcp")

TOOL_NAME = "search_exercises"


async def search_exercises(arguments: dict[str, Any]) -> Any:
    """调用 exerciseapi 的 search_exercises，返回 MCP 原始 JSON。"""
    return await call_tool(EXERCISEAPI_MCP_URL, TOOL_NAME, arguments)

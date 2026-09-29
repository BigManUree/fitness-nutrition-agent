"""nutrition-mcp 客户端（营养数据）。

只做端点与工具名的封装，入参由 app/tools/nutrition_tools.py 校验。
服务地址通过环境变量配置，默认 http://localhost:8011/mcp。
"""

import os
from typing import Any

from app.mcp.http_client import call_tool

NUTRITION_MCP_URL = os.getenv("NUTRITION_MCP_URL", "http://localhost:8011/mcp")

TOOL_NAME = "nutrition_search"


async def search_nutrition(arguments: dict[str, Any]) -> Any:
    """调用 nutrition-mcp 的 nutrition_search，返回 MCP 原始 JSON。"""
    return await call_tool(NUTRITION_MCP_URL, TOOL_NAME, arguments)

"""测试 exerciseapi 与 nutrition-mcp 两个 MCP 服务的连通性。

对每个服务依次执行：
    1. initialize()       —— 完成 MCP 握手
    2. list_tools()       —— 列出可用工具
    3. call_tool(...)     —— search_exercises / nutrition_search 各调用一次

用法：
    uv run python scripts/test_mcp.py

服务地址（HTTP 端点）通过环境变量配置：
    EXERCISEAPI_MCP_URL   默认 http://localhost:8010/mcp
    NUTRITION_MCP_URL     默认 http://localhost:8011/mcp
"""

import asyncio
import os
import sys

from mcp.client.streamable_http import streamable_http_client

from mcp import ClientSession

# Windows 控制台默认 GBK，打印 ✓/✗ 会触发 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 单次打印的最大字符数，避免输出过大（CLAUDE.md 要求控制 MCP 输出规模）
MAX_PREVIEW_CHARS = 2000

EXERCISEAPI_URL = os.getenv("EXERCISEAPI_MCP_URL", "http://localhost:8010/mcp")
NUTRITION_URL = os.getenv("NUTRITION_MCP_URL", "http://localhost:8011/mcp")


def _flatten(exc: BaseException) -> list[BaseException]:
    """展开 ExceptionGroup，返回其中的叶子异常列表。"""
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for sub in exc.exceptions:
            leaves.extend(_flatten(sub))
        return leaves
    return [exc]


def _preview(text: str, limit: int = MAX_PREVIEW_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [已截断，共 {len(text)} 字符]"


async def check_server(name: str, url: str, tool_name: str, arguments: dict) -> bool:
    """测试单个 MCP 服务：握手 -> 列工具 -> 调用目标工具。成功返回 True。"""
    print(f"\n{'=' * 70}")
    print(f"[{name}] 连接 {url}")
    print("=" * 70)
    try:
        async with streamable_http_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. initialize 握手
                init_result = await session.initialize()
                print(f"[1/3] initialize 成功：{init_result.server_info.name} "
                      f"v{init_result.server_info.version}")

                # 2. 列出工具
                tools_result = await session.list_tools()
                tool_names = [tool.name for tool in tools_result.tools]
                print(f"[2/3] list_tools 成功，共 {len(tool_names)} 个：{tool_names}")

                if tool_name not in tool_names:
                    print(f"[3/3] 跳过：服务未提供工具 {tool_name!r}")
                    return False

                # 3. 调用工具
                print(f"[3/3] 调用 {tool_name}({arguments}) ...")
                result = await session.call_tool(tool_name, arguments=arguments)

                for i, block in enumerate(result.content, start=1):
                    text = getattr(block, "text", repr(block))
                    print(f"--- 返回内容块 {i} ---")
                    print(_preview(text))

                if result.is_error:
                    print(f"[{name}] 工具调用返回了错误内容")
                    return False

                print(f"[{name}] 连通性测试通过 ✓")
                return True
    except Exception as exc:  # noqa: BLE001 - 连通性脚本需捕获并报告所有异常
        causes = _flatten(exc)
        print(f"[{name}] 连接/调用失败（{len(causes)} 个原因）：")
        for cause in causes:
            print(f"  - {type(cause).__name__}: {cause}")
        return False


async def main() -> None:
    results = await asyncio.gather(
        check_server(
            "exerciseapi",
            EXERCISEAPI_URL,
            "search_exercises",
            {"muscle": "chest", "equipment": "dumbbell", "limit": 5},
        ),
        check_server(
            "nutrition-mcp",
            NUTRITION_URL,
            "nutrition_search",
            {"query": "chicken breast", "limit": 3},
        ),
    )

    print(f"\n{'=' * 70}\n汇总")
    print("=" * 70)
    for name, ok in zip(("exerciseapi", "nutrition-mcp"), results, strict=True):
        print(f"  {name:16}: {'通过 ✓' if ok else '失败 ✗'}")

    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

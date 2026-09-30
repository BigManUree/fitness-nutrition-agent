"""节点性能装饰器：统一记录 LangGraph 各节点的 token 消耗与耗时。

用法（同步或异步节点均可）::

    from app.utils.performance_logger import log_performance

    @log_performance("generate_plan")
    async def generate_plan(state: AgentState) -> AgentState:
        response = await llm.ainvoke(messages)
        ...
        result = AgentState(plan=plan)
        result[USAGE_KEY] = extract_llm_usage(response)  # 递交 token 用量
        return result

约定：
- token 用量由节点通过返回 dict 的 USAGE_KEY 键提供（装饰器读取后弹出，
  不进入 LangGraph 全局状态）；不调用 LLM 的节点 token 字段记 NULL。
- session_id 取 state["session_id"]，缺失时回退 state["user_id"]
  （项目以 user_id 作为 checkpointer thread_id）。
- 日志写入失败只告警、不影响节点正常返回：观测代码不能拖垮主链路。
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any

from app.db.sqlite_client import log_performance as db_log_performance
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 节点向装饰器传递 LLM token 用量的约定键（(input_tokens, output_tokens)）
USAGE_KEY = "__usage__"


def extract_llm_usage(response: Any) -> tuple[int | None, int | None]:
    """从 LLM 返回对象提取 (输入 token, 输出 token)，取不到返回 (None, None)。

    兼容三种形态：
    1. LangChain AIMessage.usage_metadata：input_tokens / output_tokens；
    2. OpenAI 兼容对象的 usage 属性：prompt_tokens / completion_tokens；
    3. LangChain 旧版 additional_kwargs["token_usage"]。
    """
    usage_metadata = getattr(response, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        return (
            _as_int(usage_metadata.get("input_tokens")),
            _as_int(usage_metadata.get("output_tokens")),
        )

    raw_usage = getattr(response, "usage", None)
    if raw_usage is not None:
        if callable(raw_usage):  # 部分客户端 usage 是方法
            raw_usage = raw_usage()
        return (
            _as_int(_usage_field(raw_usage, "prompt_tokens", "input_tokens")),
            _as_int(_usage_field(raw_usage, "completion_tokens", "output_tokens")),
        )

    additional = getattr(response, "additional_kwargs", None)
    if isinstance(additional, dict):
        token_usage = additional.get("token_usage")
        if isinstance(token_usage, dict):
            return (
                _as_int(token_usage.get("prompt_tokens")),
                _as_int(token_usage.get("completion_tokens")),
            )

    return None, None


def _usage_field(usage: Any, *names: str) -> Any:
    for name in names:
        if isinstance(usage, dict) and name in usage:
            return usage[name]
        if hasattr(usage, name):
            return getattr(usage, name)
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def log_performance(node_name: str) -> Callable:
    """装饰器工厂：记录被装饰节点的 token 消耗与 wall-clock 耗时（毫秒）。"""

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(
                state: Any, *args: Any, db_path: Any = None, **kwargs: Any
            ) -> Any:
                start = time.perf_counter()
                result: Any = None
                status = "success"
                error_message: str | None = None
                try:
                    result = await func(state, *args, **kwargs)
                    return result
                except Exception as exc:
                    status, error_message = "error", str(exc)
                    raise
                finally:
                    _write_row(
                        node_name, state, result, start, status, error_message, db_path
                    )

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(
            state: Any, *args: Any, db_path: Any = None, **kwargs: Any
        ) -> Any:
            start = time.perf_counter()
            result = None
            status = "success"
            error_message = None
            try:
                result = func(state, *args, **kwargs)
                return result
            except Exception as exc:
                status, error_message = "error", str(exc)
                raise
            finally:
                _write_row(
                    node_name, state, result, start, status, error_message, db_path
                )

        return sync_wrapper

    return decorator


def _write_row(
    node_name: str,
    state: Any,
    result: Any,
    start: float,
    status: str,
    error_message: str | None,
    db_path: Any = None,
) -> None:
    duration_ms = int((time.perf_counter() - start) * 1000)
    token_input = token_output = None
    if isinstance(result, dict) and USAGE_KEY in result:
        # 弹出约定键，不进入 LangGraph 状态
        token_input, token_output = result.pop(USAGE_KEY, (None, None))

    session_id = user_id = None
    if isinstance(state, dict):
        session_id = state.get("session_id") or state.get("user_id")
        user_id = state.get("user_id")

    try:
        db_log_performance(
            session_id=session_id,
            node_name=node_name,
            duration_ms=duration_ms,
            user_id=user_id,
            token_input=token_input,
            token_output=token_output,
            status=status,
            error_message=error_message,
            db_path=db_path,
        )
    except Exception as exc:  # 观测失败绝不影响主链路
        logger.warning("performance_log 写入失败（node=%s）：%s", node_name, exc)

"""统一日志入口。

用法：
    from app.utils.logger import get_logger
    logger = get_logger(__name__)

级别读 LOG_LEVEL（默认 INFO）；只配置一次控制台 handler，
避免 Streamlit 反复 rerun 时重复添加导致同一行日志打印多遍。
Windows 控制台显式用 UTF-8 输出，中文不触发 GBK 编码错误。
"""

from __future__ import annotations

import logging
import os
import sys

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_ROOT_LOGGER_NAME = "fitness_agent"


def get_logger(name: str | None = None) -> logging.Logger:
    """返回命名 logger；首次调用时完成全局 handler 配置。"""
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    if not root.handlers:
        level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        root.setLevel(getattr(logging, level_name, logging.INFO))

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
        # Windows：stdout 可能被重定向且默认 GBK
        if hasattr(handler.stream, "reconfigure"):
            handler.stream.reconfigure(encoding="utf-8", errors="replace")
        root.addHandler(handler)
        root.propagate = False

    if name and name != _ROOT_LOGGER_NAME:
        # 子 logger 继承根 logger 的级别与 handler，保持全应用格式一致
        return root.getChild(name)
    return root

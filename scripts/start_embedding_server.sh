#!/usr/bin/env bash
# llama-server 嵌入服务管理（bash 入口，逻辑在同名 .py 中）。
#
# 背景见 scripts/start_embedding_server.py 头部文档：绕过 Ollama 0.34.4
# embed 501，直接用自带 llama-server 加载 Qwen3-Embedding-8B GGUF。
#
# 用法：
#   scripts/start_embedding_server.sh up
#   scripts/start_embedding_server.sh status
#   scripts/start_embedding_server.sh down
#
# Git Bash 与 WSL（Windows 互操作开启）均可执行；找不到 uv 时退回 python。
set -euo pipefail

cd "$(dirname "$0")/.."

action="${1:-}"
if [[ "$action" != "up" && "$action" != "down" && "$action" != "status" ]]; then
    echo "用法: $0 up|down|status" >&2
    exit 2
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run python scripts/start_embedding_server.py "$action"
fi

exec python scripts/start_embedding_server.py "$action"

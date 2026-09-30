#!/bin/sh
# 容器入口：
#   1. 等待 Ollama 可达（有限次重试；超时仍不可达则拒绝启动）
#   2. 创建 SQLite / Chroma 数据目录
#   3. 数据库文件不存在时初始化（已存在则跳过，保护挂载卷数据）
#   4. exec 传入的命令（由 tini 包裹，负责信号转发与僵尸回收）
set -e

cd /app

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
SQLITE_DB_PATH="${SQLITE_DB_PATH:-/app/data/app.db}"
CHROMA_DB_PATH="${CHROMA_DB_PATH:-/app/data/chroma_db}"

# 等待参数均可经环境变量覆盖，默认约 60 秒
OLLAMA_WAIT_RETRIES="${OLLAMA_WAIT_RETRIES:-30}"
OLLAMA_WAIT_INTERVAL="${OLLAMA_WAIT_INTERVAL:-2}"

# 1. 等待 Ollama：容忍依赖与容器同时启动时的短暂未就绪
attempt=1
while [ "$attempt" -le "$OLLAMA_WAIT_RETRIES" ]; do
    if curl -sf "${OLLAMA_BASE_URL}/api/tags" > /dev/null; then
        echo "[entrypoint] Ollama 可用：${OLLAMA_BASE_URL}"
        break
    fi
    if [ "$attempt" -eq "$OLLAMA_WAIT_RETRIES" ]; then
        echo "[entrypoint] 错误：等待 ${OLLAMA_BASE_URL}/api/tags 超时" >&2
        echo "（已重试 ${OLLAMA_WAIT_RETRIES} 次，间隔 ${OLLAMA_WAIT_INTERVAL}s）" >&2
        echo "请确认宿主机已启动 ollama serve，且 OLLAMA_BASE_URL 配置正确。" >&2
        exit 1
    fi
    echo "[entrypoint] 等待 Ollama 就绪... (${attempt}/${OLLAMA_WAIT_RETRIES})"
    attempt=$((attempt + 1))
    sleep "$OLLAMA_WAIT_INTERVAL"
done

# 2. 数据目录
mkdir -p "$(dirname "$SQLITE_DB_PATH")"
mkdir -p "$CHROMA_DB_PATH"

# 3. 数据库初始化
if [ -f "$SQLITE_DB_PATH" ]; then
    echo "[entrypoint] 数据库已存在，跳过初始化：$SQLITE_DB_PATH"
else
    echo "[entrypoint] 初始化数据库：$SQLITE_DB_PATH"
    python scripts/init_db.py --path "$SQLITE_DB_PATH"
fi

# 4. 启动命令
exec "$@"

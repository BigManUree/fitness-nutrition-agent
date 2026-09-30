# 健身营养 Agent 运行镜像（单阶段构建）
FROM python:3.12-slim

# 运行期依赖：
#   curl —— entrypoint 探测 Ollama、容器健康检查（slim 默认不含）
#   tini —— PID 1 信号转发（即使 entrypoint 用 exec，多 worker 时仍稳妥）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# 从官方 uv 镜像复制二进制，无需额外安装
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 运行期环境变量默认值（compose / docker run -e 可覆盖）：
#   PATH                虚拟环境 bin 前置
#   PYTHONUNBUFFERED    日志实时输出，不缓冲
#   UV_*                容器内 uv 行为
#   数据与服务路径      与 entrypoint、compose 对齐
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    SQLITE_DB_PATH=/app/data/app.db \
    CHROMA_DB_PATH=/app/data/chroma

# 先复制依赖清单，利用层缓存：源码变动不触发依赖重装
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 再复制应用代码（.dockerignore 已排除本地库/索引/测试/密钥）
COPY app/ ./app/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
COPY data/ ./data/

# 入口脚本（Ollama 探测/建目录/建库后 exec CMD）
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 非 root 运行：创建用户并接管应用目录与数据目录
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/data"]

EXPOSE 8000

# 镜像级健康检查（默认 CMD 为 API；ui 服务在 compose 中覆盖）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/health || exit 1

# tini(PID1) -> entrypoint -> exec CMD：保证 SIGTERM 正确转发、僵尸进程被回收
ENTRYPOINT ["/usr/bin/tini", "--", "docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

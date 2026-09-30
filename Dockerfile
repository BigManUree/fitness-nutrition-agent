# 健身营养 Agent 运行镜像（单阶段构建）
FROM python:3.12-slim

# 从官方 uv 镜像复制二进制，无需 curl/pip 安装
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 虚拟环境 bin 提前加入 PATH（uv sync 之后即生效）
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# 先复制依赖清单，利用层缓存：源码变动不会触发重新安装依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 再复制应用代码与数据
COPY app/ ./app/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
COPY data/ ./data/

# 容器入口脚本（初始化数据目录/数据库后 exec CMD）
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

.PHONY: install dev api embedding embed-up embed-down embed-status \
	mcp-up mcp-down mcp-status test lint clean

# 安装依赖
install:
	uv sync

# 启动 Streamlit 前端（多页面模式）
dev:
	uv run streamlit run ui/app.py

# 启动 FastAPI 后端
api:
	uv run uvicorn app.main:app --reload --port 8000

# 启动嵌入服务（Qwen3-Embedding-8B-AWQ-INT4，RTX 4060 8GB）
embedding:
	ollama serve

# 启动/停止/查看 llama-server 嵌入旁路（默认 127.0.0.1:8001，OpenAI 兼容）
embed-up:
	uv run python scripts/start_embedding_server.py up

embed-down:
	uv run python scripts/start_embedding_server.py down

embed-status:
	uv run python scripts/start_embedding_server.py status

# 启动 MCP stdio→Streamable HTTP 桥接（8010 exerciseapi / 8011 nutrition-mcp）
mcp-up:
	uv run python scripts/start_mcp_servers.py up

# 停止 MCP 桥接（含无 PID 文件的孤儿进程）
mcp-down:
	uv run python scripts/start_mcp_servers.py down

# 查看 MCP 桥接运行状态
mcp-status:
	uv run python scripts/start_mcp_servers.py status

# 运行全部测试
test:
	uv run pytest tests -v

# 代码检查
lint:
	uv run ruff check app ui scripts tests

# 清理临时数据
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache

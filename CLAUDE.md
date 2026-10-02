# CLAUDE.md

> 本文件为 Claude Code 提供项目上下文与开发约束。每次会话开始时自动加载，请严格遵守。
> 详细需求见 `docs/requirements.md`（如已拆分）。

---

## 1. 项目概述

**项目名称**：健身营养 Agent
**一句话简介**：根据用户身体条件、训练目标和可用器械，生成可执行的每周健身计划与配套一日三餐示例。
**项目类型**：Agent + RAG 结合（需调用 MCP 工具、SQLite、Chroma）。
**MVP 范围**：只生成一周训练计划 + 一日三餐示例 + 基础动作替换。
**交付形态**：React + TypeScript + Vite 前端 SPA（`frontend/`，FastAPI 同源托管）；Streamlit 旧版（`ui/`）暂保留。
**成本约束**：每月 ≤ 500 元（豆包 API + 本地运行，无服务器成本）。

---

## 2. 技术栈

| 模块 | 选型 |
|------|------|
| 语言 | Python 3.12（**必须 3.12，不要用 3.14**） |
| 依赖管理 | `uv` + `pyproject.toml` + `uv.lock` |
| Agent 编排 | LangGraph |
| 大模型 | 豆包 API（Doubao） |
| 工具调用 | MCP（Model Context Protocol） |
| 向量库 | Chroma（本地持久化，`./data/chroma_db`） |
| 嵌入模型 | Qwen3-Embedding-8B（Ollama 本地服务，`dengcao/Qwen3-Embedding-8B:Q5_K_M`） |
| 数据库 | SQLite（`./data/app.db`） |
| 后端 | FastAPI + Uvicorn |
| 前端 | React 18 + TypeScript + Vite + Ant Design 5（`frontend/`，替代 Streamlit；`ui/` 旧版暂保留） |
| 测试 | pytest |
| 代码规范 | ruff |

**硬件环境**：RTX 4060 8GB，Ollama 本地运行嵌入模型。

---

## 3. 项目结构

```
fitness-nutrition-agent/
├── .env
├── .env.example
├── .gitignore
├── .python-version
├── .mcp.json                   # MCP 服务器配置
├── Makefile
├── pyproject.toml
├── uv.lock
├── README.md
├── CLAUDE.md
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置加载（读 .env）
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py            # LangGraph 工作流定义
│   │   ├── state.py            # AgentState 定义
│   │   ├── prompts.py          # System Prompt
│   │   └── nodes/
│   │       ├── collect_profile.py
│   │       ├── search_exercises.py
│   │       ├── search_nutrition.py
│   │       ├── generate_plan.py
│   │       └── validate_output.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── profile_tools.py
│   │   ├── exercise_tools.py
│   │   ├── nutrition_tools.py
│   │   └── schemas.py          # JSON Schema 定义
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── exerciseapi_client.py
│   │   └── nutrition_client.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── embedding.py        # Ollama 嵌入封装
│   │   ├── chroma_client.py    # Chroma 初始化与操作
│   │   └── profile_indexer.py  # 用户画像入库
│   ├── db/
│   │   ├── __init__.py
│   │   ├── sqlite_client.py
│   │   └── models.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── validators.py       # JSON Schema 校验
│
├── ui/
│   ├── app.py                  # Streamlit 入口（多页面导航）
│   ├── pages/
│   │   ├── 1_profile.py        # 用户画像表单
│   │   ├── 2_plan.py           # 生成计划
│   │   └── 3_chat.py           # 对话调整
│   └── components/
│       ├── profile_form.py
│       ├── plan_table.py
│       └── meal_table.py
│
├── frontend/                   # React + TS + Vite 前端（替代 ui/）
│   ├── index.html
│   ├── vite.config.ts
│   ├── src/
│   │   ├── api/               # fetch 客户端 + REST/SSE 端点
│   │   ├── auth/              # AuthProvider / useAuth
│   │   ├── pages/             # Login / Register / Profile / Plan / Chat
│   │   ├── components/        # ProtectedRoute / ProfileForm / PlanTable / MealTable
│   │   ├── hooks/             # useChatStream
│   │   └── types/             # Profile / Plan 类型
│
├── data/                       # 项目根目录下
│   ├── chroma_db/
│   └── app.db
│
├── tests/
│   ├── test_tools.py
│   ├── test_rag.py
│   ├── test_agent.py
│   └── test_data/
│       └── sample_queries.json
│
└── scripts/
    ├── init_db.py
    ├── check_ollama.py
    └── test_mcp.py
```

---

## 4. 核心开发规则（必须遵守）

### 4.1 数据来源原则
- **先查 MCP，再让 LLM 组装**。MCP 提供真实动作和食物数据，LLM 只负责根据用户约束做选择和编排。
- **禁止编造动作名称、器械要求、营养数据**。所有动作和食物必须来自 MCP 返回结果。
- 所有工具入参出参必须用 **JSON Schema** 定义，并做参数校验。

### 4.2 安全边界
- 不做医疗诊断，不推荐极端节食，不推荐超出用户器械范围的动作。
- 当用户提到 **胸痛、头晕、严重关节疼痛、心悸** 等需要医学评估的症状时，必须回复：
  > “我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。[具体症状] 属于需要重视的症状，建议你暂停训练，尽快咨询医生，由专业医师评估后再决定是否运动。”

### 4.3 输出格式
- 训练计划：Markdown 表格（动作 | 组数 | 次数 | 休息 | 说明）
- 营养餐单：Markdown 表格（餐次 | 食物 | 分量 | 说明）
- 每个模块后附简短解释：“为什么这样安排”

### 4.4 异常处理

| 场景 | 策略 |
|------|------|
| 信息不全 | 追问缺失字段，不自动填充默认值 |
| MCP 超时/报错 | 先重试 1 次；仍失败则**明确告知失败、不降级为模型内置知识**，建议用户稍后重试或调整筛选条件（宁可不给，不可错给；详见 `docs/bad_cases.md` 第 7 节） |
| JSON 格式错误 | 自动重试 1 次；仍失败则返回友好提示，请用户重新描述 |
| MCP 返回空结果 | 提示用户“未找到匹配的动作/食物”，建议调整筛选条件 |
| Ollama 未启动 | 应用启动时检查连通性（`scripts/check_ollama.py`），未连接则提示用户先启动 `ollama serve` 或使用 llama-server 旁路（`make embed-up`） |

### 4.5 记忆设计
- 会话记忆：LangGraph Checkpointer（内存）
- 用户画像：SQLite `user_profile` 表
- 生成的计划：SQLite `generated_plans` 表（MVP 可选）

---

## 5. 开发顺序

**优先级：先跑通 MCP，再跑通 RAG，最后组装端到端。**

| 阶段 | 任务 | 验证方式 |
|------|------|----------|
| 1 | 项目骨架 + 配置文件 | `uv sync` 成功，`make dev` 能启动空页面 |
| 2 | MCP 连通性测试 | `uv run python scripts/test_mcp.py` 返回数据 |
| 3 | SQLite 初始化 | `uv run python scripts/init_db.py` 建表成功 |
| 4 | 工具函数实现 | `uv run pytest tests/test_tools.py -v` 通过 |
| 5 | Ollama 嵌入服务 | `ollama serve` 运行中，`curl http://localhost:11434/api/embed -d '{"model":"dengcao/Qwen3-Embedding-8B:Q5_K_M","input":"测试"}'` 返回向量 |
| 6 | Chroma RAG | `uv run pytest tests/test_rag.py -v` 通过 |
| 7 | LangGraph 节点 | `uv run pytest tests/test_agent.py -v` 通过 |
| 8 | 端到端 Agent | 从表单到生成计划完整链路跑通 |
| 9 | Streamlit 页面 | 三页面可交互 |

---

## 6. 常用命令

```bash
# 安装依赖
uv sync

# 启动 Streamlit 前端
make dev

# 前端开发 / 构建（React + Vite，替代 Streamlit）
make frontend-dev
make frontend-build

# 启动 FastAPI 后端
make api

# 启动 Ollama 嵌入服务（如果未在后台运行）
ollama serve

# 验证 Ollama 嵌入模型可用
curl http://localhost:11434/api/embed \
  -d '{"model":"dengcao/Qwen3-Embedding-8B:Q5_K_M","input":"测试文本"}'

# 运行全部测试
make test

# 代码检查
make lint

# 初始化数据库
uv run python scripts/init_db.py

# 测试 MCP 连通性
uv run python scripts/test_mcp.py

# 启动/查看/停止本地 MCP HTTP 桥接（详见 7.4 节）
make mcp-up
make mcp-status
make mcp-down

# 启动/查看/停止 llama-server 嵌入旁路（Ollama 501 时使用，详见第 9 节）
make embed-up
make embed-status
make embed-down

# 检查 Ollama 连通性
uv run python scripts/check_ollama.py

# 清理临时数据
make clean
```

---

## 7. MCP 工具

### 7.1 MCP 配置方式

MCP 服务器通过项目根目录的 `.mcp.json` 管理，**不要在 CLAUDE.md 或代码中硬编码 URL**。

`.mcp.json` 示例：

```json
{
  "mcpServers": {
    "exerciseapi": {
      "command": "npx",
      "args": ["-y", "@exerciseapi/mcp-server"],
      "env": {
        "EXERCISEAPI_KEY": "${EXERCISEAPI_KEY}"
      }
    },
    "nutrition-mcp": {
      "command": "npx",
      "args": ["-y", "nutrition-mcp"],
      "env": {
        "USDA_API_KEY": "${USDA_API_KEY}"
      }
    }
  }
}
```

- `.env` 中存放 `EXERCISEAPI_KEY` 和 `USDA_API_KEY` 的真实值。
- `.mcp.json` 和 `.env` 都必须在 `.gitignore` 中。

### 7.2 已接入 MCP（MVP）

| MCP | 用途 | 主要工具 | 类型 |
|-----|------|----------|------|
| **exerciseapi** | 动作库 | `search_exercises`（按肌群、器械、难度筛选） | stdio（npx） |
| **nutrition-mcp** | 营养数据 | `nutrition_search`（食物营养查询，支持过敏原过滤） | stdio（npx） |

### 7.3 暂不接入（后续版本）

wger（需自部署）、FatSecret（OAuth 复杂）、Workout Planner AI（功能重叠）、DietsPremium（需额外 API Key）。

### 7.4 MCP 调用示例

```python
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@exerciseapi/mcp-server"],
    env={"EXERCISEAPI_KEY": "..."}
)

async with stdio_client(server_params) as (read_stream, write_stream):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool(
            "search_exercises",
            arguments={"muscle": "chest", "equipment": "dumbbell", "limit": 5}
        )
```

**Streamable HTTP 传输（mcp SDK 2.x）**：

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# 注意：函数名带下划线（1.x 旧名 streamablehttp_client 已废弃）；
# 上下文管理器返回 2 元组，1.x 的第三个 get_server_details 已移除。
async with streamable_http_client("http://localhost:XXXX/mcp") as (
    read_stream, write_stream
):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool(
            "search_exercises",
            arguments={"muscle": "chest", "equipment": "dumbbell", "limit": 5}
        )
        # result.content 是内容块列表，文本在 TextContent.text；result.isError 标识错误
```

**错误处理提示**：连接阶段异常可能被 anyio 包成 `ExceptionGroup`，需递归拆组才能看到
根因（如 `ConnectError`），参考 `scripts/test_mcp.py` 的 `_flatten()`。

**连通性测试**：`uv run python scripts/test_mcp.py` 通过环境变量 `EXERCISEAPI_MCP_URL`、
`NUTRITION_MCP_URL`（默认 `http://localhost:8010/mcp`、`http://localhost:8011/mcp`）
以 HTTP 模式测试，与 `.mcp.json` 的 stdio 方式不通用。

**本地 HTTP 桥接**：两个 MCP 包仅支持 stdio，应用代码走 HTTP 时需先启动 supergateway 桥接：

```bash
make mcp-up       # 启动（8010 exerciseapi / 8011 nutrition-mcp）
make mcp-status   # 查看状态
make mcp-down     # 停止（taskkill /T 杀整棵进程树）
```

无 make 的环境直接执行 `uv run python scripts/start_mcp_servers.py up|down|status [服务名]`。
脚本从 `.mcp.json` 读取命令与密钥，PID 文件在 `data/run/`，日志在 `logs/mcp/`。

**注意**：Claude Code 限制单次 MCP 输出在 25,000 token 以内。返回数据过大时，在工具函数中做截断或分页。

---

## 8. 数据存储

### 8.1 SQLite 表结构

```sql
CREATE TABLE user_profile (
    user_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE generated_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    plan_type TEXT,          -- 'weekly_plan' | 'daily_meals'
    plan_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 8.2 Chroma 配置

```python
import chromadb
from pathlib import Path
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

DB_DIR = Path("./data/chroma_db")
DB_DIR.mkdir(parents=True, exist_ok=True)

# 创建 Ollama 嵌入函数
ollama_ef = OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="dengcao/Qwen3-Embedding-8B:Q5_K_M",
)

client = chromadb.PersistentClient(path=str(DB_DIR))
collection = client.get_or_create_collection(
    name="user_profiles",
    embedding_function=ollama_ef,
    metadata={"hnsw:space": "cosine"}
)
```

**用户画像入库**：

```python
collection.upsert(
    ids=[user_id],
    documents=[profile_natural_language],  # 如“30岁男性，身高175cm，体重70kg，目标增肌...”
    metadatas=[{
        "user_id": user_id,
        "goal": goal,
        "equipment": ",".join(equipment),
        "allergies": ",".join(allergies)
    }]
)
```

**检索**：

```python
results = collection.query(
    query_texts=[current_query],
    n_results=3,
    where={"user_id": user_id}
)
```

---

## 9. RAG 策略

- **首要用途**：用户画像向量化检索（SQLite → 自然语言 → Chroma）。
- **通用知识库**：MVP 阶段不建，依赖 MCP；后续从 USDA FoodData Central + PubMed 摘要补充。
- **嵌入模型**：Qwen3-Embedding-8B（`dengcao/Qwen3-Embedding-8B:Q5_K_M`），通过 Ollama 本地服务提供，端口 11434。
- **Chroma 集成方式**：使用 `OllamaEmbeddingFunction` 直接对接 Ollama API。
- **分块策略**：用户画像作为整体 chunk；未来文档用语义分块（`semantic-text-splitter`）。
- **评估方式**：MVP 先人工测试；后续构建小型评估集（20-30 条）。

**llama-server 旁路（Ollama 0.34.4 embed 返回 501 时）**：

当 Ollama 版本错配导致 `/api/embed` 持续 501 时，绕过 Ollama 路由，直接用其
自带 llama-server 加载本地 GGUF，提供 OpenAI 兼容端点：

```bash
make embed-up        # 或 uv run python scripts/start_embedding_server.py up
make embed-status
make embed-down
```

- GGUF 路径从 Ollama manifest 自动解析，不写死 blob 文件名；PID 在 `data/run/`，日志在 `logs/embedding_server.log`。
- 就绪判定走 `/health`（端口可连时模型可能仍在加载）；后端可用 `EMBED_BACKEND=vulkan|cuda_v12|cuda_v13|cpu` 切换。
- 应用侧需设 `EMBED_PROVIDER=openai`，端点 `http://127.0.0.1:8001/v1`，客户端模型名 `qwen3-embedding`，输出 4096 维。

**Ollama 服务**（确保后台运行）：

```bash
# 启动 Ollama（通常安装后自动作为服务运行）
ollama serve

# 验证模型已下载
ollama list
# 应看到：dengcao/Qwen3-Embedding-8B:Q5_K_M

# 测试嵌入接口
curl http://localhost:11434/api/embed \
  -d '{"model":"dengcao/Qwen3-Embedding-8B:Q5_K_M","input":"测试文本"}'
```

**Chroma 集成代码**：

```python
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

ollama_ef = OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="dengcao/Qwen3-Embedding-8B:Q5_K_M",
)

collection = client.get_or_create_collection(
    name="user_profiles",
    embedding_function=ollama_ef,
    metadata={"hnsw:space": "cosine"}
)
```

Chroma 官方提供了 `OllamaEmbeddingFunction` 包装器，可以直接对接 Ollama 的嵌入 API。

**LangChain 集成代码**（如果节点内部用 LangChain 调用）：

```python
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(
    model="dengcao/Qwen3-Embedding-8B:Q5_K_M",
    base_url="http://localhost:11434",
)
```

LangChain 的 `OllamaEmbeddings` 支持 Qwen3-Embedding 系列，还可以通过 `dimensions` 参数指定输出维度（Qwen3-Embedding 支持 32–4096 维自定义输出）。

---

## 10. 环境变量

`.env.example` 模板：

```bash
# 豆包 API
DOUBAO_API_KEY=your_api_key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-pro-32k

# MCP 密钥
EXERCISEAPI_KEY=exlib_your_key_here
USDA_API_KEY=your_usda_key_here

# Ollama 嵌入服务
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=dengcao/Qwen3-Embedding-8B:Q5_K_M

# 数据库
SQLITE_DB_PATH=./data/app.db
CHROMA_DB_PATH=./data/chroma_db

# 应用配置
LOG_LEVEL=INFO
```

**严禁将 API Key 写入代码或提交到 Git。**

`.gitignore` 必须包含：

```
.venv/
__pycache__/
*.pyc
.env
.mcp.json
data/chroma_db/
data/app.db
```

---

## 11. 测试要求

- 每个模块必须有对应的 pytest 测试文件。
- 测试顺序：配置加载 → SQLite → Ollama 连通性 → Chroma → MCP 客户端 → 工具函数 → LangGraph 节点 → 端到端 → UI。
- 正向用例：10-15 条，覆盖增肌、减脂、塑形、不同器械、饮食偏好等组合。
- 边界用例：信息不全、目标模糊、年龄/伤病限制、每周训练天数极端值。
- 注入测试：越狱提示、诱导医疗诊断、要求编造动作。
- 工具报错模拟：手动断网或 mock 返回超时/空结果。
- 性能记录：token 消耗、端到端延迟，写入日志或 SQLite。

---

## 12. 已知风险与注意事项

1. **Python 版本**：必须使用 3.12，3.14 存在 LangGraph、FastAPI、Pydantic 兼容性问题。
2. **嵌入模型与 Ollama**：RTX 4060 8GB 使用 `dengcao/Qwen3-Embedding-8B:Q5_K_M`（约 5.6GB），Q5 量化在 8GB 显存上运行流畅。确保 `ollama serve` 在后台运行，否则 Chroma 检索会失败。
3. **MCP 工具数量**：MVP 只接入 `exerciseapi` 和 `nutrition-mcp`，避免 LLM 选择困难。
4. **Claude Code 上下文管理**：定期使用 `/compact` 压缩上下文，主要任务之间重启会话。
5. **Git 安全网**：每完成一个小任务就 commit，Claude Code 修改代码前会展示 diff 等你确认。
6. **MCP 输出限制**：单次输出不超过 25,000 token，超出时在工具函数中截断。
7. **Ollama 服务依赖**：所有涉及嵌入的操作（用户画像入库、检索）都依赖 Ollama 服务。如果 Ollama 未启动，Chroma 的 `upsert` 和 `query` 会报连接错误。建议在应用启动时检查 Ollama 连通性。

---

## 13. 参考文档

- 完整需求说明书：`docs/requirements.md`（第 1–5 步汇总）
- Bad Case 记录：`docs/bad_cases.md`（第 6 步创建）
- MCP 协议文档：https://modelcontextprotocol.io
- LangGraph 文档：https://langchain-ai.github.io/langgraph/
- Streamlit 多页面文档：https://docs.streamlit.io/develop/concepts/multipage-apps
- Ollama 嵌入 API：https://github.com/ollama/ollama/blob/main/docs/api.md#generate-embeddings

---

> **本文件是 Claude Code 的项目上下文基线。如有变更，请同步更新此文件。**
# 健身营养 Agent 🏋️🍱

根据用户身体条件、训练目标和可用器械，生成**每周健身计划**与**一日三餐示例**，并支持在对话中替换动作。

- **数据真实**：所有动作与食物来自 MCP 工具检索（exerciseapi / nutrition-mcp），LLM 只负责选择与编排，**不编造动作名称、器械与营养数据**。
- **安全边界**：不做医疗诊断；用户描述胸痛、头晕、严重关节疼痛、心悸等症状时，代码层直接拦截并给出固定就医建议（不依赖模型自觉）。
- **本地优先**：SQLite 存画像、Chroma + 本地嵌入模型做画像语义检索，月运行成本可控（≤500 元）。

## 技术栈

| 模块 | 选型 |
|---|---|
| 语言 | Python 3.12（**不支持 3.14**） |
| 依赖管理 | uv |
| Agent 编排 | LangGraph（MemorySaver Checkpointer） |
| 大模型 | OpenAI 兼容接口（默认 DeepSeek；缺 Key 时降级本地 Ollama） |
| 工具 | MCP（exerciseapi 动作库 + nutrition-mcp 营养数据） |
| 向量 / 嵌入 | Chroma + Qwen3-Embedding-8B（Ollama 或 llama-server 旁路） |
| 数据库 | SQLite |
| 界面 / 后端 | React + TypeScript + Vite（Ant Design）+ FastAPI；Streamlit 旧版暂保留 |
| 测试 / 规范 | pytest + ruff |

## 快速开始

### 1. 环境准备

```bash
# 必须 Python 3.12
uv sync

# 配置密钥（从模板复制后填入真实值；.env 已在 .gitignore 中）
cp .env.example .env
```

需要的 Key：`DEEPSEEK_API_KEY`（或其他 OpenAI 兼容服务）、`EXERCISEAPI_KEY`、`USDA_API_KEY`。
**严禁把 Key 写入代码或提交到 Git。**

### 2. 启动 MCP 桥接

两个 MCP 包仅支持 stdio，应用通过本地 HTTP 桥接访问：

```bash
make mcp-up       # 8010 exerciseapi / 8011 nutrition-mcp
make mcp-status   # 查看状态
```

### 3. 启动嵌入服务（二选一）

```bash
# 方式 A：Ollama（模型约 5.6GB，RTX 4060 8GB 可流畅运行）
ollama serve
uv run python scripts/check_ollama.py   # 验证连通性

# 方式 B：Ollama 版本错配（/api/embed 返回 501）时的 llama-server 旁路
make embed-up
```

### 4. 启动应用

```bash
# 前端（React，推荐）
make frontend-dev    # Vite dev server：http://localhost:5173（/api 代理到 8000）
make frontend-build  # 生产构建到 frontend/dist，由 FastAPI 静态托管（同源单服务）
make api             # FastAPI：http://localhost:8000（/docs 查看接口；已构建时 / 即前端页面）

make dev             # Streamlit 旧版（暂保留）：http://localhost:8501
```

前端已迁移到 **React + TypeScript + Vite（Ant Design）**：`make frontend-dev` 本地开发、
`make frontend-build` 构建产物由 FastAPI 托管（无需 CORS）；`make dev`（Streamlit）暂保留至切换稳定。

使用流程：**用户画像**（表单填写并保存）→ **生成计划** → **对话调整**（如"把卧推换成哑铃能做的动作"，候选动作可一键写回计划）。

## 测试与检查

```bash
make test         # 全部 pytest
make lint         # ruff
```

测试覆盖：工具层（含打桩 MCP）、SQLite、RAG、LangGraph 节点与 Checkpointer、FastAPI、
对话工具循环，以及注入/越狱安全测试（评估查询集见 `tests/test_data/sample_queries.json`）。

## 项目结构

```
app/
  agent/        LangGraph 工作流、节点、LLM 工厂、对话工具循环、安全守卫
  tools/        search_exercises / substitute_exercise / search_nutrition / 画像工具 + JSON Schema
  mcp/          MCP HTTP 传输与客户端
  rag/          嵌入、Chroma、画像入库
  db/           Profile 模型、SQLite 客户端
  utils/        日志、JSON Schema 校验
  main.py       FastAPI 入口
ui/             Streamlit 旧版多页面（画像 / 计划 / 对话调整，暂保留）
frontend/       React + TS + Vite 前端（替代 ui/）：api / auth / pages / components / hooks / types
scripts/        MCP 桥接、嵌入服务、初始化与连通性脚本
tests/          pytest 测试
docs/           需求说明书与 Bad Case 记录
```

## 安全与异常策略

- 器械越权防护：即使模型在工具参数里给出其他器械，服务端也强制以画像中的器械覆盖。
- 查无原动作：替换工具在动作库中定位不到原动作时，拒绝猜测肌群和候选，如实说明。
- 信息不全：返回缺失字段由用户补全，不自动填默认值。

更多已知问题与决策记录见 [`docs/bad_cases.md`](docs/bad_cases.md)。

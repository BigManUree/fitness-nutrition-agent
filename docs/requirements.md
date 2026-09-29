# 健身营养 Agent 需求说明书（第 1–5 步）

> 版本：v1.0  
> 日期：2026-09-28  
> 说明：本文档汇总第 1 步至第 5 步的全部确认决策，作为后续开发与测试的基线。

---

## 第 1 步：项目目标 + 边界

### 一句话项目简介
根据用户的身体条件、训练目标和可用器械，生成可执行的每周健身计划与配套一日三餐示例的健身营养 Agent。

### 项目类型
- **Agent + RAG 结合**：需要调用工具（MCP、SQLite、Chroma），同时需要向量检索用户画像。

### MVP 功能清单
1. 采集用户基础信息：身体条件、目标、可用器械、饮食偏好/过敏。
2. 生成一周训练计划：结构化输出动作、组数、次数、休息时间。
3. 生成一日三餐示例：结合营养目标与饮食限制，给出可执行餐单。
4. 支持基础多轮调整：例如“替换这个动作”“我不吃牛肉”。
5. 提供简单交互页面：Streamlit，可本地运行、可小范围分享。

### 不做清单（MVP 排除项）
- 不做长期打卡追踪与自动调整计划（后续版本）
- 不做健康设备同步（Fitbit/Apple Health 等）
- 不做复杂用户系统、登录、支付
- 不做医疗诊断或治疗建议
- 不做精确到克的营养计算（MVP 先给示例餐单）
- 不做飞书/钉钉/微信机器人
- 不做高并发、企业级监控
- 不做多用户数据隔离（MVP 可先单用户/本地）

### 交付形态
- **MVP 阶段**：Streamlit 本地页面
- **公测阶段（可选）**：Hugging Face Spaces / Render
- **长期阶段（可选）**：轻量云服务器 + Docker

### 成本约束
- 每月总成本 ≤ 500 元（豆包 API + 本地运行，无服务器成本）

---

## 第 2 步：技术选型

### 技术栈清单

| 模块 | 选型 | 说明 |
|------|------|------|
| Agent 编排 | **LangGraph** | 路线 B，有状态多步骤工作流 |
| 大模型 | **豆包 (Doubao)** | 支持 Function Calling 和 MCP |
| 工具调用 | **MCP** | 使用现成健身/营养 MCP |
| 知识库/RAG | **Chroma**（本地） | 用户画像向量化 |
| 嵌入模型 | **Qwen3-Embedding-8B** | 本地 GPU 部署，INT4 量化 |
| 后端 | **FastAPI** | 封装 Agent 逻辑 |
| 前端 | **Streamlit** | 数据展示型界面，多页面模式 |
| 数据库 | **SQLite** | 用户画像与计划存储 |
| 部署 | **本地运行** | 先不部署 |
| 依赖管理 | **uv + pyproject.toml** | Python 3.12 |
| Python 版本 | **3.12** | 兼容性最成熟 |

### MCP 工具精简方案（MVP）

| 用途 | 推荐 MCP | 理由 |
|------|----------|------|
| 动作库 | **exerciseapi MCP** | 2,198+ 人工核验动作，含肌群、器械、难度、安全提示 |
| 动作库备选 | Smart Rabbit MCP | 直接生成个性化训练计划，集成 PubMed 引用 |
| 营养数据 | **nutrition-mcp** | 本地 SQLite 缓存 326K+ 食物，USDA 回退，无 OAuth |
| 营养数据备选 | wellness-nourish | 本地优先，无需 OAuth，支持食物搜索与记录 |

**暂不接入**：wger（需自部署）、FatSecret（OAuth 复杂）、Workout Planner AI（功能重叠）、DietsPremium（需额外 API Key，超出 MVP 范围）。

### 环境与部署
- 本地运行
- Python 虚拟环境：`uv`
- 依赖管理：`pyproject.toml` + `uv.lock`

---

## 第 3 步：Agent 工作流、提示词、工具定义

### 1. 工作流设计（混合式）

```
用户打开 Streamlit 页面
    ↓
阶段 A：表单采集（必填字段）
性别 / 年龄 / 身高 / 体重 / 目标 / 每周训练天数 /
可用器械 / 饮食偏好与过敏
    ↓
阶段 B：Agent 追问（信息不全时触发）
检查必填字段 → 缺失则通过对话追问 → 补全后写入 Profile
    ↓
阶段 C：用户点击「生成计划」按钮
    ↓
LangGraph 执行链路：
① 读取 Profile（从 SQLite 加载）
② 调用 MCP：exerciseapi.search_exercises
   → 根据器械/难度/肌群筛选候选动作
③ 调用 MCP：nutrition-mcp.nutrition_search
   → 根据饮食偏好/过敏筛选候选食材
④ LLM 组装：基于 MCP 返回的真实数据 + Profile
   → 生成结构化周计划 + 一日三餐
⑤ 校验输出：JSON Schema 校验 + 安全规则检查
⑥ 返回结构化结果 → Streamlit 表格渲染
```

**关键设计原则**：先查 MCP，再让 LLM 组装。MCP 提供真实动作和食物数据，LLM 负责根据用户约束做选择和编排。

### 2. System Prompt 草稿

```markdown
## 角色
你是一位有 10 年经验的健身教练兼注册营养师，擅长为普通人制定可执行的训练和饮食计划。

## 能力边界
- 你只能基于工具返回的真实动作库和营养数据来制定计划。
- 你不得编造任何动作名称、器械要求或营养数据。
- 你不得进行医疗诊断，不得推荐极端节食方案。
- 你不推荐超出用户可用器械范围的动作。

## 工作流程
1. 当用户信息不全时，主动追问缺失的必填字段。
2. 生成计划前，先调用工具获取候选动作和食材数据。
3. 基于工具返回的数据，结合用户画像，组装训练计划和营养餐单。
4. 输出格式：
   - 训练计划：Markdown 表格（动作 | 组数 | 次数 | 休息 | 说明）
   - 营养餐单：Markdown 表格（餐次 | 食物 | 分量 | 说明）
   - 每个模块后附简短解释：“为什么这样安排”

## 禁止行为
- 不做医疗诊断
- 不推荐极端节食
- 不推荐超出用户器械范围的动作
- 不编造动作名称和营养数据
- 不给出“胸痛还能不能练”这类需要医学判断的建议

## 安全边界
当用户提到胸痛、头晕、严重关节疼痛、心悸等需要医学评估的症状时，
必须回复：“我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。
[具体症状] 属于需要重视的症状，建议你暂停训练，尽快咨询医生，
由专业医师评估后再决定是否运动。”
```

### 3. 工具清单（含 JSON Schema）

#### 工具 1：`collect_profile`

```json
{
  "name": "collect_profile",
  "description": "校验并保存用户画像，缺失字段返回待追问列表",
  "parameters": {
    "type": "object",
    "properties": {
      "sex": {"type": "string", "enum": ["male", "female"]},
      "age": {"type": "integer", "minimum": 14, "maximum": 80},
      "height_cm": {"type": "number"},
      "weight_kg": {"type": "number"},
      "goal": {"type": "string", "enum": ["fat_loss", "muscle_gain", "recomp", "general_fitness"]},
      "days_per_week": {"type": "integer", "minimum": 1, "maximum": 7},
      "equipment": {"type": "array", "items": {"type": "string"}},
      "dietary_preferences": {"type": "array", "items": {"type": "string"}},
      "allergies": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["sex", "age", "height_cm", "weight_kg", "goal", "days_per_week", "equipment"]
  }
}
```

#### 工具 2：`generate_weekly_plan`

```json
{
  "name": "generate_weekly_plan",
  "description": "基于用户画像和候选动作库，生成一周训练计划。必须先通过 search_exercises 获取候选动作。",
  "parameters": {
    "type": "object",
    "properties": {
      "profile": {"type": "object", "description": "用户画像"},
      "candidate_exercises": {
        "type": "array",
        "items": {"type": "object"},
        "description": "来自 exerciseapi MCP 的候选动作列表"
      }
    },
    "required": ["profile", "candidate_exercises"]
  }
}
```

#### 工具 3：`generate_daily_meals`

```json
{
  "name": "generate_daily_meals",
  "description": "基于用户画像和候选食物数据，生成一日三餐示例。必须先通过 nutrition_search 获取候选食物。",
  "parameters": {
    "type": "object",
    "properties": {
      "profile": {"type": "object"},
      "candidate_foods": {
        "type": "array",
        "items": {"type": "object"},
        "description": "来自 nutrition-mcp 的候选食物列表"
      },
      "target_calories": {"type": "number", "description": "可选，每日目标热量"}
    },
    "required": ["profile", "candidate_foods"]
  }
}
```

#### 工具 4：`substitute_exercise`

```json
{
  "name": "substitute_exercise",
  "description": "根据伤病约束或器械限制，为指定动作查找替代方案",
  "parameters": {
    "type": "object",
    "properties": {
      "original_exercise": {"type": "string"},
      "reason": {"type": "string", "description": "如：膝盖不适、没有哑铃"},
      "equipment_available": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["original_exercise", "reason"]
  }
}
```

#### 工具 5：`search_exercises`（封装 exerciseapi MCP）

```json
{
  "name": "search_exercises",
  "description": "从 exerciseapi.dev 搜索经过人工核验的动作，按肌群、器械、难度筛选",
  "parameters": {
    "type": "object",
    "properties": {
      "muscle": {"type": "string"},
      "equipment": {"type": "string"},
      "difficulty": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
      "limit": {"type": "integer", "default": 20}
    }
  }
}
```

#### 工具 6：`search_nutrition`（封装 nutrition-mcp）

```json
{
  "name": "search_nutrition",
  "description": "从 nutrition-mcp 搜索食物营养数据，支持过敏原过滤",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "allergen_exclude": {"type": "array", "items": {"type": "string"}},
      "limit": {"type": "integer", "default": 10}
    },
    "required": ["query"]
  }
}
```

### 4. 异常处理策略

| 场景 | 策略 |
|------|------|
| 信息不全 | 追问缺失字段，不自动填充默认值 |
| MCP 超时/报错 | 先重试 1 次；仍失败则明确告知失败、不降级为模型内置知识，建议稍后重试或调整筛选条件（宁可不给，不可错给；决策记录见 `docs/bad_cases.md` 第 7 节） |
| JSON 格式错误 | 自动重试 1 次；仍失败则返回友好提示，请用户重新描述 |
| 超出能力范围（如“胸痛还能练吗”） | 固定回复：“我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。胸痛属于需要重视的症状，建议你暂停训练，尽快咨询医生，由专业医师评估后再决定是否运动。” |
| MCP 返回空结果 | 提示用户“未找到匹配的动作/食物”，建议调整筛选条件 |

### 5. 记忆设计

| 层级 | 内容 | 存储位置 |
|------|------|----------|
| 会话记忆 | 当前对话历史 | LangGraph Checkpointer（内存） |
| 用户画像 | Profile（性别、年龄、身高、体重、目标、器械、偏好、过敏） | SQLite |
| 生成的计划 | 历史周计划、餐单（可选，MVP 可先不做） | SQLite |

**跨会话记忆加载流程**：
```
用户打开页面
    → 从 SQLite 读取 Profile（若存在）
    → 预填充表单
    → 用户可修改后重新生成
    → 生成完成后，将新 Profile 写回 SQLite
```

**SQLite 表结构建议**：
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

---

## 第 4 步：准备数据（RAG）

### 1. RAG 策略总览

| 项目 | 决策 |
|------|------|
| RAG 首要用途 | 用户画像向量化检索（SQLite → 自然语言 → Chroma） |
| 用户画像描述格式 | “30岁男性，身高175cm，体重70kg，目标增肌，每周练4天，有哑铃和杠铃，在健身房训练，膝盖有旧伤，不吃牛肉，西兰花” |
| 通用知识库 | MVP 阶段不建，依赖 MCP；后续从 USDA FoodData Central + PubMed 摘要渠道补充 |
| 嵌入模型 | `Qwen3-Embedding-8B`（本地 GPU 部署） |
| 分块策略 | 用户画像作为整体 chunk；未来文档用语义分块 |
| Chroma 操作方式 | `upsert` + `user_id` 元数据过滤 |
| Chroma 持久化路径 | `./chroma_db` |
| 评估方式 | MVP 先人工测试；后续构建小型评估集 |

### 2. 向量库与数据流设计

**Chroma 持久化配置**：
```python
import chromadb
from pathlib import Path

DB_DIR = Path("./chroma_db")
DB_DIR.mkdir(exist_ok=True)

client = chromadb.PersistentClient(path=str(DB_DIR))
```

**用户画像的 upsert 与元数据过滤**：
```python
collection = client.get_or_create_collection(
    name="user_profiles",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

collection.upsert(
    ids=[user_id],
    documents=[profile_natural_language],
    metadatas=[{
        "user_id": user_id,
        "goal": goal,
        "equipment": ",".join(equipment),
        "allergies": ",".join(allergies)
    }]
)

results = collection.query(
    query_texts=[current_query],
    n_results=3,
    where={"user_id": user_id}
)
```

**数据流全景**：
```
用户表单提交
    → Profile 写入 SQLite（结构化）
    → Profile 转自然语言描述
    → Qwen3-Embedding-8B 生成向量
    → upsert 到 Chroma（./chroma_db）

用户下次打开页面
    → 从 SQLite 读取 Profile 预填表单
    → 若用户要求调整计划，用当前查询检索 Chroma 中的画像
    → 检索结果 + MCP 数据 → LLM 组装新计划
```

### 3. 嵌入模型部署方案

| 方案 | 显存需求 | 适用场景 |
|------|----------|----------|
| BF16 全精度 | ~16 GB | RTX 4090 / A6000 等 |
| **INT4 量化（AWQ）** | ~8 GB | **RTX 4060 8GB 适用** |

**推荐方式**：通过 HuggingFace Embedding Server 与 Chroma 集成。
```python
from chromadb.utils.embedding_functions import HuggingFaceEmbeddingServer

embedding_fn = HuggingFaceEmbeddingServer(url="http://localhost:8001/embed")
```

**启动嵌入服务**：
```bash
vllm serve drawais/Qwen3-Embedding-8B-AWQ-INT4 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.94 \
    --port 8001
```

**向量维度**：Qwen3-Embedding-8B 输出 4096 维向量，用户画像文本量小，无需降维。

### 4. 语义分块策略（未来文档使用）

```python
from semantic_text_splitter import CharacterTextSplitter

splitter = CharacterTextSplitter()
chunks = splitter.chunks(document_text, chunk_capacity=(200, 1000))
```

**参数建议**：
- USDA 营养数据文档：`chunk_capacity=(64, 128)`
- PubMed 摘要：`chunk_capacity=(512, 1024)`

---

## 第 5 步：本地开发 + 搭建 MVP 原型

### 1. 开发环境配置

| 项目 | 决策 |
|------|------|
| 虚拟环境 | `uv` |
| Python 版本 | **3.12**（3.14 存在兼容性风险，已确认降至 3.12） |
| 依赖管理 | `pyproject.toml` + `uv.lock` |
| GPU | RTX 4060 8GB → Qwen3-Embedding-8B 用 **INT4 量化（AWQ）** |

**uv 初始化命令**：
```bash
uv init fitness-nutrition-agent
cd fitness-nutrition-agent
uv python pin 3.12
uv sync
uv add langgraph langchain fastapi uvicorn streamlit chromadb \
       mcp sentence-transformers semantic-text-splitter python-dotenv
```

### 2. 项目目录结构

```
fitness-nutrition-agent/
├── .env
├── .env.example
├── .gitignore
├── .python-version
├── Makefile
├── pyproject.toml
├── uv.lock
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── prompts.py
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
│   │   └── schemas.py
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── exerciseapi_client.py
│   │   └── nutrition_client.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── embedding.py
│   │   ├── chroma_client.py
│   │   └── profile_indexer.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── sqlite_client.py
│   │   └── models.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── validators.py
│
├── ui/
│   ├── app.py
│   ├── pages/
│   │   ├── 1_profile.py
│   │   ├── 2_plan.py
│   │   └── 3_chat.py
│   └── components/
│       ├── profile_form.py
│       ├── plan_table.py
│       └── meal_table.py
│
├── data/
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
    ├── start_embedding.sh
    └── test_mcp.py
```

**.gitignore 关键条目**：
```gitignore
.venv/
__pycache__/
*.pyc
.env
data/chroma_db/
data/app.db
```

**Makefile 示例**：
```makefile
.PHONY: install dev test lint embedding clean

install:
	uv sync

dev:
	uv run streamlit run ui/app.py

api:
	uv run uvicorn app.main:app --reload

embedding:
	bash scripts/start_embedding.sh

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check .

clean:
	rm -rf data/chroma_db/* data/app.db __pycache__
```

### 3. 开发顺序（先跑通 MCP，再跑通 RAG）

#### 阶段 1：MCP 连通性验证（最先做）

**目标**：确认 `exerciseapi` 和 `nutrition-mcp` 都能正常调用并返回数据。

```python
# scripts/test_mcp.py
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_exerciseapi():
    async with streamablehttp_client("http://localhost:XXXX/mcp") as (
        read_stream, write_stream, _
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("可用工具:", [t.name for t in tools.tools])
            result = await session.call_tool(
                "search_exercises",
                arguments={"muscle": "chest", "equipment": "dumbbell", "limit": 5}
            )
            print("搜索结果:", result)

if __name__ == "__main__":
    asyncio.run(test_exerciseapi())
```

#### 阶段 2：单元测试顺序

| 顺序 | 模块 | 测试命令/方式 |
|------|------|---------------|
| 1 | 配置加载 | `uv run python -c "from app.config import settings; print(settings)"` |
| 2 | SQLite 建表与读写 | `make init-db` + 手动插一条测试数据 |
| 3 | Qwen3-Embedding 服务 | `curl http://localhost:8001/embed -d '{"texts":["测试"]}'` |
| 4 | Chroma 存取 | `uv run pytest tests/test_rag.py -v` |
| 5 | **MCP 客户端** | `uv run python scripts/test_mcp.py` |
| 6 | 工具函数 | `uv run pytest tests/test_tools.py -v` |
| 7 | LangGraph 节点 | `uv run pytest tests/test_agent.py -v` |
| 8 | 端到端 | Streamlit 手动测试 |
| 9 | UI | Streamlit 手动测试 |

### 4. Streamlit 多页面布局

采用 `pages/` 目录 + `st.navigation` 方式，页面间通过 `st.session_state` 共享数据。

**`ui/app.py`（入口）**：
```python
import streamlit as st

st.set_page_config(page_title="健身营养 Agent", layout="wide")

if "profile" not in st.session_state:
    st.session_state.profile = None
if "plan" not in st.session_state:
    st.session_state.plan = None

pg = st.navigation([
    st.Page("pages/1_profile.py", title="用户画像", icon="👤"),
    st.Page("pages/2_plan.py", title="生成计划", icon="📋"),
    st.Page("pages/3_chat.py", title="对话调整", icon="💬"),
])
pg.run()
```

- **页面 1**：表单采集 + 自然语言预览 + 保存到 SQLite。
- **页面 2**：显示画像摘要 + 生成按钮 + 训练/营养表格。
- **页面 3**：聊天框 + `substitute_exercise` 工具调用。

### 5. 最小闭环（阶段 1 优先跑通 MCP）

```
用户填表单（Streamlit）
    → Profile 写入 SQLite
    → 点击「生成计划」
    → 调用 exerciseapi MCP：search_exercises（按器械筛选）
    → 调用 nutrition-mcp：nutrition_search（按偏好/过敏筛选）
    → 豆包 LLM 组装：基于 MCP 真实数据 + Profile
    → JSON Schema 校验
    → Streamlit 表格渲染
```

**阶段 1 只跑 MCP，暂时不做**：Chroma 画像检索、对话追问、动作替换、异常重试完整逻辑。

### 6. 交付物清单

| 交付物 | 状态 |
|--------|------|
| `pyproject.toml` + `uv.lock` | 待创建 |
| `.gitignore` + `Makefile` | 待创建 |
| 完整目录结构 | 待创建 |
| `scripts/test_mcp.py` | 优先创建 |
| `scripts/init_db.py` | 待创建 |
| `scripts/start_embedding.sh` | 待创建 |
| Streamlit 三页面骨架 | 待创建 |
| 本地可运行的 Agent 原型 | 阶段 1 目标 |

---

## 附：关键风险与提醒

1. **Python 版本**：已确认降至 3.12，避免 LangGraph、FastAPI、Pydantic 在 3.14 下的兼容性问题。
2. **MCP 工具数量**：MVP 阶段只接入 `exerciseapi` 和 `nutrition-mcp`，避免工具过多导致 LLM 选择困难。
3. **嵌入模型显存**：RTX 4060 8GB 需使用 INT4 量化版 Qwen3-Embedding-8B，`--max-model-len` 设为 8192。
4. **安全边界**：涉及胸痛、头晕、严重关节疼痛等症状时，必须触发固定安全回复，不得给出医学判断。

---

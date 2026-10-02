# React 前端迁移设计

> 日期：2026-10-01
> 分支：`feat/react-frontend-migration`
> 状态：已评审通过，待实现

## 1. 背景与目标

当前前端是 Streamlit 多页（`ui/`），通过"同进程直接 import `app.*`"的方式调用后端，
没有浏览器跨域、鉴权边界问题。现要替换为**真正的企业级现代前端**，面向"给很多人用"：

- **框架**：React 18 + TypeScript + Vite + **Ant Design 5**。
- **路由**：React Router，含受保护路由。
- **状态管理**：TanStack Query（服务端状态）+ 轻量 Auth Context。
- **通信**：通过 REST 调现有 FastAPI；对话调整走 **SSE 流式**。
- **构建部署**：Vite 构建产物由 FastAPI 静态托管（同源单服务）。

## 2. 范围（含 / 不含）

**含**：
- 三个现有页面的等价迁移：用户画像、生成计划、对话调整。
- 后端补齐：httpOnly cookie 鉴权、聊天 SSE 端点、画像规整 + 向量入库、SPA 静态托管。

**不含（明确排除）**：
- 计划历史列表/详情（`generated_plans` 读接口）。
- X-API-Key 中间件（当前代码并不存在，YAGNI）。
- Docker / docker-compose 改动（`docs/deployment.md` 与代码已脱节，后续单独处理）。
- 保留 `ui/` Streamlit 版本直到 React 切换稳定（不删除）。

## 3. 已锁定的决策

| 决策点 | 结论 |
|--------|------|
| 组件库 | Ant Design 5 |
| Token 存储 | httpOnly cookie（`SameSite=Lax`），`current_user` 优先读 cookie、回退 Bearer |
| 部署形态 | Vite dev proxy（`/api`、`/health` → `:8000`）+ FastAPI 托管 `dist`，不引入 CORS 中间件 |
| 聊天流式 | SSE（`text/event-stream`），前端用 `@microsoft/fetch-event-source` |
| 状态管理 | TanStack Query + Auth Context |

## 4. 现状事实（读代码确认）

已有端点（`app/main.py`，Bearer 会话鉴权，`sessions` 表）：

```
GET  /health
POST /api/auth/register      → {token, username}
POST /api/auth/login         → {token, username}
POST /api/auth/logout
GET  /api/me
PUT  /api/profile            → {username, status}
GET  /api/profile            → {username, profile}   (无画像时 404)
POST /api/plans/generate     → {username, plan, validation, errors}
```

真实缺口：

1. **无 CORS 中间件**（浏览器端 React 跨源会被拦）。
2. **无对话调整接口**（`3_chat.py` 直接 import `stream_with_tools` / `pre_check_message` 进程内跑）。
3. **`PUT /api/profile` 只 `save_profile`**：不做 `normalize_equipment` / `normalize_text_list`，
   也不 `index_profile` 进 Chroma（Streamlit 两样都做）。
4. **计划历史只写不读**（无 `load_plans` / `load_plan`）。

## 5. 后端改动

### 5.1 鉴权切 httpOnly cookie

- `register` / `login` 成功时，响应带
  `Set-Cookie: session=<token>; HttpOnly; SameSite=Lax; Path=/`。
- `current_user` 依赖：优先读请求 cookie `session`，回退读 `Authorization: Bearer <token>`
  （保留旧脚本 / pytest / 脚本的 Bearer 兼容）。
- `logout`：吊销会话 + `Set-Cookie` 清空（`Max-Age=0`）。
- 前端 fetch 一律 `credentials: 'include'`。

### 5.2 新增 `POST /api/plans/chat`（SSE 流式）

- **请求体**：`{plan, messages, message}`
  - `plan`：当前计划（随请求带，因为"替换动作"是客户端改的，DB 里仍是原始计划）。
  - `messages`：历史消息 `[{role: "user"|"assistant", content: str}]`（不含本轮最新）。
  - `message`：本轮最新用户输入。
  - 服务端画像从 DB 读取（`load_profile(user)`，权威来源，不信任客户端画像）。
  - 系统提示由服务端组装（沿用 `3_chat.py` 的 `CHAT_SYSTEM`，把 `plan` JSON 内嵌）。
- **服务端流程**：
  1. 无画像 → 返回 HTTP 400。
  2. `pre_check_message(message)` 命中（医疗症状 / 极端节食 / 编造诱导）→ 直接流式回固定话术。
  3. 否则 `get_llm` + `stream_with_tools`，逐 token 发 `event: token`。
  4. 结束后发一个 `event: done`，data 携带本轮 `tool_results`（替代候选）。
  5. 异常发 `event: error`。
- **SSE 事件协议**（`text/event-stream`，每条 `data:` 为 UTF-8 文本）：

```
event: token   data: <文本增量>
event: done    data: {"tool_results": [...]}
event: error   data: {"message": "<错误信息>"}
```

- `tool_results` 元素沿用 `substitute_exercise` 返回结构
  `{original_exercise, alternatives: [{name, ...}], total, source, note}`；
  前端取最后一条 `alternatives` 非空的作为 `pending_substitution`。

### 5.3 增强 `PUT /api/profile`

- save 前：`normalize_equipment`（去空白 / 去重 / 统一小写）+ `normalize_text_list`
  （`dietary_preferences`、`allergies`）。
- save 后：`index_profile`（Chroma 入库）；失败不阻塞，响应带
  `{username, status, indexing_warning: str|None}`。

### 5.4 SPA 静态托管

- 注册顺序（后者 catch 前者未命中）：`/health`、`/api/*` 路由 →
  `app.mount("/assets", StaticFiles(directory="frontend/dist/assets"))` →
  catch-all `GET /{full_path:path}` 返回 `FileResponse("frontend/dist/index.html")`
  （`dist` 未构建时返回 404）。使前端路由（`/profile` 等）刷新不 404。

## 6. 前端工程（`frontend/`）

### 6.1 目录结构

```
frontend/
├── package.json
├── vite.config.ts          # server.proxy: /api,/health → http://localhost:8000
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx             # 路由表
    ├── api/
    │   ├── client.ts       # fetch 封装：credentials include、统一 401/错误处理
    │   ├── auth.ts         # register/login/logout/me
    │   ├── profile.ts      # get/put profile
    │   ├── plan.ts         # generate
    │   └── chat.ts         # SSE 流式（fetch-event-source）
    ├── auth/
    │   ├── AuthProvider.tsx
    │   └── useAuth.ts
    ├── pages/
    │   ├── Login.tsx
    │   ├── Register.tsx
    │   ├── Profile.tsx
    │   ├── Plan.tsx
    │   └── Chat.tsx
    ├── components/
    │   ├── ProtectedRoute.tsx
    │   ├── ProfileForm.tsx
    │   ├── PlanTable.tsx
    │   └── MealTable.tsx
    ├── types/
    │   ├── profile.ts      # 严格镜像 Pydantic Profile
    │   └── plan.ts         # 宽松 Plan 类型
    └── hooks/
        ├── useProfile.ts
        └── useChatStream.ts
```

### 6.2 路由与门禁

| 路径 | 页面 | 门禁 |
|------|------|------|
| `/login` | 登录 | 公开 |
| `/register` | 注册 | 公开 |
| `/profile` | 画像表单 | 受保护 |
| `/plan` | 生成计划 | 受保护 |
| `/chat` | 对话调整 | 受保护（且需已有 plan） |

`ProtectedRoute`：无会话（`/api/me` 未通过）→ 跳 `/login`；已登录 → 渲染子路由。
`AuthProvider` 启动时调 `/api/me` 探测会话，暴露 `user` / `loading` / `logout`。

### 6.3 页面职责

- **Profile**：Ant Design Form 展示/编辑画像；提交调 `PUT /api/profile`；
  成功后进入下一步提示。
- **Plan**：`POST /api/plans/generate`（长请求 1–3 分钟，spinner + 提示，fetch 不设短超时）；
  渲染 `PlanTable`（一周计划 + weight/progression 引导）与 `MealTable`（三餐 + 营养目标闭环）。
- **Chat**：`useChatStream` 消费 SSE；历史气泡；`pending_substitution` 候选下拉 +
  "应用到计划"（客户端改 plan 状态，同现状，不落库）。

## 7. 类型与校验

- **Profile（严格）**：`sex: "male"|"female"`、`age: 14–80`、`height_cm/weight_kg > 0`、
  `goal: "fat_loss"|"muscle_gain"|"recomp"|"general_fitness"`、`days_per_week: 1–7`、
  `equipment: string[]`（非空）、`medical_conditions/dietary_preferences/allergies: string[]`（可空）。
- **Ant Design Form 校验规则** 镜像上述约束；提交前不给后端发非法值。
- **Plan（宽松）**：LLM 输出，关键渲染字段 `weekly_plan[]`、`daily_meals`、
  `nutrition_targets`、`nutrition_totals`、`rationale`、`weight_guidance`、
  `progression_guide`、`translation_warning`；缺失字段前端容错展示，不崩溃。

## 8. 错误处理

| 状态码 | 前端表现 |
|--------|----------|
| 401 | 清会话 → 跳 `/login` |
| 409 | 注册重名提示 |
| 422 | 回显 `missing_fields` / 校验提示 |
| 502 | "Agent 执行失败" + 建议 `make mcp-up` |

## 9. 测试

- **后端 pytest**：cookie 鉴权（set/read/回退 Bearer）、`/api/plans/chat` SSE
  （注入 fake `llm` / `tool_runner`，断言 token/done/error 事件与工具候选）、
  `PUT /api/profile` 规整 + 索引（mock Chroma，断言 warning）。
- **前端 Vitest + RTL**：`ProfileForm` 校验规则、`AuthProvider` 会话流转、
  api 客户端（mock fetch，断言 `credentials: 'include'` 与 401 处理）。

## 10. 命令与文档

- Makefile 增：`frontend-dev`（`npm --prefix frontend run dev`）、
  `frontend-build`（`npm --prefix frontend run build`）。
- 同步文档：`README.md`、`CLAUDE.md`（第 3 节结构、第 6 节命令、第 10 节环境变量若有新增）。

# React 前端迁移 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 React + TypeScript + Vite + Ant Design 重写三页前端，通过 REST 调现有 FastAPI，并补齐后端 cookie 鉴权 / 聊天 SSE / 画像规整入库 / SPA 托管。

**Architecture:** 后端在现有 `app/main.py` 上做 4 处增量（cookie 会话、SSE 聊天端点、画像增强、静态托管）；前端新建 `frontend/`（Vite SPA，TanStack Query 管服务端状态、Auth Context 管会话、React Router 受保护路由）。两部分以已固化的 REST/SSE 契约为边界，各自可独立测试。

**Tech Stack:** 后端 Python 3.12 + FastAPI + 现有 LangGraph/LangChain 组件；前端 React 18 + TypeScript + Vite + Ant Design 5 + React Router 6 + TanStack Query 5 + `@microsoft/fetch-event-source` + Vitest/RTL。

**Spec:** `docs/superpowers/specs/2026-10-01-react-frontend-migration-design.md`

## Global Constraints

- Python 3.12（`requires-python = ">=3.12,<3.13"`），ruff line-length=100、ignore E501。
- 前端构建产物目录固定为 `frontend/dist`，dev 端口 5173，后端 8000。
- 所有 `/api` 鉴权接口保持 **Bearer 回退兼容**：现有脚本与 `tests/test_api.py` 不得破坏。
- 每个 commit 信息末尾统一追加署名行（示例见 Task 1 第 5 步，后续每步同）：
  `Co-Authored-By: Claude Code <noreply@anthropic.com>`
- 前端 fetch 一律 `credentials: 'include'`；SSE 用 `@microsoft/fetch-event-source`。
- 不新增 Python 依赖（`httpx` 已在 pyproject 中，`fastapi.testclient.TestClient` 已用）。

## Review Focus

以下五类是 spec 隐含、但单个任务测试未必覆盖、最可能坑到使用者的输入/失败形态。每个都落到 owning task 的一条测试里。

1. **Cookie 缺失/过期但带 Bearer**：`current_user` 必须回退 Bearer 成功；cookie 在但会话已吊销 → 401（Task 1）。
2. **无画像时聊天**：`POST /api/plans/chat` 返回 HTTP 400，而不是 500 或静默空流（Task 3）。
3. **装备大小写/空格混入**：`PUT /api/profile` 收到 `[" Dumbbell ", "BARBELL"]` 入库为 `["dumbbell","barbell"]`（Task 2）。
4. **LLM 流中途抛异常**：SSE 必须发 `event: error`，客户端收到错误文案而非挂起（Task 3）。
5. **未构建前端**：`dist` 不存在时 `/api/*`、`/health` 仍可用，catch-all 返回 404 + 友好提示，应用能正常启动（Task 4）。

---

# Part A — 后端（可独立验证）

## Task 1: httpOnly cookie 会话鉴权

**Files:**
- Modify: `app/main.py:50-60`（`current_user`）、`:94-96`（`_issue_token`）、`:107-133`（register/login/logout）
- Create: `tests/test_auth_cookie.py`

**Interfaces:**
- Consumes: `app.db.users.create_session / get_session_user / revoke_session`（已存在）。
- Produces:
  - `current_user(authorization, session_cookie) -> str`：cookie 优先、Bearer 回退。
  - register/login 响应体仍含 `{token, username}`（脚本兼容）并 `Set-Cookie: session=...; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000`。
  - logout 响应 `delete_cookie("session")` + 吊销。

- [ ] **Step 1: 写失败测试**

`tests/test_auth_cookie.py`：

```python
"""httpOnly cookie 会话鉴权测试（Bearer 回退兼容）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "bob"
PASSWORD = "secret123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_cookie.db"))
    return TestClient(api_main.app)


def _register(c: TestClient) -> dict:
    resp = c.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_register_sets_session_cookie(client):
    body = _register(client)
    assert body["username"] == USERNAME
    assert "session" in client.cookies  # TestClient 的 cookie jar 已收到


def test_cookie_auth_without_header(client):
    _register(client)
    resp = client.get("/api/me")  # 不带 Authorization 头，走 cookie
    assert resp.status_code == 200
    assert resp.json()["username"] == USERNAME


def test_bearer_fallback_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_bearer.db"))
    bare = TestClient(api_main.app)
    token = _register(bare)["token"]
    bare.cookies.clear()  # 仅用 Bearer 头
    bare.headers["Authorization"] = f"Bearer {token}"
    assert bare.get("/api/me").status_code == 200


def test_logout_clears_cookie_and_revokes(client):
    _register(client)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_revoked_cookie_rejected(client):
    _register(client)
    client.post("/api/auth/logout")
    # 再注册同账号拿新 cookie 前，旧 cookie 应已失效
    assert client.get("/api/me").status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_auth_cookie.py -v`
Expected: 失败——register 目前不 Set-Cookie，`client.cookies` 无 `session`，cookie 鉴权 401。

- [ ] **Step 3: 实现**

改 `app/main.py`。顶部 import 增补：

```python
import json

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
```

替换 `current_user`（原 50-59 行）：

```python
SESSION_COOKIE_NAME = "session"


def current_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    """cookie 优先、Bearer 回退解析当前账号；无效则 401。"""
    token = session_cookie
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="缺失或格式错误的凭证，请登录")
    username = get_session_user(token)
    if username is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期，请重新登录")
    return username


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
```

替换 `_issue_token` 与 register/login/logout（原 94-133 行）：

```python
def _issue_token(username: str) -> dict[str, str]:
    return {"token": create_session(username), "username": username}


@app.post("/api/auth/register", status_code=201)
async def register(body: AuthRequest, response: Response) -> dict[str, str]:
    try:
        create_user(body.username, body.password)
    except UserExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = _issue_token(body.username)
    _set_session_cookie(response, payload["token"])
    return payload


@app.post("/api/auth/login")
async def login(body: AuthRequest, response: Response) -> dict[str, str]:
    if not verify_user(body.username, body.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    payload = _issue_token(body.username)
    _set_session_cookie(response, payload["token"])
    return payload


@app.post("/api/auth/logout")
async def logout(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    user: str = Depends(current_user),
    response: Response = None,  # FastAPI 自动注入
) -> dict[str, str]:
    token = session_cookie
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
    if token:
        revoke_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"username": user, "status": "logged_out"}
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_auth_cookie.py tests/test_api.py -v`
Expected: 全绿（`test_api.py` 的 Bearer 用例仍通过 = 回退兼容成立）。

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_auth_cookie.py
git commit -m "feat: httpOnly cookie 会话鉴权（Bearer 回退兼容）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 2: 画像保存增强（规整 + 向量入库）

**Files:**
- Modify: `app/main.py:145-153`（`put_my_profile`）
- Create: `tests/test_profile_api.py`

**Interfaces:**
- Consumes: `app.tools.profile_tools.build_profile`（抛 `ProfileToolError`）、`app.db.sqlite_client.save_profile`、`app.rag.profile_indexer.index_profile`。
- Produces: `app.main.index_profile_if_available(profile: Profile, user_id: str) -> str | None`（返回警告文案或 None）；`PUT /api/profile` 响应 `{username, status, indexing_warning: str|None}`。

- [ ] **Step 1: 写失败测试**

`tests/test_profile_api.py`：

```python
"""画像保存增强：装备规整 + 向量入库非阻塞告警。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "carol"
PASSWORD = "secret123"

BASE = {
    "sex": "female",
    "age": 28,
    "height_cm": 165.0,
    "weight_kg": 55.0,
    "goal": "fat_loss",
    "days_per_week": 3,
    "equipment": ["dumbbell"],
    "dietary_preferences": [],
    "allergies": [],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_profile.db"))
    c = TestClient(api_main.app)
    c.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD})
    # 默认不真正写向量库（测试无 Ollama）
    monkeypatch.setattr(api_main, "index_profile_if_available", lambda p, u: None)
    return c


def test_equipment_normalized_before_save(client):
    body = {**BASE, "equipment": [" Dumbbell ", "BARBELL", "dumbbell", "gym"]}
    resp = client.put("/api/profile", json=body)
    assert resp.status_code == 200
    got = client.get("/api/profile").json()["profile"]["equipment"]
    assert got == ["gym"]  # 小写去重后，gym 折叠为唯一值


def test_indexing_failure_sets_warning(client, monkeypatch):
    def boom(profile, user_id):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(api_main, "index_profile_if_available", boom)
    resp = client.put("/api/profile", json=BASE)
    body = resp.json()
    assert body["status"] == "saved"
    assert body["indexing_warning"] is not None


def test_indexing_success_no_warning(client):
    resp = client.put("/api/profile", json=BASE)
    assert resp.json()["indexing_warning"] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_profile_api.py -v`
Expected: 失败——当前 `put_my_profile` 不规整、不索引、响应无 `indexing_warning`。

- [ ] **Step 3: 实现**

改 `app/main.py`。在 `put_my_profile` 上方加模块级 helper，并替换端点（原 145-153 行）：

```python
def index_profile_if_available(profile: Profile, user_id: str) -> str | None:
    """把画像写入向量库；失败返回警告文案（不抛），成功返回 None。"""
    try:
        from app.rag.profile_indexer import index_profile

        index_profile(profile, user_id)
    except Exception as exc:
        return f"向量入库失败（{exc}），不影响生成计划"
    return None


@app.put("/api/profile")
async def put_my_profile(
    profile: Profile, user: str = Depends(current_user)
) -> dict[str, Any]:
    from app.tools.profile_tools import ProfileToolError, build_profile

    try:
        normalized = build_profile(profile.model_dump())
    except ProfileToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        save_profile(normalized, user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"画像保存失败：{exc}") from exc
    return {
        "username": user,
        "status": "saved",
        "indexing_warning": index_profile_if_available(normalized, user),
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_profile_api.py tests/test_api.py -v`
Expected: 全绿（`test_api.py::test_profile_save_get_roundtrip` 仍 200 + `status=saved`）。

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_profile_api.py
git commit -m "feat: 画像保存规整 + 向量入库非阻塞告警

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 3: 聊天 SSE 端点

**Files:**
- Modify: `app/agent/chat_adjust.py`（新增 `CHAT_SYSTEM_TEMPLATE` + `build_chat_system_prompt`）
- Modify: `app/main.py`（新增 `ChatRequest` + `POST /api/plans/chat`）
- Create: `tests/test_chat_api.py`

**Interfaces:**
- Consumes: `app.agent.safety.pre_check_message(text) -> str|None`、`app.agent.llm.get_llm(json_mode=False, temperature=0.4)`、`app.agent.chat_adjust.stream_with_tools(llm, messages, profile, tool_results=[]) -> Iterator[str]`、`app.db.sqlite_client.load_profile`。
- Produces:
  - `build_chat_system_prompt(plan: dict) -> str`
  - `POST /api/plans/chat`，body `{plan, messages: [{role, content}], message}`，响应 `text/event-stream`，事件 `token` / `done` / `error`。

- [ ] **Step 1: 写失败测试**

`tests/test_chat_api.py`：

```python
"""聊天 SSE 端点测试（注入 fake stream，不依赖 LLM / MCP）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as api_main

USERNAME = "dave"
PASSWORD = "secret123"

PROFILE = {
    "sex": "male",
    "age": 30,
    "height_cm": 175.0,
    "weight_kg": 72.0,
    "goal": "muscle_gain",
    "days_per_week": 4,
    "equipment": ["barbell"],
    "dietary_preferences": [],
    "allergies": [],
}

PLAN = {"weekly_plan": [], "daily_meals": {}, "rationale": "x"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test_chat.db"))
    c = TestClient(api_main.app)
    c.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD})
    c.put("/api/profile", json=PROFILE)
    return c


def test_chat_without_profile_400(client):
    bare = TestClient(api_main.app)
    bare.post("/api/auth/register", json={"username": "eve", "password": "secret123"})
    resp = bare.post(
        "/api/plans/chat", json={"plan": PLAN, "messages": [], "message": "hi"}
    )
    assert resp.status_code == 400


def test_chat_guard_reply_streams(client, monkeypatch):
    def should_not_run(*a, **k):
        raise AssertionError("命中安全守卫时不应调 stream_with_tools")

    monkeypatch.setattr(api_main, "stream_with_tools", should_not_run)
    resp = client.post(
        "/api/plans/chat",
        json={"plan": PLAN, "messages": [], "message": "我胸痛还能继续练吗"},
    )
    assert resp.status_code == 200
    text = resp.text
    assert "event: token" in text
    assert "建议你暂停训练" in text
    assert "event: done" in text


def test_chat_streams_tokens_and_tool_results(client, monkeypatch):
    def fake_stream(llm, messages, profile, tool_results=None):
        yield "候选："
        yield "Dumbbell Press"
        if tool_results is not None:
            tool_results.append(
                {
                    "original_exercise": "卧推",
                    "alternatives": [{"name": "Dumbbell Press"}],
                    "total": 1,
                    "source": "mcp",
                }
            )

    monkeypatch.setattr(api_main, "stream_with_tools", fake_stream)
    monkeypatch.setattr(api_main, "get_llm", lambda **kw: object())
    resp = client.post(
        "/api/plans/chat",
        json={"plan": PLAN, "messages": [], "message": "把卧推换成哑铃"},
    )
    text = resp.text
    assert "Dumbbell Press" in text
    assert '"tool_results"' in text
    assert '"alternatives"' in text


def test_chat_error_emits_error_event(client, monkeypatch):
    def boom(llm, messages, profile, tool_results=None):
        yield "开始"
        raise RuntimeError("llm 挂了")

    monkeypatch.setattr(api_main, "stream_with_tools", boom)
    monkeypatch.setattr(api_main, "get_llm", lambda **kw: object())
    resp = client.post(
        "/api/plans/chat",
        json={"plan": PLAN, "messages": [], "message": "你好"},
    )
    assert "event: error" in resp.text
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_chat_api.py -v`
Expected: 失败——`/api/plans/chat` 不存在（404）。

- [ ] **Step 3: 实现**

(3a) `app/agent/chat_adjust.py` 文件顶部 `from __future__ import annotations` 之后加 `import json`，并在 `default_tool_runner` 前新增：

```python
CHAT_SYSTEM_TEMPLATE = """你是健身营养 Agent 的对话助手，帮助用户理解和微调"已生成的计划"。

规则：
1. 普通问答只能围绕下方计划内容；不要编造计划之外的新动作或新食物。
2. 当用户要求"替换/换掉某个动作"时，必须调用 substitute_exercise 工具，
   并根据工具返回的真实候选回答；工具返回为空时如实转述，不要自己编候选。
3. 不做医疗诊断，不推荐极端节食或危险动作。
4. 如果用户描述胸痛、头晕、严重关节疼痛、心悸等症状，回复：
   "我没办法判断你的身体情况，不能给出是否可以继续锻炼的建议。该症状属于需要重视的症状，建议你暂停训练，尽快咨询医生，由专业医师评估后再决定是否运动。"
5. 用简洁中文回答；列出候选动作时保留动作原名（英文）。

当前计划：
{plan_json}"""


def build_chat_system_prompt(plan: dict[str, Any]) -> str:
    """把当前计划 JSON 内嵌进对话系统提示（plan 随客户端请求带入）。"""
    return CHAT_SYSTEM_TEMPLATE.format(plan_json=json.dumps(plan, ensure_ascii=False))
```

(3b) `app/main.py`：顶部 import 增补：

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from fastapi.responses import StreamingResponse

from app.agent.chat_adjust import build_chat_system_prompt, stream_with_tools
from app.agent.llm import get_llm
from app.agent.safety import pre_check_message
```

在 `PlanGenerateRequest` 之后新增请求模型与 SSE helper，并在 `generate_plan_endpoint` 之后新增端点：

```python
class ChatRequest(BaseModel):
    """对话调整请求：plan 随请求带入（替换动作后 DB 里仍是原始计划）。"""

    plan: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, str]] = Field(default_factory=list)
    message: str = Field(min_length=1)


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/plans/chat")
def chat_stream(
    request: ChatRequest, user: str = Depends(current_user)
) -> StreamingResponse:
    profile = load_profile(user)
    if profile is None:
        raise HTTPException(status_code=400, detail="尚未填写画像，无法进行对话调整")
    profile_data = profile.model_dump()

    def generate() -> Any:
        guard = pre_check_message(request.message)
        if guard is not None:
            yield _sse_event("token", guard)
            yield _sse_event("done", {"tool_results": []})
            return
        try:
            llm = get_llm(json_mode=False, temperature=0.4)
            messages: list[Any] = [
                SystemMessage(content=build_chat_system_prompt(request.plan))
            ]
            for m in request.messages:
                cls = HumanMessage if m.get("role") == "user" else AIMessage
                messages.append(cls(content=m.get("content", "")))
            messages.append(HumanMessage(content=request.message))
            tool_results: list[dict[str, Any]] = []
            for text in stream_with_tools(
                llm, messages, profile_data, tool_results=tool_results
            ):
                yield _sse_event("token", text)
            yield _sse_event("done", {"tool_results": tool_results})
        except Exception as exc:
            yield _sse_event("error", {"message": f"调用模型失败：{exc}"})

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_chat_api.py tests/test_chat_adjust.py -v`
Expected: 全绿（`chat_adjust` 现有测试不破坏）。

- [ ] **Step 5: Commit**

```bash
git add app/agent/chat_adjust.py app/main.py tests/test_chat_api.py
git commit -m "feat: 对话调整 SSE 端点 /api/plans/chat

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 4: SPA 静态托管 + catch-all

**Files:**
- Modify: `app/main.py`（文件末尾）
- Create: `tests/test_spa.py`

**Interfaces:**
- Consumes: `fastapi.staticfiles.StaticFiles`、`fastapi.responses.FileResponse`。
- Produces: 模块级 `FRONTEND_DIST: Path`；`GET /{full_path:path}` catch-all（`include_in_schema=False`）。

- [ ] **Step 1: 写失败测试**

`tests/test_spa.py`：

```python
"""SPA 静态托管：dist 存在返回 index.html，缺失则 404 且不破坏 /api。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as api_main


def test_spa_fallback_returns_index(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA-ROOT</html>", encoding="utf-8")
    monkeypatch.setattr(api_main, "FRONTEND_DIST", dist)
    resp = TestClient(api_main.app).get("/profile")
    assert resp.status_code == 200
    assert "SPA-ROOT" in resp.text


def test_spa_fallback_without_dist_404(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "FRONTEND_DIST", tmp_path / "missing")
    resp = TestClient(api_main.app).get("/profile")
    assert resp.status_code == 404


def test_api_routes_unaffected_by_fallback():
    bare = TestClient(api_main.app)
    assert bare.get("/health").status_code == 200
    assert bare.get("/api/me").status_code == 401  # 走鉴权，不被 catch-all 吞掉
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_spa.py -v`
Expected: 失败——`/profile` 当前 404 且无 catch-all（无 `FRONTEND_DIST` 属性，monkeypatch 报 AttributeError）。

- [ ] **Step 3: 实现**

`app/main.py` 顶部 import 增补（若 Task 3 已加过 `StreamingResponse`，把它**合并**为下面这一行，不要重复 import）：

```python
from pathlib import Path

from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
```

文件**末尾**追加（在所有 `/api` 路由之后）：

```python
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app.mount(
    "/assets",
    StaticFiles(directory=str(FRONTEND_DIST / "assets"), check_dir=False),
    name="assets",
)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="前端未构建：请先运行 make frontend-build")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_spa.py tests/test_api.py -v`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_spa.py
git commit -m "feat: SPA 静态托管 + 前端路由 catch-all

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

# Part B — 前端（`frontend/`）

## Task 5: 脚手架（Vite + React + TS + AntD + Vitest）

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/vitest.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/test/setup.ts`, `frontend/src/test/smoke.test.tsx`
- Modify: `.gitignore`（追加前端忽略）

**Interfaces:**
- Produces: 可运行的 dev server（`:5173`，`/api`、`/health` 代理到 `:8000`）；测试环境 jsdom + RTL。

- [ ] **Step 1: 写文件**

`frontend/package.json`：

```json
{
  "name": "fitness-agent-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@microsoft/fetch-event-source": "^2.0.1",
    "@tanstack/react-query": "^5.62.0",
    "antd": "^5.22.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

`frontend/vite.config.ts`：

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
```

`frontend/vitest.config.ts`：

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
});
```

`frontend/tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts", "vitest.config.ts"]
}
```

`frontend/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>健身营养 Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/main.tsx`：

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

`frontend/src/App.tsx`（骨架，指向尚未创建的路由页）：

```tsx
import { Routes, Route, Navigate } from 'react-router-dom';

export default function App() {
  return (
    <Routes>
      <Route path="*" element={<Navigate to="/plan" replace />} />
    </Routes>
  );
}
```

`frontend/src/test/setup.ts`：

```ts
import '@testing-library/jest-dom';
```

`frontend/src/test/smoke.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';

describe('smoke', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(document.body).toBeInTheDocument();
  });
});
```

`.gitignore` 末尾追加：

```
# 前端
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: 安装并跑冒烟测试**

Run: `cd frontend && npm install && npm test`
Expected: 1 个 smoke 测试通过。

- [ ] **Step 3: 验证构建类型检查**

Run: `cd frontend && npm run build`
Expected: `tsc` 无类型错误，产出 `frontend/dist/`。

- [ ] **Step 4: Commit**

```bash
git add frontend .gitignore
git commit -m "chore: React+TS+Vite+AntD 前端脚手架

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 6: 类型 + API 客户端

**Files:**
- Create: `frontend/src/types/profile.ts`, `frontend/src/types/plan.ts`, `frontend/src/api/client.ts`, `frontend/src/api/auth.ts`, `frontend/src/api/profile.ts`, `frontend/src/api/plan.ts`, `frontend/src/api/chat.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces:
  - `ApiError(status, detail)` + `isUnauthorized(err) -> bool`
  - `apiFetch<T>(path, init) -> Promise<T>`（`credentials: 'include'`，非 2xx 抛 `ApiError`）
  - `register/login/logout/me`、`getProfile/saveProfile`、`generatePlan`、`streamChat(plan, messages, message, handlers, signal)`。

- [ ] **Step 1: 写失败测试**

`frontend/src/api/client.test.ts`：

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { apiFetch, ApiError, isUnauthorized } from './client';

describe('apiFetch', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends credentials include and parses JSON', async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ username: 'alice' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', spy);

    const data = await apiFetch<{ username: string }>('/api/me');
    expect(data.username).toBe('alice');
    const [, init] = spy.mock.calls[0];
    expect(init.credentials).toBe('include');
  });

  it('throws ApiError with status on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '未登录' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    const err = await apiFetch('/api/me').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(isUnauthorized(err)).toBe(true);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 失败——`./client` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/types/profile.ts`：

```ts
export type Sex = 'male' | 'female';
export type Goal = 'fat_loss' | 'muscle_gain' | 'recomp' | 'general_fitness';

export interface Profile {
  sex: Sex;
  age: number;
  height_cm: number;
  weight_kg: number;
  goal: Goal;
  days_per_week: number;
  equipment: string[];
  medical_conditions?: string[];
  dietary_preferences?: string[];
  allergies?: string[];
}
```

`frontend/src/types/plan.ts`：

```ts
export interface Exercise {
  name?: string;
  name_zh?: string;
  name_en?: string;
  sets?: number;
  reps?: string;
  rest?: string;
  note?: string;
  weight?: string;
  rpe?: string;
  [k: string]: unknown;
}

export interface PlanDay {
  day?: number;
  focus?: string;
  exercises?: Exercise[];
  [k: string]: unknown;
}

export interface MealItem {
  food?: string;
  food_zh?: string;
  amount?: string;
  note?: string;
  [k: string]: unknown;
}

export interface DailyMeals {
  breakfast?: MealItem[];
  lunch?: MealItem[];
  dinner?: MealItem[];
  [k: string]: MealItem[] | undefined;
}

export interface Plan {
  weekly_plan?: PlanDay[];
  daily_meals?: DailyMeals;
  nutrition_targets?: { calories?: number; protein?: number; [k: string]: unknown };
  nutrition_totals?: Record<string, unknown>;
  rationale?: string;
  weight_guidance?: string;
  progression_guide?: string;
  translation_warning?: string;
  [k: string]: unknown;
}
```

`frontend/src/api/client.ts`：

```ts
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `请求失败（${status}）`);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const resp = await fetch(path, { ...init, headers, credentials: 'include' });
  if (!resp.ok) {
    let detail: unknown = null;
    try {
      detail = await resp.json();
    } catch {
      detail = await resp.text().catch(() => null);
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
```

`frontend/src/api/auth.ts`：

```ts
import { apiFetch } from './client';

export interface AuthResult {
  token: string;
  username: string;
}

export function register(username: string, password: string) {
  return apiFetch<AuthResult>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string) {
  return apiFetch<AuthResult>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return apiFetch<{ username: string; status: string }>('/api/auth/logout', {
    method: 'POST',
  });
}

export function me() {
  return apiFetch<{ username: string }>('/api/me');
}
```

`frontend/src/api/profile.ts`：

```ts
import type { Profile } from '../types/profile';
import { apiFetch } from './client';

export interface ProfileResponse {
  username: string;
  profile: Profile;
}

export interface ProfileSaveResponse {
  username: string;
  status: string;
  indexing_warning?: string | null;
}

export function getProfile() {
  return apiFetch<ProfileResponse>('/api/profile');
}

export function saveProfile(profile: Profile) {
  return apiFetch<ProfileSaveResponse>('/api/profile', {
    method: 'PUT',
    body: JSON.stringify(profile),
  });
}
```

`frontend/src/api/plan.ts`：

```ts
import type { Profile } from '../types/profile';
import type { Plan } from '../types/plan';
import { apiFetch } from './client';

export interface GenerateResponse {
  username: string;
  plan: Plan;
  validation: { valid: boolean; violations?: string[] } | null;
  errors: string[];
}

export function generatePlan(profile: Profile | null) {
  return apiFetch<GenerateResponse>('/api/plans/generate', {
    method: 'POST',
    body: JSON.stringify({ profile, persist: true }),
  });
}
```

`frontend/src/api/chat.ts`：

```ts
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { Plan } from '../types/plan';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ToolResult {
  original_exercise: string;
  alternatives: { name: string; [k: string]: unknown }[];
  total: number;
  source: string;
  note?: string;
}

export interface ChatDone {
  tool_results: ToolResult[];
}

export interface ChatStreamHandlers {
  onToken: (text: string) => void;
  onDone: (done: ChatDone) => void;
  onError: (message: string) => void;
}

export function streamChat(
  plan: Plan,
  messages: ChatMessage[],
  message: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
) {
  return fetchEventSource('/api/plans/chat', {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan, messages, message }),
    async onopen(response) {
      if (!response.ok) {
        let detail = '';
        try {
          detail = JSON.stringify(await response.json());
        } catch {
          /* ignore */
        }
        handlers.onError(detail || `请求失败（${response.status}）`);
        throw new Error(detail || 'chat request failed');
      }
    },
    onmessage(msg) {
      if (msg.event === 'token') {
        // 后端 token 事件 data 为 JSON 编码的字符串（见 _sse_event），需反解
        try {
          handlers.onToken(JSON.parse(msg.data));
        } catch {
          handlers.onToken(msg.data);
        }
      } else if (msg.event === 'done') {
        let done: ChatDone = { tool_results: [] };
        try {
          done = JSON.parse(msg.data);
        } catch {
          /* ignore */
        }
        handlers.onDone(done);
      } else if (msg.event === 'error') {
        let message = msg.data;
        try {
          message = JSON.parse(msg.data).message ?? msg.data;
        } catch {
          /* ignore */
        }
        handlers.onError(message);
      }
    },
    onerror(err) {
      handlers.onError(err instanceof Error ? err.message : String(err));
      throw err; // 抛出让 fetch-event-source 停止重连
    },
  });
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npm test && npm run build`
Expected: client.test 通过，`tsc` 无错。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: 前端类型定义与 API 客户端

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 7: AuthProvider + ProtectedRoute

**Files:**
- Create: `frontend/src/auth/useAuth.ts`, `frontend/src/auth/AuthProvider.tsx`, `frontend/src/components/ProtectedRoute.tsx`
- Test: `frontend/src/auth/AuthProvider.test.tsx`

**Interfaces:**
- Consumes: `api/auth.me`、`api/auth.logout`。
- Produces: `AuthProvider({children})`；`useAuth() -> { user: string|null, loading: boolean, logout(): Promise<void>, setUser(u) }`。

- [ ] **Step 1: 写失败测试**

`frontend/src/auth/AuthProvider.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthProvider';

vi.mock('../api/auth', () => ({
  me: vi.fn(),
  logout: vi.fn().mockResolvedValue({ username: 'x', status: 'logged_out' }),
}));

import { me } from '../api/auth';

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <div>loading</div>;
  return <div>user: {user ?? 'none'}</div>;
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.mocked(me).mockReset();
  });

  it('sets user when /api/me succeeds', async () => {
    vi.mocked(me).mockResolvedValue({ username: 'alice' });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByText('loading')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('user: alice')).toBeInTheDocument());
  });

  it('leaves user null when /api/me rejects', async () => {
    vi.mocked(me).mockRejectedValue(new Error('401'));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText('user: none')).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 失败——`./AuthProvider` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/auth/useAuth.ts`：

```ts
import { createContext, useContext } from 'react';

export interface AuthContextValue {
  user: string | null;
  loading: boolean;
  logout: () => Promise<void>;
  setUser: (username: string | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用');
  return ctx;
}
```

`frontend/src/auth/AuthProvider.tsx`：

```tsx
import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { me, logout as apiLogout } from '../api/auth';
import { AuthContext, AuthContextValue } from './useAuth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    me()
      .then((r) => setUser(r.username))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      /* 服务端失败也清本地会话 */
    }
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, logout, setUser }),
    [user, loading, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export { useAuth };
```

`frontend/src/components/ProtectedRoute.tsx`：

```tsx
import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../auth/useAuth';

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npm test && npm run build`
Expected: 测试通过，类型检查通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/auth frontend/src/components/ProtectedRoute.tsx
git commit -m "feat: AuthProvider + 受保护路由

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 8: 登录 / 注册页

**Files:**
- Create: `frontend/src/pages/Login.tsx`, `frontend/src/pages/Register.tsx`
- Modify: `frontend/src/App.tsx`（接入路由）
- Test: `frontend/src/pages/Login.test.tsx`

**Interfaces:**
- Consumes: `api/auth.login / register`、`useAuth().setUser`。
- Produces: `/login`、`/register` 页面。

- [ ] **Step 1: 写失败测试**

`frontend/src/pages/Login.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthProvider';
import { ApiError } from '../api/client';
import Login from './Login';

vi.mock('../api/auth', () => ({
  me: vi.fn().mockRejectedValue(new Error('401')),
  logout: vi.fn(),
  login: vi.fn(),
}));

import { login } from '../api/auth';

describe('Login', () => {
  beforeEach(() => vi.mocked(login).mockReset());

  it('submits and shows error on wrong password', async () => {
    vi.mocked(login).mockRejectedValue(
      new ApiError(401, { detail: '用户名或密码错误' }),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText('用户名'), 'alice');
    await userEvent.type(screen.getByLabelText('密码'), 'wrongpass');
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    await waitFor(() => expect(login).toHaveBeenCalledWith('alice', 'wrongpass'));
    expect(await screen.findByText('用户名或密码错误')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 失败——`./Login` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/pages/Login.tsx`：

```tsx
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { login } from '../api/auth';
import { isUnauthorized } from '../api/client';
import { useAuth } from '../auth/useAuth';

export default function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    try {
      const r = await login(values.username, values.password);
      setUser(r.username);
      navigate('/plan', { replace: true });
    } catch (err) {
      if (isUnauthorized(err)) message.error('用户名或密码错误');
      else message.error(err instanceof Error ? err.message : '登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: '80px auto' }}>
      <Card title="登录 健身营养 Agent">
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>
            登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16 }}>
          没有账号？<Link to="/register">注册新账号</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
```

`frontend/src/pages/Register.tsx`：

```tsx
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { register } from '../api/auth';
import { useAuth } from '../auth/useAuth';

export default function Register() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: {
    username: string;
    password: string;
    confirm: string;
  }) => {
    if (values.password !== values.confirm) {
      message.error('两次输入的密码不一致');
      return;
    }
    setSubmitting(true);
    try {
      const r = await register(values.username, values.password);
      setUser(r.username);
      navigate('/plan', { replace: true });
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注册失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: '80px auto' }}>
      <Card title="注册新账号">
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { pattern: /^[A-Za-z0-9_]{3,20}$/, message: '3-20 位字母/数字/下划线' },
            ]}
          >
            <Input autoFocus />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少 6 位' },
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认密码"
            rules={[{ required: true, message: '请再次输入密码' }]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>
            注册并登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16 }}>
          已有账号？<Link to="/login">去登录</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
```

`frontend/src/App.tsx` 替换为：

```tsx
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Register from './pages/Register';
import Plan from './pages/Plan';
import Profile from './pages/Profile';
import Chat from './pages/Chat';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route path="/plan" element={<ProtectedRoute><Plan /></ProtectedRoute>} />
        <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/plan" replace />} />
      </Routes>
    </AuthProvider>
  );
}
```

- [ ] **Step 4: 运行确认通过（暂以占位页满足类型检查）**

本步 `App.tsx` 引用了 `Plan/Profile/Chat` 三页，尚未创建。先创建三个最小占位页使 `tsc` 通过：

`frontend/src/pages/Profile.tsx` / `Plan.tsx` / `Chat.tsx` 各自内容（后续任务覆盖为完整实现）：

```tsx
export default function Profile() {
  return <div>Profile</div>;
}
```

（`Plan.tsx`、`Chat.tsx` 同理，函数名与默认导出对应文件名。）

Run: `cd frontend && npm test && npm run build`
Expected: Login 测试通过；`tsc` 通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: 登录/注册页 + 路由接入

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 9: 画像页 + 表单校验

**Files:**
- Modify: `frontend/src/pages/Profile.tsx`（替换占位）
- Create: `frontend/src/components/ProfileForm.tsx`
- Test: `frontend/src/components/ProfileForm.test.tsx`

**Interfaces:**
- Consumes: `api/profile.getProfile / saveProfile`、`types/profile.Profile`。
- Produces: `<ProfileForm initial onSave onSaved saving saveWarning />`。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/ProfileForm.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProfileForm from './ProfileForm';

describe('ProfileForm 校验', () => {
  it('缺装备时阻止提交并提示', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileForm onSave={onSave} onSaved={() => {}} saving={false} />);

    await userEvent.click(screen.getByRole('button', { name: '保存画像' }));
    await waitFor(() => expect(onSave).not.toHaveBeenCalled());
    expect(await screen.findByText('请至少选择一种器械')).toBeInTheDocument();
  });

  it('年龄越界提示', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileForm onSave={onSave} onSaved={() => {}} saving={false} />);
    await userEvent.type(screen.getByLabelText('年龄'), '200');
    await userEvent.click(screen.getByRole('button', { name: '保存画像' }));
    expect(await screen.findByText('年龄需在 14–80 之间')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 失败——`./ProfileForm` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/components/ProfileForm.tsx`：

```tsx
import { useState } from 'react';
import { Alert, Button, Form, InputNumber, Radio, Select, message } from 'antd';
import type { Goal, Profile } from '../types/profile';

const EQUIPMENT_OPTIONS = [
  { value: 'gym', label: '健身房（全部器械）' },
  { value: 'dumbbell', label: '哑铃' },
  { value: 'barbell', label: '杠铃' },
  { value: 'kettlebell', label: '壶铃' },
  { value: 'band', label: '弹力带' },
  { value: 'bodyweight', label: '自重（无器械）' },
  { value: 'bench', label: '卧推凳' },
  { value: 'cable', label: '绳索器械' },
  { value: 'machine', label: '固定器械' },
  { value: 'pull-up bar', label: '引体杆' },
];

const GOAL_OPTIONS: { value: Goal; label: string }[] = [
  { value: 'fat_loss', label: '减脂' },
  { value: 'muscle_gain', label: '增肌' },
  { value: 'recomp', label: '塑形（减脂+增肌）' },
  { value: 'general_fitness', label: '综合体能/健康' },
];

interface Props {
  initial?: Profile;
  onSave: (profile: Profile) => Promise<unknown>;
  onSaved: () => void;
  saving: boolean;
  saveWarning?: string | null;
}

const positiveRule = (label: string) => ({
  validator: (_: unknown, value: number | null) =>
    value === null || value === undefined || value > 0
      ? Promise.resolve()
      : Promise.reject(new Error(`${label}需大于 0`)),
});

export default function ProfileForm({ initial, onSave, onSaved, saving, saveWarning }: Props) {
  const [error, setError] = useState<string | null>(null);

  const finish = async (values: Profile) => {
    setError(null);
    try {
      await onSave(values);
      message.success('画像已保存 ✅');
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  };

  return (
    <Form<Profile> layout="vertical" initialValues={initial} onFinish={finish} requiredMark>
      <Form.Item name="sex" label="性别" rules={[{ required: true, message: '请选择性别' }]}>
        <Radio.Group options={[{ value: 'male', label: '男' }, { value: 'female', label: '女' }]} />
      </Form.Item>

      <Form.Item
        name="age"
        label="年龄"
        rules={[
          { required: true, message: '请输入年龄' },
          { type: 'number', min: 14, max: 80, message: '年龄需在 14–80 之间' },
        ]}
      >
        <InputNumber min={14} max={80} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item
        name="height_cm"
        label="身高（cm）"
        rules={[{ required: true, message: '请输入身高' }, positiveRule('身高')]}
      >
        <InputNumber min={1} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item
        name="weight_kg"
        label="体重（kg）"
        rules={[{ required: true, message: '请输入体重' }, positiveRule('体重')]}
      >
        <InputNumber min={1} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item name="goal" label="目标" rules={[{ required: true, message: '请选择目标' }]}>
        <Select options={GOAL_OPTIONS} />
      </Form.Item>

      <Form.Item
        name="days_per_week"
        label="每周训练天数"
        rules={[
          { required: true, message: '请输入训练天数' },
          { type: 'number', min: 1, max: 7, message: '训练天数需在 1–7 之间' },
        ]}
      >
        <InputNumber min={1} max={7} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item
        name="equipment"
        label="可用器械"
        rules={[{ required: true, message: '请至少选择一种器械' }]}
      >
        <Select mode="multiple" options={EQUIPMENT_OPTIONS} placeholder="可多选" />
      </Form.Item>

      <Form.Item name="medical_conditions" label="伤病情况（可选）">
        <Select mode="tags" placeholder="如：膝盖、肩（回车添加）" open={false} />
      </Form.Item>

      <Form.Item name="dietary_preferences" label="饮食偏好（可选）">
        <Select mode="tags" placeholder="如：素食、低碳（回车添加）" open={false} />
      </Form.Item>

      <Form.Item name="allergies" label="过敏（可选）">
        <Select mode="tags" placeholder="如：花生、乳糖（回车添加）" open={false} />
      </Form.Item>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      {saveWarning && <Alert type="warning" message={saveWarning} style={{ marginBottom: 16 }} />}

      <Button type="primary" htmlType="submit" loading={saving} block>
        保存画像
      </Button>
    </Form>
  );
}
```

`frontend/src/pages/Profile.tsx` 替换为：

```tsx
import { useNavigate } from 'react-router-dom';
import { Alert, Spin, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile, saveProfile } from '../api/profile';
import { ApiError } from '../api/client';
import ProfileForm from '../components/ProfileForm';
import type { Profile } from '../types/profile';

export default function Profile() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['profile'], queryFn: getProfile });

  const save = useMutation({
    mutationFn: (p: Profile) => saveProfile(p),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profile'] }),
  });

  const missing = isError && error instanceof ApiError && error.status === 404;

  if (isLoading) return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  if (isError && !missing) {
    return <Alert type="error" message="读取画像失败，请稍后重试" style={{ margin: 40 }} />;
  }

  return (
    <div style={{ maxWidth: 720, margin: '40px auto' }}>
      <Typography.Title level={3}>📋 用户画像</Typography.Title>
      {missing && <Alert type="info" message="尚未填写画像，请填写后保存" style={{ marginBottom: 16 }} />}
      <ProfileForm
        initial={data?.profile}
        onSaved={() => navigate('/plan')}
        onSave={(p) => save.mutateAsync(p)}
        saving={save.isPending}
        saveWarning={save.data?.indexing_warning ?? null}
      />
    </div>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npm test && npm run build`
Expected: ProfileForm 测试通过，`tsc` 通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: 画像页 + AntD 表单校验

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 10: 计划页 + 训练/餐单表格

**Files:**
- Modify: `frontend/src/pages/Plan.tsx`（替换占位）
- Create: `frontend/src/components/PlanTable.tsx`, `frontend/src/components/MealTable.tsx`
- Test: `frontend/src/components/PlanTable.test.tsx`

**Interfaces:**
- Consumes: `api/profile.getProfile`、`api/plan.generatePlan`、`types/plan.Plan`。
- Produces: `<PlanTable plan />`、`<MealTable plan />`；生成成功后 `queryClient.setQueryData(['plan'], plan)`。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/PlanTable.test.tsx`：

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PlanTable from './PlanTable';
import type { Plan } from '../types/plan';

const plan: Plan = {
  weekly_plan: [
    {
      day: 1,
      focus: '胸+三头',
      exercises: [
        { name: 'Barbell Bench Press', name_zh: '杠铃卧推', sets: 4, reps: '8-10', rest: '90秒' },
      ],
    },
  ],
};

describe('PlanTable', () => {
  it('renders day and Chinese name with English original', () => {
    render(<PlanTable plan={plan} />);
    expect(screen.getByText(/第 1 天/)).toBeInTheDocument();
    expect(screen.getByText(/杠铃卧推（Barbell Bench Press）/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 失败——`./PlanTable` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/components/PlanTable.tsx`：

```tsx
import { Table, Typography } from 'antd';
import type { Exercise, Plan } from '../types/plan';

function renderName(_name: string | undefined, row: Exercise) {
  const zh = row.name_zh;
  const en = row.name ?? row.name_en;
  if (!en) return '—';
  return zh && zh !== en ? `${zh}（${en}）` : en;
}

const columns = [
  { title: '动作', dataIndex: 'name', key: 'name', render: renderName },
  { title: '组数', dataIndex: 'sets', key: 'sets', render: (v?: number) => v ?? '' },
  { title: '次数', dataIndex: 'reps', key: 'reps', render: (v?: string) => v ?? '' },
  { title: '休息', dataIndex: 'rest', key: 'rest', render: (v?: string) => v ?? '' },
  { title: '说明', dataIndex: 'note', key: 'note', render: (v?: string) => v ?? '' },
];

export default function PlanTable({ plan }: { plan: Plan }) {
  const days = plan.weekly_plan ?? [];
  if (days.length === 0) {
    return <Typography.Text type="secondary">暂无训练计划</Typography.Text>;
  }
  return (
    <>
      {days.map((day, i) => (
        <div key={i} style={{ marginBottom: 24 }}>
          <Typography.Title level={5}>
            第 {day.day ?? i + 1} 天 · {day.focus ?? ''}
          </Typography.Title>
          <Table
            rowKey={(r: Exercise) => r.name ?? ''}
            columns={columns}
            dataSource={day.exercises ?? []}
            pagination={false}
            size="small"
          />
        </div>
      ))}
    </>
  );
}
```

`frontend/src/components/MealTable.tsx`：

```tsx
import { Alert, Table, Typography } from 'antd';
import type { MealItem, Plan } from '../types/plan';

function renderFood(_food: string | undefined, r: MealItem) {
  const en = r.food;
  const zh = r.food_zh;
  if (!en) return '—';
  return zh && zh !== en ? `${zh}（${en}）` : en;
}

const mealColumns = [
  { title: '食物', dataIndex: 'food', key: 'food', render: renderFood },
  { title: '分量', dataIndex: 'amount', key: 'amount', render: (v?: string) => v ?? '' },
  { title: '说明', dataIndex: 'note', key: 'note', render: (v?: string) => v ?? '' },
];

const MEALS: { key: 'breakfast' | 'lunch' | 'dinner'; label: string }[] = [
  { key: 'breakfast', label: '早餐' },
  { key: 'lunch', label: '午餐' },
  { key: 'dinner', label: '晚餐' },
];

export default function MealTable({ plan }: { plan: Plan }) {
  const meals = plan.daily_meals ?? {};
  const targets = plan.nutrition_targets;
  return (
    <div>
      {targets && (
        <Alert
          type="info"
          style={{ marginBottom: 12 }}
          message={`目标热量约 ${targets.calories ?? '—'} kcal · 蛋白质约 ${targets.protein ?? '—'} g`}
        />
      )}
      {MEALS.map((m) => (
        <div key={m.key} style={{ marginBottom: 16 }}>
          <Typography.Title level={5}>{m.label}</Typography.Title>
          <Table
            rowKey={(r: MealItem, i) => `${m.key}-${i}`}
            columns={mealColumns}
            dataSource={meals[m.key] ?? []}
            pagination={false}
            size="small"
          />
        </div>
      ))}
    </div>
  );
}
```

`frontend/src/pages/Plan.tsx` 替换为：

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Spin, Tabs, Typography, message } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile } from '../api/profile';
import { generatePlan } from '../api/plan';
import { ApiError } from '../api/client';
import PlanTable from '../components/PlanTable';
import MealTable from '../components/MealTable';
import type { Plan as PlanType } from '../types/plan';

export default function Plan() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState<PlanType | null>(null);
  const [validation, setValidation] = useState<{ valid: boolean; violations?: string[] } | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ['profile'], queryFn: getProfile, retry: false });

  const generate = async () => {
    setGenerating(true);
    setErrors([]);
    try {
      const r = await generatePlan(data?.profile ?? null);
      setPlan(r.plan);
      setValidation(r.validation);
      setErrors(r.errors);
      queryClient.setQueryData(['plan'], r.plan);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        message.error('请先到「用户画像」填写并保存画像');
      } else if (err instanceof ApiError && err.status === 422) {
        message.error('画像信息不全，请补全后重试');
      } else {
        message.error(err instanceof Error ? err.message : '生成失败，请确认 MCP 桥接已启动（make mcp-up）');
      }
    } finally {
      setGenerating(false);
    }
  };

  if (isLoading) return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  if (!data) {
    return (
      <Alert
        type="info"
        style={{ margin: 40 }}
        message="请先填写画像"
        description="生成计划需要先保存用户画像。"
        action={<Button onClick={() => navigate('/profile')}>去填写画像</Button>}
      />
    );
  }

  return (
    <div style={{ maxWidth: 1000, margin: '40px auto' }}>
      <Typography.Title level={3}>📅 生成计划</Typography.Title>
      <Button type="primary" size="large" loading={generating} onClick={generate}>
        🚀 生成一周训练 + 一日三餐
      </Button>
      {generating && (
        <Alert type="info" message="正在检索动作/食物并由模型编排，约需 1–3 分钟…" style={{ marginTop: 16 }} />
      )}

      {errors.length > 0 && (
        <Alert type="warning" message={`过程中有 ${errors.length} 条提示`} description={errors.join('；')} style={{ marginTop: 16 }} />
      )}
      {plan && validation && !validation.valid && (
        <Alert type="warning" message={'计划未通过校验：' + (validation.violations ?? []).join('；')} style={{ marginTop: 16 }} />
      )}
      {plan?.translation_warning && <Alert type="warning" message={plan.translation_warning} style={{ marginTop: 16 }} />}

      {plan && (
        <>
          <Tabs
            style={{ marginTop: 16 }}
            items={[
              {
                key: 'weekly',
                label: '🏋️ 一周训练计划',
                children: (
                  <>
                    {plan.weight_guidance && <Alert type="info" message={plan.weight_guidance} style={{ marginBottom: 12 }} />}
                    {plan.progression_guide && <Alert type="info" message={plan.progression_guide} style={{ marginBottom: 12 }} />}
                    <PlanTable plan={plan} />
                  </>
                ),
              },
              { key: 'meals', label: '🍱 一日三餐', children: <MealTable plan={plan} /> },
            ]}
          />
          <Typography.Title level={5} style={{ marginTop: 24 }}>💡 为什么这样安排</Typography.Title>
          <Typography.Paragraph>{plan.rationale ?? ''}</Typography.Paragraph>
          <Button style={{ marginTop: 8 }} onClick={() => navigate('/chat')}>💬 对话调整计划</Button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npm test && npm run build`
Expected: PlanTable 测试通过，`tsc` 通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: 计划页 + 训练/餐单表格

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 11: 对话调整页 + SSE 消费

**Files:**
- Create: `frontend/src/hooks/useChatStream.ts`
- Modify: `frontend/src/pages/Chat.tsx`（替换占位）
- Test: `frontend/src/hooks/useChatStream.test.ts`

**Interfaces:**
- Consumes: `api/chat.streamChat`、`api/chat.ToolResult`、`types/plan.Plan`。
- Produces: `useChatStream(plan) -> { messages, streaming, pending, error, send(text) }`。

- [ ] **Step 1: 写失败测试**

`frontend/src/hooks/useChatStream.test.ts`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatStream } from './useChatStream';
import { streamChat } from '../api/chat';

vi.mock('../api/chat', () => ({
  streamChat: vi.fn(),
}));

const PLAN = { weekly_plan: [] };

function captureHandlers(impl: (h: any) => void) {
  vi.mocked(streamChat).mockImplementation((_plan, _msgs, _msg, handlers) => {
    impl(handlers);
    return Promise.resolve();
  });
}

describe('useChatStream', () => {
  beforeEach(() => vi.mocked(streamChat).mockReset());

  it('accumulates tokens into last assistant message', async () => {
    captureHandlers((h) => {
      h.onToken('你');
      h.onToken('好');
      h.onDone({ tool_results: [] });
    });
    const { result } = renderHook(() => useChatStream(PLAN));
    await act(async () => {
      await result.current.send('你好');
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('你好');
    expect(result.current.streaming).toBe(false);
  });

  it('sets pending from last tool result with alternatives', async () => {
    captureHandlers((h) => {
      h.onDone({
        tool_results: [
          {
            original_exercise: '卧推',
            alternatives: [{ name: 'Dumbbell Press' }],
            total: 1,
            source: 'mcp',
          },
        ],
      });
    });
    const { result } = renderHook(() => useChatStream(PLAN));
    await act(async () => {
      await result.current.send('换动作');
    });
    expect(result.current.pending?.original_exercise).toBe('卧推');
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 失败——`./useChatStream` 不存在。

- [ ] **Step 3: 实现**

`frontend/src/hooks/useChatStream.ts`：

```ts
import { useCallback, useRef, useState } from 'react';
import { streamChat, ChatDone, ChatMessage, ToolResult } from '../api/chat';
import type { Plan } from '../types/plan';

export function useChatStream(plan: Plan) {
  const planRef = useRef(plan);
  planRef.current = plan;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [pending, setPending] = useState<ToolResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(
    async (text: string) => {
      const history = [...messages];
      setMessages((m) => [...m, { role: 'user', content: text }]);
      setStreaming(true);
      setError(null);
      setPending(null);

      let acc = '';
      setMessages((m) => [...m, { role: 'assistant', content: '' }]);

      try {
        await streamChat(planRef.current, history, text, {
          onToken: (t) => {
            acc += t;
            setMessages((m) => {
              const next = [...m];
              next[next.length - 1] = { role: 'assistant', content: acc };
              return next;
            });
          },
          onDone: (done: ChatDone) => {
            const latest = [...done.tool_results].reverse().find((r) => r.alternatives?.length);
            if (latest) setPending(latest);
          },
          onError: (msg) => setError(msg),
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setStreaming(false);
      }
    },
    [messages],
  );

  return { messages, streaming, pending, error, send };
}
```

`frontend/src/pages/Chat.tsx` 替换为：

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Input, List, Select, Space, Spin, Typography, message } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '../hooks/useChatStream';
import type { Plan } from '../types/plan';

export default function Chat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(() => qc.getQueryData<Plan>(['plan']) ?? null);
  const [input, setInput] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const { messages, streaming, pending, error, send } = useChatStream(plan ?? {});

  if (!plan) {
    return (
      <Alert
        type="info"
        style={{ margin: 40 }}
        message="请先生成计划"
        description="对话调整需要基于一份已生成的计划。"
        action={<Button onClick={() => navigate('/plan')}>去生成</Button>}
      />
    );
  }

  const applySubstitution = (newName: string) => {
    if (!pending) return;
    const target = pending.original_exercise.trim().toLowerCase();
    const next: Plan = JSON.parse(JSON.stringify(plan));
    let changed = false;
    for (const day of next.weekly_plan ?? []) {
      for (const ex of day.exercises ?? []) {
        if (typeof ex.name === 'string' && ex.name.trim().toLowerCase() === target) {
          ex.name = newName;
          changed = true;
        }
      }
    }
    if (changed) {
      setPlan(next);
      qc.setQueryData(['plan'], next);
      message.success(`已替换为 ${newName}`);
    } else {
      message.warning('当前计划中未找到该原动作');
    }
    setChosen(null);
  };

  return (
    <div style={{ maxWidth: 800, margin: '40px auto' }}>
      <Typography.Title level={3}>💬 对话调整</Typography.Title>

      <List
        dataSource={messages}
        renderItem={(m) => (
          <List.Item style={{ justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div
              style={{
                background: m.role === 'user' ? '#e6f4ff' : '#f5f5f5',
                padding: '8px 12px',
                borderRadius: 8,
                maxWidth: '80%',
                whiteSpace: 'pre-wrap',
              }}
            >
              {m.content || (streaming ? <Spin size="small" /> : '')}
            </div>
          </List.Item>
        )}
      />

      {pending?.alternatives?.length ? (
        <Space style={{ marginTop: 12 }}>
          <Select
            style={{ width: 240 }}
            placeholder="选择替代动作"
            value={chosen ?? undefined}
            onChange={setChosen}
            options={pending.alternatives.map((a) => ({ value: a.name, label: a.name }))}
          />
          <Button type="primary" disabled={!chosen} onClick={() => chosen && applySubstitution(chosen)}>
            ✅ 应用到当前计划
          </Button>
        </Space>
      ) : null}

      {error && <Alert type="error" message={error} style={{ marginTop: 12 }} />}

      <Space.Compact style={{ width: '100%', marginTop: 16 }}>
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => {
            if (input.trim() && !streaming) {
              send(input.trim());
              setInput('');
            }
          }}
          placeholder="如：把卧推换成哑铃能做的"
          disabled={streaming}
        />
        <Button
          type="primary"
          disabled={!input.trim() || streaming}
          onClick={() => {
            send(input.trim());
            setInput('');
          }}
        >
          发送
        </Button>
      </Space.Compact>
    </div>
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npm test && npm run build`
Expected: useChatStream 测试通过，`tsc` 通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: 对话调整页 + SSE 流式消费

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 12: 构建 + Makefile + 文档 + 端到端冒烟

**Files:**
- Modify: `Makefile`（`.PHONY` 行 + 新增两个 target）
- Modify: `README.md`、`CLAUDE.md`（第 3 节结构、第 6 节命令）

**Interfaces:**
- Consumes: 无新接口。
- Produces: `make frontend-dev` / `make frontend-build`；文档与结构同步。

- [ ] **Step 1: Makefile**

`.PHONY` 行改为（追加两个词）：

```make
.PHONY: install dev api embedding embed-up embed-down embed-status \
	mcp-up mcp-down mcp-status test lint clean frontend-dev frontend-build
```

文件末尾追加（**注意：recipe 行必须用 Tab 缩进**，不能用空格）：

```make
# 前端（React + Vite）：dev server（5173，/api 代理到 8000）
frontend-dev:
	npm --prefix frontend run dev

# 前端生产构建：产出 frontend/dist（由 FastAPI 静态托管）
frontend-build:
	npm --prefix frontend install
	npm --prefix frontend run build
```

- [ ] **Step 2: 构建产物验证**

Run: `make frontend-build`
Expected: `tsc` + `vite build` 成功，`frontend/dist/index.html` 与 `frontend/dist/assets/` 存在。

- [ ] **Step 3: 后端托管冒烟**

Run（后台起后端后手动验证）:
```bash
uv run uvicorn app.main:app --port 8000   # 终端 A
# 终端 B：
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ | head -c 200          # 应返回 index.html
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/profile   # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/me     # 401（鉴权）
```
Expected: `/health` 200；`/` 返回 SPA HTML；`/profile` 200（index.html 兜底）；`/api/me` 401。

- [ ] **Step 4: 全量回归**

Run: `uv run pytest tests -v && make lint && cd frontend && npm test`
Expected: 后端全绿 + ruff 全绿 + 前端 Vitest 全绿。

- [ ] **Step 5: 文档同步**

`CLAUDE.md` 第 3 节结构树中，`ui/` 之后新增：

```
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
```

`CLAUDE.md` 第 6 节常用命令增补：

```bash
# 前端开发 / 构建（React + Vite，替代 Streamlit）
make frontend-dev
make frontend-build
```

`README.md`：在"启动"段落补充一行说明"前端已迁移到 React（`make frontend-dev` 开发、`make frontend-build` 构建由 FastAPI 托管）"，并注明 `make dev`（Streamlit）暂保留。

- [ ] **Step 6: Commit**

```bash
git add Makefile README.md CLAUDE.md
git commit -m "docs: 前端构建命令与项目结构文档

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review 记录（已内联修正）

- **Spec 覆盖**：cookie 鉴权(T1)、聊天 SSE(T3)、画像规整+索引(T2)、SPA 托管(T4)、三页前端(T8/T9/T10/T11)、路由/状态/校验/构建部署(T5/T7/T12) 均有对应任务；计划历史/X-API-Key/Docker 明确排除（spec 不含）。
- **占位扫描**：无 TBD/TODO；每个代码步骤给出完整可运行代码。
- **类型一致性**：`useAuth()` 在 `useAuth.ts` 定义、`AuthProvider.tsx` re-export；`apiFetch`/`streamChat`/`build_chat_system_prompt`/`index_profile_if_available` 命名前后一致。
- **Review Focus**：5 条各落到 T1/T3/T3/T3/T4 的测试中。

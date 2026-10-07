"""FastAPI 后端：多账号认证 + 画像存取 + Agent 计划生成。

启动：
    make api  （uv run uvicorn app.main:app --reload）

鉴权：
    注册/登录成功后返回会话 token；受保护接口需带
        Authorization: Bearer <token>
    服务端按 token 反查当前账号，所有画像/计划都以该账号为隔离边界。

端点：
    GET  /health                健康检查（无需鉴权）
    POST /api/auth/register     注册并返回 token
    POST /api/auth/login        登录并返回 token
    POST /api/auth/logout       登出（吊销 token）
    GET  /api/me                当前账号
    PUT  /api/profile           保存/更新当前账号画像
    GET  /api/profile           读取当前账号画像
    POST /api/plans/generate    运行 Agent 生成计划
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.chat_adjust import build_chat_system_prompt, stream_with_tools
from app.agent.llm import get_llm
from app.agent.safety import pre_check_message
from app.db.models import Profile
from app.db.sqlite_client import (
    append_chat_message,
    clear_chat_pending,
    load_chat_history,
    load_chat_pending,
    load_latest_plan,
    load_profile,
    save_chat_pending,
    save_plan,
    save_profile,
)
from app.db.users import (
    UserExistsError,
    create_session,
    create_user,
    get_session_user,
    revoke_session,
    verify_user,
)

app = FastAPI(
    title="健身营养 Agent API",
    version="0.2.0",
    description="多账号：注册登录后，按账号生成一周训练计划与一日三餐。",
)


# ============================================================
# 鉴权依赖
# ============================================================

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


# ============================================================
# 请求模型
# ============================================================

class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=128)


class PlanGenerateRequest(BaseModel):
    """生成计划请求。

    profile 可省略：此时从数据库读取当前账号已存画像。
    """

    profile: Profile | None = None
    persist: bool = Field(
        default=True, description="生成成功后是否把计划追加存入 generated_plans"
    )


class ChatRequest(BaseModel):
    """对话调整请求：plan 随请求带入（替换动作后 DB 里仍是原始计划）。"""

    plan: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, str]] = Field(default_factory=list)
    message: str = Field(min_length=1)


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_agent(user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    """执行 LangGraph 工作流（测试中可 monkeypatch 此函数）。"""
    from app.agent.graph import agent_graph

    return await agent_graph.ainvoke(
        {"user_id": user_id, "profile": profile},
        # Checkpointer 要求按 thread_id 隔离会话记忆；同一账号复用同一条会话
        config={"configurable": {"thread_id": user_id}},
    )


def _issue_token(username: str) -> dict[str, str]:
    return {"token": create_session(username), "username": username}


# ============================================================
# 认证
# ============================================================

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    # 用户不存在与密码错统一返回 401，避免账号枚举
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


@app.get("/api/me")
async def me(user: str = Depends(current_user)) -> dict[str, str]:
    return {"username": user}


# ============================================================
# 画像（按当前账号）
# ============================================================

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


@app.get("/api/profile")
async def get_my_profile(user: str = Depends(current_user)) -> dict[str, Any]:
    profile = load_profile(user)
    if profile is None:
        raise HTTPException(status_code=404, detail="尚未填写画像")
    return {"username": user, "profile": profile.model_dump()}


# ============================================================
# 计划生成（按当前账号）
# ============================================================

@app.post("/api/plans/generate")
async def generate_plan_endpoint(
    request: PlanGenerateRequest,
    user: str = Depends(current_user),
) -> dict[str, Any]:
    if request.profile is not None:
        profile_data = request.profile.model_dump()
    else:
        stored = load_profile(user)
        if stored is None:
            raise HTTPException(
                status_code=400,
                detail="未提供 profile，且当前账号没有已存画像",
            )
        profile_data = stored.model_dump()

    try:
        result = await run_agent(user, profile_data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent 执行失败：{exc}") from exc

    if result.get("missing_fields"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "画像信息不全，请补全后重试",
                "missing_fields": result["missing_fields"],
            },
        )

    plan = result.get("plan") or {}
    if not plan:
        raise HTTPException(
            status_code=502,
            detail={"message": "本次未生成计划", "errors": result.get("errors", [])},
        )

    # 重试耗尽仍不合法：不把含编造内容的计划返回给用户
    validation = result.get("validation") or {}
    if not validation.get("valid") and validation.get("user_message"):
        raise HTTPException(status_code=422, detail={"message": validation["user_message"]})

    if request.persist:
        try:
            save_plan(user, plan, "weekly_plan")
        except Exception:
            # 计划已生成，持久化失败不应让整个请求失败
            pass

    return {
        "username": user,
        "plan": plan,
        "validation": result.get("validation"),
        "errors": result.get("errors", []),
    }


@app.get("/api/plans/latest")
def get_latest_plan(user: str = Depends(current_user)) -> dict[str, Any]:
    """恢复该用户最近一次持久化的计划；从未生成过则 404。"""
    record = load_latest_plan(user)
    if record is None:
        raise HTTPException(status_code=404, detail="还没有已保存的计划")
    plan, created_at = record
    return {"plan": plan, "created_at": created_at}


class PersistPlanRequest(BaseModel):
    """对话调整后把更新过的计划持久化。"""

    plan: dict[str, Any] = Field(default_factory=dict)


@app.put("/api/plans/latest")
def persist_latest_plan(
    request: PersistPlanRequest, user: str = Depends(current_user)
) -> dict[str, Any]:
    """保存对话调整后的计划，使其成为该账号的最近计划（表格/刷新后均可恢复）。"""
    if not request.plan:
        raise HTTPException(status_code=400, detail="plan 不能为空")
    save_plan(user, request.plan, "weekly_plan")
    record = load_latest_plan(user)
    plan, created_at = record if record is not None else (request.plan, None)
    return {"plan": plan, "created_at": created_at}


@app.get("/api/chat/history")
def chat_history(user: str = Depends(current_user)) -> dict[str, Any]:
    """读取当前账号持久化的对话调整历史与待确认建议（重登后恢复用）。"""
    return {
        "messages": load_chat_history(user),
        "pending": load_chat_pending(user),
    }


@app.post("/api/plans/chat")
def chat_stream(
    request: ChatRequest, user: str = Depends(current_user)
) -> StreamingResponse:
    profile = load_profile(user)
    if profile is None:
        raise HTTPException(status_code=400, detail="尚未填写画像，无法进行对话调整")
    profile_data = profile.model_dump()

    def make_accept_runner() -> Any:
        """用户同意后执行更换：校验候选出自待确认建议，再改表并持久化。"""

        def run(*, original_exercise: str, replacement_name: str) -> dict[str, Any]:
            pending = load_chat_pending(user)
            if pending is None:
                raise ValueError("当前没有待确认的更换建议")
            wanted = original_exercise.strip().lower()
            if wanted != str(pending.get("original_exercise", "")).strip().lower():
                raise ValueError("原动作与待确认建议不一致")
            names = [
                str(a.get("name", "")).strip().lower()
                for a in pending.get("alternatives", [])
                if isinstance(a, dict)
            ]
            if replacement_name.strip().lower() not in names:
                raise ValueError("只能更换为此前建议的候选动作")

            next_plan: dict[str, Any] = structured_clone(request.plan)
            changed = False
            for day in next_plan.get("weekly_plan", []):
                for ex in day.get("exercises", []):
                    if (
                        isinstance(ex.get("name"), str)
                        and ex["name"].strip().lower() == wanted
                    ):
                        ex["name"] = replacement_name
                        changed = True
            if not changed:
                raise ValueError("当前计划中未找到该原动作")

            save_plan(user, next_plan, "weekly_plan")
            clear_chat_pending(user)
            return {
                "accepted": True,
                "original_exercise": original_exercise,
                "replacement": replacement_name,
                "plan": next_plan,
            }

        return run

    def generate() -> Any:
        # 用户消息先落库；历史以服务端存储为准，不采信客户端上送的 messages
        append_chat_message(user, "user", request.message)

        guard = pre_check_message(request.message)
        if guard is not None:
            append_chat_message(user, "assistant", guard)
            yield _sse_event("token", guard)
            yield _sse_event(
                "done", {"tool_results": [], "applied_plan": None}
            )
            return
        try:
            pending = load_chat_pending(user)
            llm = get_llm(json_mode=False, temperature=0.4)
            messages: list[Any] = [
                SystemMessage(
                    content=build_chat_system_prompt(request.plan, pending)
                )
            ]
            for m in load_chat_history(user):
                cls = HumanMessage if m["role"] == "user" else AIMessage
                messages.append(cls(content=m["content"]))
            tool_results: list[dict[str, Any]] = []
            acc = ""
            for text in stream_with_tools(
                llm,
                messages,
                profile_data,
                tool_results=tool_results,
                accept_runner=make_accept_runner(),
            ):
                acc += text
                yield _sse_event("token", text)

            if acc.strip():
                append_chat_message(user, "assistant", acc)

            # 新建议覆盖待确认；已接受的更换把更新后的计划回传前端
            proposal = next(
                (
                    r
                    for r in reversed(tool_results)
                    if r.get("alternatives")
                    and not r.get("accepted")
                ),
                None,
            )
            if proposal is not None:
                save_chat_pending(user, proposal)

            accepted = next(
                (r for r in tool_results if r.get("accepted")), None
            )
            yield _sse_event(
                "done",
                {
                    "tool_results": tool_results,
                    "applied_plan": accepted["plan"] if accepted else None,
                },
            )
        except Exception as exc:
            yield _sse_event("error", {"message": f"调用模型失败：{exc}"})

    return StreamingResponse(generate(), media_type="text/event-stream")


def structured_clone(value: dict[str, Any]) -> dict[str, Any]:
    """深拷贝 dict（JSON 可序列化的计划数据）。"""
    return json.loads(json.dumps(value, ensure_ascii=False))


# ============================================================
# SPA 静态托管（前端 React 构建产物；dist 未构建时 /api 仍可用）
# ============================================================

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

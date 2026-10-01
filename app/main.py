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

from typing import Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.db.models import Profile
from app.db.sqlite_client import load_profile, save_plan, save_profile
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

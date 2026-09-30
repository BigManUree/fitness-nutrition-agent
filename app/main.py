"""FastAPI 后端：封装用户画像存取与 Agent 计划生成。

启动：
    make api  （uv run uvicorn app.main:app --reload）

端点：
    GET  /health                        健康检查
    PUT  /api/profiles/{user_id}        保存/更新画像（写 SQLite）
    GET  /api/profiles/{user_id}        读取画像
    GET  /api/profiles                  读取最近一份画像
    POST /api/plans/generate            运行 Agent 生成计划
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.models import Profile
from app.db.sqlite_client import load_latest_profile, load_profile, save_plan, save_profile

app = FastAPI(
    title="健身营养 Agent API",
    version="0.1.0",
    description="根据身体条件、目标与器械生成一周训练计划与一日三餐。",
)

settings = get_settings()


@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    """内部调用鉴权：除 /health 外，请求头 X-API-Key 必须与 .env 中 API_KEY 一致。

    未配置 API_KEY（或仍为占位符）时不启用校验，便于本地开发与测试。
    """
    if request.url.path == "/health" or not settings.api_auth_enabled:
        return await call_next(request)
    if request.headers.get("X-API-Key") != settings.api_key:
        return JSONResponse(status_code=401, content={"detail": "无效或缺失的 X-API-Key"})
    return await call_next(request)


class PlanGenerateRequest(BaseModel):
    """生成计划请求。

    profile 可省略：此时按 user_id 从 SQLite 读取已存画像。
    """

    user_id: str = Field(min_length=1)
    profile: Profile | None = None
    persist: bool = Field(
        default=True, description="生成成功后是否把计划追加存入 generated_plans"
    )


async def run_agent(user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    """执行 LangGraph 工作流（测试中可 monkeypatch 此函数）。"""
    from app.agent.graph import agent_graph

    return await agent_graph.ainvoke(
        {"user_id": user_id, "profile": profile},
        # Checkpointer 要求按 thread_id 隔离会话记忆；同一 user_id 复用同一条会话
        config={"configurable": {"thread_id": user_id}},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.put("/api/profiles/{user_id}")
async def put_profile(user_id: str, profile: Profile) -> dict[str, str]:
    try:
        save_profile(profile, user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"画像保存失败：{exc}") from exc
    return {"user_id": user_id, "status": "saved"}


@app.get("/api/profiles/{user_id}")
async def get_profile(user_id: str) -> dict[str, Any]:
    profile = load_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该用户画像")
    return {"user_id": user_id, "profile": profile.model_dump()}


@app.get("/api/profiles")
async def get_latest_profile() -> dict[str, Any]:
    latest = load_latest_profile()
    if latest is None:
        raise HTTPException(status_code=404, detail="数据库中暂无画像")
    user_id, profile = latest
    return {"user_id": user_id, "profile": profile.model_dump()}


@app.post("/api/plans/generate")
async def generate_plan_endpoint(
    request: PlanGenerateRequest,
) -> dict[str, Any]:
    if request.profile is not None:
        profile_data = request.profile.model_dump()
    else:
        stored = load_profile(request.user_id)
        if stored is None:
            raise HTTPException(
                status_code=400,
                detail="未提供 profile，且该 user_id 在数据库中没有已存画像",
            )
        profile_data = stored.model_dump()

    try:
        result = await run_agent(request.user_id, profile_data)
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
    validation = result.get("validation") or {}
    if not plan:
        raise HTTPException(
            status_code=502,
            detail={"message": "本次未生成计划", "errors": result.get("errors", [])},
        )

    # 重试耗尽仍不合法：不把含编造内容的计划返回给用户，抛出降级提示
    if not validation.get("valid") and validation.get("user_message"):
        raise HTTPException(
            status_code=422,
            detail={"message": validation["user_message"]},
        )

    if request.persist:
        try:
            save_plan(request.user_id, plan, "weekly_plan")
        except Exception:
            # 计划已生成，持久化失败不应让整个请求失败
            pass

    return {
        "user_id": request.user_id,
        "plan": plan,
        "validation": result.get("validation"),
        "errors": result.get("errors", []),
    }

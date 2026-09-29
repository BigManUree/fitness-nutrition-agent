"""节点 1：校验用户画像。信息不全则返回 missing_fields，流程终止等待补全。"""

from __future__ import annotations

from pydantic import ValidationError

from app.agent.state import AgentState
from app.db.models import Profile


def collect_profile(state: AgentState) -> AgentState:
    raw = state.get("profile") or {}
    try:
        profile = Profile(**raw)
    except ValidationError as exc:
        missing = sorted({str(err["loc"][0]) for err in exc.errors()})
        return AgentState(
            missing_fields=missing,
            errors=[f"画像字段缺失或不合法：{', '.join(missing)}"],
        )
    return AgentState(profile=profile.model_dump(), missing_fields=[], errors=[])

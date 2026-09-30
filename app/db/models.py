"""数据模型定义。

Profile 与 docs/requirements.md 中 collect_profile 的 JSON Schema 保持一致：
性别 / 年龄 / 身高 / 体重 / 目标 / 每周训练天数 / 可用器械 / 饮食偏好 / 过敏。
"""

from typing import Literal

from pydantic import BaseModel, Field

Sex = Literal["male", "female"]
Goal = Literal["fat_loss", "muscle_gain", "recomp", "general_fitness"]


class Profile(BaseModel):
    """用户画像（结构化形态，存 SQLite；向量化前转自然语言）。"""

    sex: Sex
    age: int = Field(ge=14, le=80)
    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)
    goal: Goal
    days_per_week: int = Field(ge=1, le=7)
    equipment: list[str]
    medical_conditions: list[str] = Field(default_factory=list)
    dietary_preferences: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


# ============================================================
# 观测与复盘表（DDL 常量，由 sqlite_client 拼入 SCHEMA_SQL）
# ============================================================

# 性能流水：LangGraph 每个节点执行一条；token 仅模型节点有值，
# 安全拦截（safety.py）等不调模型的节点 token 字段为 NULL。
PERFORMANCE_LOG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS performance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    user_id TEXT,
    node_name TEXT,
    token_input INTEGER,
    token_output INTEGER,
    duration_ms INTEGER,
    status TEXT DEFAULT 'success' CHECK (status IN ('success', 'error')),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_performance_log_session
    ON performance_log(session_id);
CREATE INDEX IF NOT EXISTS idx_performance_log_created
    ON performance_log(created_at);
"""

# Bad Case 台账：与 docs/bad_cases.md 的字段对应；case_id 唯一，
# 同一 case 复盘修复走 upsert（更新 actual/fix_plan/status，刷新 updated_at）。
BAD_CASES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bad_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT UNIQUE,
    scenario_type TEXT,
    input TEXT,
    expected_output TEXT,
    actual_output TEXT,
    problem_category TEXT,
    severity TEXT,
    fix_plan TEXT,
    status TEXT DEFAULT '待修复',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bad_cases_status ON bad_cases(status);
CREATE INDEX IF NOT EXISTS idx_bad_cases_scenario ON bad_cases(scenario_type);
CREATE INDEX IF NOT EXISTS idx_bad_cases_severity ON bad_cases(severity);
"""

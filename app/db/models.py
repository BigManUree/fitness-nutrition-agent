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
    dietary_preferences: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)

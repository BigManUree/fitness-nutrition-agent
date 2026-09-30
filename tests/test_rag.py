"""RAG 画像入库测试。

不依赖真实 Ollama/Chroma：用 FakeCollection 记录 upsert/query 调用。
覆盖：自然语言渲染、数字格式化、空可选字段、元数据类型、upsert 入参、检索。
"""

from typing import Any

import pytest
from app.db.models import Profile
from app.rag import build_metadata, index_profile, profile_to_natural_language, search_profiles
from pydantic import ValidationError


def make_profile(**overrides: Any) -> Profile:
    data = {
        "sex": "male",
        "age": 30,
        "height_cm": 175,
        "weight_kg": 70,
        "goal": "muscle_gain",
        "days_per_week": 4,
        "equipment": ["dumbbell", "barbell"],
        "dietary_preferences": ["high protein"],
        "allergies": ["peanut"],
    }
    data.update(overrides)
    return Profile(**data)


class FakeCollection:
    """记录调用参数的 Chroma 集合替身。"""

    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls.append(kwargs)

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        return {"documents": [["30岁男性，身高175cm，体重70kg。"]]}


# ------------------------------------------------------------
# 自然语言渲染
# ------------------------------------------------------------

def test_natural_language_full_profile() -> None:
    text = profile_to_natural_language(make_profile())

    assert text.startswith("30岁男性，身高175cm，体重70kg，目标是增肌，每周训练4天")
    assert "可用器械：哑铃（dumbbell）、杠铃（barbell）" in text
    assert "饮食偏好：high protein" in text
    assert "过敏：peanut" in text
    assert text.endswith("。")


def test_natural_language_strips_trailing_zeros() -> None:
    text = profile_to_natural_language(make_profile(weight_kg=70.5))

    assert "身高175cm" in text  # 175.0 -> 175
    assert "体重70.5kg" in text


def test_natural_language_empty_optionals_say_none() -> None:
    text = profile_to_natural_language(
        make_profile(
            medical_conditions=[], dietary_preferences=[], allergies=[]
        )
    )

    assert "伤病情况：无伤病" in text
    assert "饮食偏好：无特殊偏好" in text
    assert "过敏：无" in text


def test_natural_language_includes_injuries() -> None:
    text = profile_to_natural_language(
        make_profile(medical_conditions=["膝盖旧伤"])
    )

    assert "伤病情况：膝盖旧伤" in text


def test_goal_labels() -> None:
    assert "减脂" in profile_to_natural_language(make_profile(goal="fat_loss"))
    assert "塑形" in profile_to_natural_language(make_profile(goal="recomp"))


# ------------------------------------------------------------
# 元数据
# ------------------------------------------------------------

def test_build_metadata_shapes() -> None:
    metadata = build_metadata(make_profile(), "user-123")

    assert metadata == {
        "user_id": "user-123",
        "goal": "muscle_gain",
        "equipment": "dumbbell,barbell",
        "medical_conditions": "",
        "allergies": "peanut",
    }
    # Chroma 要求所有值为 str/int/float/bool，且不允许 None
    assert all(isinstance(value, str) for value in metadata.values())


def test_build_metadata_empty_lists_become_empty_strings() -> None:
    metadata = build_metadata(
        make_profile(allergies=[]), "user-123"
    )

    assert metadata["allergies"] == ""


# ------------------------------------------------------------
# upsert
# ------------------------------------------------------------

def test_index_profile_calls_upsert() -> None:
    collection = FakeCollection()

    index_profile(make_profile(), "user-123", collection=collection)

    assert len(collection.upsert_calls) == 1
    call = collection.upsert_calls[0]
    assert call["ids"] == ["user-123"]
    assert call["documents"] == [profile_to_natural_language(make_profile())]
    assert call["metadatas"] == [build_metadata(make_profile(), "user-123")]


def test_index_profile_rejects_invalid_profile() -> None:
    with pytest.raises(ValidationError):
        Profile(sex="male", age=10)  # 低于最小年龄，且缺必填字段


# ------------------------------------------------------------
# 检索
# ------------------------------------------------------------

def test_search_profiles_returns_documents() -> None:
    collection = FakeCollection()

    docs = search_profiles("我想调整训练计划", "user-123", collection=collection)

    assert docs == ["30岁男性，身高175cm，体重70kg。"]
    query_call = collection.query_calls[0]
    assert query_call["query_texts"] == ["我想调整训练计划"]
    assert query_call["where"] == {"user_id": "user-123"}

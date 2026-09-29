"""app.tools.profile_tools 测试：规整、校验、缺字段追问。"""

from __future__ import annotations

import pytest
from app.tools import (
    ProfileToolError,
    build_profile,
    missing_profile_fields,
    normalize_equipment,
    normalize_text_list,
)

VALID_RAW = {
    "sex": "male",
    "age": 28,
    "height_cm": 175,
    "weight_kg": 72,
    "goal": "muscle_gain",
    "days_per_week": 3,
    "equipment": [" Dumbbell ", "dumbbell", "", "Barbell"],
    "dietary_preferences": [" 高蛋白 ", "高蛋白"],
    "allergies": ["peanut"],
}


def test_normalize_text_list_trims_dedups_and_preserves_order():
    assert normalize_text_list([" a ", "a", "", "b", "  "]) == ["a", "b"]
    assert normalize_text_list(None) == []


def test_normalize_text_list_rejects_non_list():
    with pytest.raises(ProfileToolError):
        normalize_text_list("dumbbell")
    with pytest.raises(ProfileToolError):
        normalize_text_list([1, 2])


def test_normalize_equipment_lowercases():
    assert normalize_equipment(["Dumbbell", " dumbbell", "Barbell"]) == [
        "dumbbell",
        "barbell",
    ]


def test_build_profile_cleans_and_validates():
    profile = build_profile(VALID_RAW)
    assert profile.equipment == ["dumbbell", "barbell"]
    assert profile.dietary_preferences == ["高蛋白"]
    assert profile.allergies == ["peanut"]


def test_build_profile_rejects_bad_enum():
    raw = dict(VALID_RAW, goal="become-invincible")
    with pytest.raises(ProfileToolError):
        build_profile(raw)


def test_build_profile_rejects_non_dict():
    with pytest.raises(ProfileToolError):
        build_profile("not a dict")  # type: ignore[arg-type]


def test_missing_profile_fields_lists_required():
    assert missing_profile_fields({"goal": "muscle_gain"}) == [
        "sex",
        "age",
        "height_cm",
        "weight_kg",
        "days_per_week",
        "equipment",
    ]
    assert missing_profile_fields({}) == list(missing_profile_fields(""))
    assert missing_profile_fields(VALID_RAW) == []


def test_empty_equipment_counts_as_missing():
    raw = dict(VALID_RAW, equipment=[])
    assert "equipment" in missing_profile_fields(raw)

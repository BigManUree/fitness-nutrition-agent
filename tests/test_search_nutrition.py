"""search_nutrition 节点：按偏好/目标个性化检索词表测试。"""

from __future__ import annotations

from app.agent.nodes.search_nutrition import build_queries


def test_default_queries_include_omnivore_protein_and_grains():
    queries = build_queries([])
    assert "chicken breast" in queries
    assert "salmon" in queries
    assert "oatmeal" in queries
    assert "brown rice" in queries
    assert "broccoli" in queries
    # 不应包含植物蛋白专有词
    assert "tofu" not in queries


def test_vegetarian_swaps_to_plant_protein():
    queries = build_queries(["素食"])
    assert "tofu" in queries
    assert "lentil" in queries
    assert "chickpea" in queries
    # 荤食被替换
    assert "chicken breast" not in queries
    assert "beef" not in queries
    assert "salmon" not in queries


def test_vegetarian_english_keyword():
    queries = build_queries(["vegetarian"])
    assert "tofu" in queries
    assert "chicken breast" not in queries


def test_low_carb_reduces_grains_and_adds_veggies():
    queries = build_queries(["低碳水"])
    # 主食压缩为仅燕麦
    assert "oatmeal" in queries
    assert "brown rice" not in queries
    assert "quinoa" not in queries
    # 低碳额外蔬菜/优质脂肪
    assert "cauliflower" in queries
    assert "avocado" in queries


def test_queries_are_deduplicated():
    # 无重复项
    queries = build_queries([])
    assert len(queries) == len(set(queries))


def test_preference_keywords_case_insensitive():
    queries = build_queries(["VeGaN"])
    assert "tofu" in queries
    assert "chicken breast" not in queries
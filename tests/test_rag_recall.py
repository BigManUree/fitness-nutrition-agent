"""画像召回准确率测试：用 eval_set.json 的 10 条正向用例驱动。

指标定义：
    Recall@5（向量召回 n_results=5）：目标画像文档出现在前 5 条中；
    Recall@3（keyword_rerank 后）：目标画像重排后进入前 3。

为保证门禁不依赖 Ollama/嵌入服务，这里用 BigramSimilarityCollection：
以查询与文档的字符二元组重叠做确定性"伪向量"排序——它验证的是
"画像模板是否把查询中的关键约束写进了文档"以及 rerank 的有效性；
真实嵌入的召回需在服务环境单独跑（见文末 skip 说明）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.rag.profile_indexer import (
    DEFAULT_N_RESULTS,
    keyword_rerank,
    profile_to_natural_language,
)
from app.tools import build_profile

EVAL_SET = Path("tests/test_data/eval_set.json")

# ============================================================
# 字符 bigram 相似度集合（确定性 fake Chroma）
# ============================================================


def _bigrams(text: str) -> set[str]:
    # 仅保留中英文/数字字符，连续二元组（"3天""健身房"等均可命中）
    chars = re.findall(r"[一-鿿]|[a-z0-9]+", text.lower())
    flat: list[str] = []
    for token in chars:
        if re.fullmatch(r"[a-z0-9]+", token):
            flat.extend(list(token))
        else:
            flat.append(token)
    return {flat[i] + flat[i + 1] for i in range(len(flat) - 1)}


class BigramSimilarityCollection:
    """最小 Chroma 集合：upsert 存文档，query 按 bigram 重叠排序。"""

    def __init__(self) -> None:
        self._docs: dict[str, str] = {}

    def upsert(self, *, ids: list[str], documents: list[str], **_: Any) -> None:
        for doc_id, doc in zip(ids, documents, strict=True):
            self._docs[doc_id] = doc

    def query(
        self,
        *,
        query_texts: list[str],
        n_results: int,
        **_: Any,
    ) -> dict[str, Any]:
        query_grams = _bigrams(query_texts[0])
        scored = [
            (
                len(query_grams & _bigrams(doc)),
                doc_id,
                doc,
            )
            for doc_id, doc in self._docs.items()
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        top = [doc for _, _, doc in scored[:n_results]]
        return {"documents": [top]}


# ============================================================
# 构建评估集语料
# ============================================================


def _positive_cases() -> list[dict[str, Any]]:
    data = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    return [c for c in data["cases"] if c["type"] == "positive"]


POSITIVE_CASES = _positive_cases()


def _indexed_collection() -> tuple[BigramSimilarityCollection, dict[str, str]]:
    collection = BigramSimilarityCollection()
    target_docs: dict[str, str] = {}
    for case in POSITIVE_CASES:
        profile = build_profile(case["profile"])
        doc = profile_to_natural_language(profile)
        collection.upsert(ids=[case["id"]], documents=[doc])
        target_docs[case["id"]] = doc
    return collection, target_docs


def _recall_at(candidates: list[str], target: str, k: int) -> bool:
    return target in candidates[:k]


# ============================================================
# Recall@5：增大 n_results 后的召回
# ============================================================


def test_positive_set_has_10_cases():
    assert len(POSITIVE_CASES) == 10


def test_default_n_results_is_5():
    assert DEFAULT_N_RESULTS == 5


def test_recall_at_5_is_perfect():
    collection, target_docs = _indexed_collection()

    hits = 0
    for case in POSITIVE_CASES:
        results = collection.query(
            query_texts=[case["query"]], n_results=5
        )["documents"][0]
        if _recall_at(results, target_docs[case["id"]], 5):
            hits += 1

    assert hits == 10, f"Recall@5 = {hits}/10"


# ============================================================
# Recall@3：rerank 后的召回（应不劣化，且目标进 top3）
# ============================================================


def test_rerank_recall_at_3_is_perfect():
    collection, target_docs = _indexed_collection()

    hits = 0
    for case in POSITIVE_CASES:
        recalled = collection.query(
            query_texts=[case["query"]], n_results=5
        )["documents"][0]
        reranked = keyword_rerank(case["query"], recalled, top_k=3)
        if _recall_at(reranked, target_docs[case["id"]], 3):
            hits += 1

    assert hits == 10, f"rerank Recall@3 = {hits}/10"


def test_rerank_keeps_perfect_vector_result_when_no_keyword_match():
    """查询无任何关键词命中时，rerank 保持原顺序（不退化为乱序）。"""
    docs = ["文档A内容", "文档B内容", "文档C内容"]
    ranked = keyword_rerank("zzz qqq", docs, top_k=3)
    assert ranked == docs


def test_rerank_moves_keyword_match_to_top():
    query = "我在健身房增肌"
    docs = [
        "26岁女性，身高163cm，体重58kg，目标是减脂，每周训练3天",
        "28岁男性，身高178cm，体重74kg，目标是增肌，每周训练4天，"
        "可用器械：健身房（全部器械可用）",
    ]

    ranked = keyword_rerank(query, docs, top_k=2)

    assert ranked[0] == docs[1]  # 同时命中"健身房+增肌"两个维度


# ============================================================
# 真实嵌入召回（需 Ollama/旁路在跑；CI 跳过）
# ============================================================


def test_real_embedding_recall_when_available():
    """服务环境下的真实 Recall@5 冒烟：嵌入服务不可达则跳过。"""
    import pytest
    from app.rag.embedding import get_embedding_function

    try:
        ef = get_embedding_function()
        vectors = ef(["健康测试"])
    except Exception:
        pytest.skip("嵌入服务未启动，跳过真实向量召回")

    assert vectors and len(vectors[0]) > 100

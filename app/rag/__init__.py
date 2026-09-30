"""RAG 模块：用户画像向量化与检索。"""

from app.rag.profile_indexer import (
    build_metadata,
    index_profile,
    keyword_rerank,
    profile_to_natural_language,
    search_profiles,
)

__all__ = [
    "profile_to_natural_language",
    "build_metadata",
    "index_profile",
    "search_profiles",
    "keyword_rerank",
]

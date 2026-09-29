"""Chroma 初始化与集合访问。

本地持久化到 CHROMA_DB_PATH（默认 ./data/chroma_db），
集合名 user_profiles，距离度量 cosine。
"""

import os
from pathlib import Path

import chromadb
from chromadb import Collection
from chromadb.api import ClientAPI

from app.rag.embedding import get_embedding_function

COLLECTION_NAME = "user_profiles"


def get_db_path() -> Path:
    return Path(os.getenv("CHROMA_DB_PATH", "./data/chroma_db"))


def get_client() -> ClientAPI:
    """返回本地持久化 Chroma 客户端。"""
    db_path = get_db_path()
    db_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(db_path))


def get_user_profiles_collection() -> Collection:
    """获取（不存在则创建）用户画像集合，已绑定 Ollama 嵌入函数。"""
    return get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )

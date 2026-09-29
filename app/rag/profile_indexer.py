"""用户画像入库：Profile -> 自然语言描述 -> upsert 到 Chroma。

数据流（见 docs/requirements.md 数据流全景）：
    Profile（结构化，SQLite）
      -> profile_to_natural_language()
      -> Chroma 经 Ollama 生成 Qwen3-Embedding 向量
      -> collection.upsert(ids, documents, metadatas)

画像作为整体 chunk（CLAUDE.md 分块策略）；Chroma 元数据只放
可过滤、且类型为 str/int/float/bool 的字段（None 不允许）。
"""

from collections.abc import Sequence

from app.db.models import Profile
from app.rag.chroma_client import get_user_profiles_collection

# 枚举值 -> 中文描述
_SEX_LABELS = {"male": "男性", "female": "女性"}
_GOAL_LABELS = {
    "fat_loss": "减脂",
    "muscle_gain": "增肌",
    "recomp": "塑形（减脂同时增肌）",
    "general_fitness": "综合体能与健康",
}


def profile_to_natural_language(profile: Profile) -> str:
    """把 Profile 渲染为一段中文自然语言，作为向量化的 document。

    必填字段（性别/年龄/身高/体重/目标/训练天数/器械）按固定顺序输出；
    可选的饮食偏好与过敏为空时以"无"明确标注，而不是静默省略，
    使语义检索能区分"未提供"与"有特殊限制"。
    """
    parts: list[str] = [
        f"{_format_number(profile.age)}岁{_SEX_LABELS[profile.sex]}",
        f"身高{_format_number(profile.height_cm)}cm",
        f"体重{_format_number(profile.weight_kg)}kg",
        f"目标是{_GOAL_LABELS[profile.goal]}",
        f"每周训练{profile.days_per_week}天",
        f"可用器械：{_join_items(profile.equipment)}",
        f"饮食偏好：{_join_items(profile.dietary_preferences, empty='无特殊偏好')}",
        f"过敏：{_join_items(profile.allergies, empty='无')}",
    ]
    return "，".join(parts) + "。"


def build_metadata(profile: Profile, user_id: str) -> dict[str, str]:
    """构建 Chroma 元数据。

    列表字段逗号拼接成字符串；空列表给空串。Chroma 不接受 None 值，
    因此这里所有值都保证为字符串。
    """
    return {
        "user_id": user_id,
        "goal": profile.goal,
        "equipment": ",".join(profile.equipment),
        "allergies": ",".join(profile.allergies),
    }


def index_profile(
    profile: Profile,
    user_id: str,
    collection=None,
) -> None:
    """把画像向量化并 upsert 进 Chroma。

    Args:
        profile: 用户画像。
        user_id: 用户唯一标识，同时作为 Chroma 文档 id；重复入库即覆盖。
        collection: 可注入的集合（测试用）；为 None 时使用本地默认集合。

    Raises:
        连接错误：默认集合在 Ollama 未启动时，upsert 会因无法生成向量而失败。
    """
    collection = collection or get_user_profiles_collection()
    document = profile_to_natural_language(profile)
    metadata = build_metadata(profile, user_id)

    collection.upsert(
        ids=[user_id],
        documents=[document],
        metadatas=[metadata],
    )


def search_profiles(
    query_text: str,
    user_id: str,
    n_results: int = 3,
    collection=None,
) -> Sequence[str]:
    """按自然语言查询检索画像文档，并按 user_id 过滤。

    供"用户要求调整计划"节点使用：返回匹配到的画像自然语言描述。
    """
    collection = collection or get_user_profiles_collection()
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where={"user_id": user_id},
    )
    documents = results.get("documents") or []
    return documents[0] if documents else []


def _format_number(value: float) -> str:
    """整数浮点去掉无意义的 .0（175.0 -> '175'，70.5 -> '70.5'）。"""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _join_items(items: Sequence[str], *, empty: str = "无") -> str:
    return "、".join(items) if items else empty

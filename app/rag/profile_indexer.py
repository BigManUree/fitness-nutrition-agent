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
    # 固定模板：9 类信息全部出现且顺序固定，便于向量稳定编码与关键词 rerank。
    # 每个可选维度为空都显式写"无"，使检索能区分"未提供"与"有限制"。
    parts: list[str] = [
        f"{_format_number(profile.age)}岁{_SEX_LABELS[profile.sex]}",
        f"身高{_format_number(profile.height_cm)}cm",
        f"体重{_format_number(profile.weight_kg)}kg",
        f"目标是{_GOAL_LABELS[profile.goal]}",
        f"每周训练{profile.days_per_week}天",
        f"可用器械：{_format_equipment(profile.equipment)}",
        f"伤病情况：{_join_items(profile.medical_conditions, empty='无伤病')}",
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
        "medical_conditions": ",".join(profile.medical_conditions),
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


DEFAULT_N_RESULTS = 5


def search_profiles(
    query_text: str,
    user_id: str,
    n_results: int = DEFAULT_N_RESULTS,
    collection=None,
    rerank: bool = False,
    top_k: int | None = None,
) -> Sequence[str]:
    """按自然语言查询检索画像文档，并按 user_id 过滤。

    n_results 默认 5（调参：由 3 增大以提高召回）；rerank=True 时
    在向量召回结果上再做一次简单关键词重排（见 keyword_rerank）。
    """
    collection = collection or get_user_profiles_collection()
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where={"user_id": user_id},
    )
    documents = results.get("documents") or []
    candidates = documents[0] if documents else []
    if rerank:
        return keyword_rerank(query_text, candidates, top_k=top_k or n_results)
    return candidates


# ============================================================
# 关键词 rerank（可选，轻量，无模型调用）
# ============================================================

# 语义维度：查询中命中"触发词"，则文档中出现"文档形态"即得分。
# 文档形态与 profile_to_natural_language 的渲染结果保持一致。
_RERANK_KEYWORD_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # 目标
    (("增肌",), ("目标是增肌",)),
    (("减脂", "瘦"), ("目标是减脂",)),
    (("塑形",), ("塑形",)),
    # 器械
    (("健身房",), ("健身房（全部器械可用）",)),
    (("哑铃", "dumbbell"), ("可用器械：dumbbell", "dumbbell")),
    (("杠铃", "barbell"), ("可用器械：barbell", "barbell")),
    (("弹力带", "band"), ("band",)),
    (("无器械", "自重", "没有任何器械"), ("bodyweight", "无器械")),
    # 饮食与过敏
    (("素食", "吃素"), ("素食",)),
    (("乳糖不耐", "奶制品"), ("乳糖",)),
    (("不吃牛肉",), ("不吃牛肉",)),
    (("不吃海鲜",), ("不吃海鲜", "海鲜")),
    # 伤病
    (("膝盖",), ("膝盖",)),
    (("肩",), ("肩",)),
)


def extract_query_keywords(query_text: str) -> list[tuple[str, ...]]:
    """提取查询命中的语义维度（返回对应的文档形态元组列表）。"""
    matched: list[tuple[str, ...]] = []
    for triggers, doc_forms in _RERANK_KEYWORD_GROUPS:
        if any(trigger in query_text for trigger in triggers):
            matched.append(doc_forms)
    return matched


def keyword_rerank(
    query_text: str,
    documents: Sequence[str],
    top_k: int = 3,
) -> list[str]:
    """对向量召回的文档做简单关键词重排。

    打分：文档命中查询语义维度的数量（命中越多排越前）；
    分数相同保持原相对顺序（向量相似度作为隐式 tie-break，稳定排序）。
    无任何关键词命中时顺序不变，等价于纯向量结果。
    """
    keyword_groups = extract_query_keywords(query_text)

    def score(doc: str) -> int:
        return sum(
            1
            for forms in keyword_groups
            if any(form in doc for form in forms)
        )

    ranked = sorted(documents, key=score, reverse=True)
    return ranked[:top_k]


# 器械标识 -> 中文标签（英文保留括号内：中文查询靠标签命中，英文查询/rerank 不受影响）
_EQUIPMENT_LABELS = {
    "dumbbell": "哑铃（dumbbell）",
    "barbell": "杠铃（barbell）",
    "kettlebell": "壶铃（kettlebell）",
    "band": "弹力带（band）",
    "bodyweight": "自重（bodyweight）",
    "bench": "卧推凳（bench）",
    "cable": "绳索器械（cable）",
    "machine": "固定器械（machine）",
    "pull-up bar": "引体杆（pull-up bar）",
}


def _format_equipment(items: Sequence[str]) -> str:
    """渲染器械列表；gym（健身房）折叠值转成可读中文，其余加中文标签。"""
    if items == ["gym"]:
        return "健身房（全部器械可用）"
    return _join_items([_EQUIPMENT_LABELS.get(item, item) for item in items])


def _format_number(value: float) -> str:
    """整数浮点去掉无意义的 .0（175.0 -> '175'，70.5 -> '70.5'）。"""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _join_items(items: Sequence[str], *, empty: str = "无") -> str:
    return "、".join(items) if items else empty

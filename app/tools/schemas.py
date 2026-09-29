"""工具函数的 JSON Schema 契约。

约定：
    - *_INPUT_SCHEMA  校验调用方传入的参数；
    - *_OUTPUT_SCHEMA 校验"规范化之后"的返回结果（内部统一 snake_case）。

MCP 原始字段（如 primaryMuscles）不直接对外暴露，先在 tools 层
规范化，再按这里的 schema 校验，使下游节点与 MCP 数据版本解耦。
"""

# ---- 枚举值（与 exerciseapi 当前数据一致） ----

CATEGORIES = [
    "strength",
    "calisthenics",
    "yoga",
    "pilates",
    "mobility",
    "physical_therapy",
    "plyometrics",
    "stretching",
    "conditioning",
    "olympic_weightlifting",
    "powerlifting",
    "strongman",
]

DIFFICULTIES = ["beginner", "intermediate", "advanced"]

# ============================================================
# search_exercises
# ============================================================

SEARCH_EXERCISES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        # 自由文本（动作名/关键词）
        "query": {"type": "string", "minLength": 1, "maxLength": 100},
        # 肌群，如 "chest"、"glutes"
        "muscle": {"type": "string", "minLength": 1, "maxLength": 50},
        "category": {"type": "string", "enum": CATEGORIES},
        # 器械，如 "dumbbell"、"barbell"、"bodyweight"
        "equipment": {"type": "string", "minLength": 1, "maxLength": 50},
        "difficulty": {"type": "string", "enum": DIFFICULTIES},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        # 为 true 时只保留以目标肌群为主肌群的动作（工具层二次过滤）
        "primary_only": {"type": "boolean"},
    },
    "additionalProperties": False,
}

_EXERCISE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "primary_muscles": {"type": "array", "items": {"type": "string"}},
        "secondary_muscles": {"type": "array", "items": {"type": "string"}},
        "equipment": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
        "difficulty": {"type": ["string", "null"], "enum": DIFFICULTIES + [None]},
        "force": {"type": ["string", "null"]},
        "mechanic": {"type": ["string", "null"]},
    },
    "required": ["id", "name", "primary_muscles", "secondary_muscles"],
    "additionalProperties": False,
}

SEARCH_EXERCISES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": _EXERCISE_ITEM_SCHEMA},
        "total": {"type": "integer", "minimum": 0},
        "source": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["items", "total", "source"],
    "additionalProperties": False,
}

# ============================================================
# substitute_exercise
# ============================================================

SUBSTITUTE_EXERCISE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        # 被替换的动作名（必须能在动作库中定位，不凭名字猜测肌群）
        "original_exercise": {"type": "string", "minLength": 1, "maxLength": 100},
        # 替换原因，如 "膝盖不适"、"没有哑铃"
        "reason": {"type": "string", "minLength": 1, "maxLength": 200},
        # 用户可用器械，如 ["barbell", "bodyweight"]；
        # 为空时不按器械过滤（只保证同肌群）
        "equipment_available": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
            "maxItems": 20,
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
    },
    "required": ["original_exercise", "reason"],
    "additionalProperties": False,
}

_SUBSTITUTE_ITEM_SCHEMA = {
    **_EXERCISE_ITEM_SCHEMA,
    # 附加：为什么这条适合作为替代（同肌群/同器械/难度相近）
    "properties": {
        **_EXERCISE_ITEM_SCHEMA["properties"],
        "match_reasons": {"type": "array", "items": {"type": "string"}},
    },
}

SUBSTITUTE_EXERCISE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "original_exercise": {"type": "string", "minLength": 1},
        "alternatives": {"type": "array", "items": _SUBSTITUTE_ITEM_SCHEMA},
        "total": {"type": "integer", "minimum": 0},
        "source": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["original_exercise", "alternatives", "total", "source"],
    "additionalProperties": False,
}

# ============================================================
# search_nutrition
# ============================================================

SEARCH_NUTRITION_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        # 食物名称，必填（CLAUDE.md：信息不全时不自动补默认值）
        "query": {"type": "string", "minLength": 1, "maxLength": 100},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["query"],
    "additionalProperties": False,
}

_MACROS_SCHEMA = {
    "type": "object",
    "properties": {
        "calories": {"type": ["number", "null"], "minimum": 0},
        "protein": {"type": ["number", "null"], "minimum": 0},
        "fat": {"type": ["number", "null"], "minimum": 0},
        "carbs": {"type": ["number", "null"], "minimum": 0},
        "fiber": {"type": ["number", "null"], "minimum": 0},
        "sugar": {"type": ["number", "null"], "minimum": 0},
        "sodium": {"type": ["number", "null"], "minimum": 0},
    },
    # 分量未知的字段允许为 null，但字段本身存在，方便下游直接取用
    "required": ["calories", "protein", "fat", "carbs"],
    "additionalProperties": False,
}

_FOOD_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "brand": {"type": ["string", "null"]},
        # "per_serving" | "per_100g"
        "basis": {"type": ["string", "null"]},
        "serving_size": {"type": ["string", "null"]},
        "serving_weight_g": {"type": ["number", "null"], "minimum": 0},
        # 宏量营养素随 basis 缩放后的值
        "calories": {"type": ["number", "null"], "minimum": 0},
        "protein": {"type": ["number", "null"], "minimum": 0},
        "fat": {"type": ["number", "null"], "minimum": 0},
        "carbs": {"type": ["number", "null"], "minimum": 0},
        "fiber": {"type": ["number", "null"], "minimum": 0},
        "sugar": {"type": ["number", "null"], "minimum": 0},
        "sodium": {"type": ["number", "null"], "minimum": 0},
        # 每 100g 的标准值，始终保留以便二次计算
        "per_100g": _MACROS_SCHEMA,
    },
    "required": ["id", "name", "per_100g"],
    "additionalProperties": False,
}

SEARCH_NUTRITION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": _FOOD_ITEM_SCHEMA},
        "total": {"type": "integer", "minimum": 0},
        "source": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["items", "total", "source"],
    "additionalProperties": False,
}

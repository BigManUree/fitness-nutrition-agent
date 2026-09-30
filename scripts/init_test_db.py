"""初始化测试用 SQLite 数据库。

与 scripts/init_db.py 的区别：
    - 默认写入独立测试库 ./data/test_app.db，绝不污染开发库 ./data/app.db；
    - 除 user_profile / generated_plans 外，额外建 eval_run 表，
      供离线评估脚本回填 eval_set.json 中各用例的 metrics。

用法：
    uv run python scripts/init_test_db.py
    uv run python scripts/init_test_db.py --path ./tmp/pytest.db

可重复执行：表已存在时不会重建或清空数据。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.sqlite_client import SCHEMA_SQL  # noqa: E402

DEFAULT_TEST_DB_PATH = Path("./data/test_app.db")

# 评估结果表：每条用例一行；metrics 与 eval_set.json 的 metrics 字段对应。
# 重复评估同一用例时追加历史行，便于对比不同版本。
EVAL_RUN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eval_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    case_type TEXT,
    retrieval_accuracy REAL,
    tool_call_accuracy REAL,
    plan_quality_score REAL,
    metrics_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_test_db(db_path: str | Path | None = None) -> Path:
    """在测试库中创建全部表（幂等），返回库路径。"""
    path = Path(db_path) if db_path is not None else DEFAULT_TEST_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(EVAL_RUN_SCHEMA_SQL)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化测试用 SQLite 数据库")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_TEST_DB_PATH,
        help="测试库路径（默认 ./data/test_app.db）",
    )
    args = parser.parse_args()

    if args.path.resolve() == Path("./data/app.db").resolve():
        print("[错误] 测试库路径不能与开发库 ./data/app.db 相同，已中止。")
        sys.exit(1)

    db_path = init_test_db(args.path)
    print(f"测试数据库初始化完成：{db_path.resolve()}")

    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
    print("当前数据表：", ", ".join(tables))


if __name__ == "__main__":
    main()

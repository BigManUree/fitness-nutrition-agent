"""初始化 SQLite 数据库：创建全部业务表。

表清单（DDL 单一事实源：app/db/sqlite_client.py 的 SCHEMA_SQL）：
    user_profile     用户画像（按 user_id 唯一）
    generated_plans  生成计划历史
    performance_log  节点性能流水（token / 耗时 / 状态）
    bad_cases        Bad Case 台账（与 docs/bad_cases.md 对应）

用法：
    uv run python scripts/init_db.py
    uv run python scripts/init_db.py --path ./tmp/app.db

可重复执行：表已存在时不会重建或清空数据。
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.sqlite_client import ensure_tables  # noqa: E402


def init_db(db_path: Path | None = None) -> Path:
    return ensure_tables(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 SQLite 数据库")
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="数据库路径（默认取 SQLITE_DB_PATH，即 ./data/app.db）",
    )
    args = parser.parse_args()

    db_path = init_db(args.path)
    print(f"数据库初始化完成：{db_path.resolve()}")

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

"""初始化 SQLite 数据库：创建 user_profile 与 generated_plans 两张表。

用法：
    uv run python scripts/init_db.py

可重复执行：表已存在时不会重建或清空数据。
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.sqlite_client import ensure_tables  # noqa: E402


def init_db(db_path: Path | None = None) -> Path:
    return ensure_tables(db_path)


def main() -> None:
    db_path = init_db()
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

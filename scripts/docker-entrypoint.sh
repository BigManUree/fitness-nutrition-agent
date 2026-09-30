#!/bin/sh
# 容器入口：确保数据目录与 SQLite 表就绪，然后执行 CMD。
# 密钥不写进镜像：DEEPSEEK_API_KEY / EXERCISEAPI_KEY / USDA_API_KEY 等
# 通过 `docker run -e` 或 --env-file 传入（应用配置直接读环境变量）。
set -e

cd /app

mkdir -p /app/data

# SQLITE_DB_PATH 未显式传入时用默认路径；仅在库文件不存在时初始化，
# 避免每次重启覆盖已挂载卷中的历史数据。
DB_PATH="${SQLITE_DB_PATH:-/app/data/app.db}"
if [ ! -f "$DB_PATH" ]; then
    echo "[entrypoint] 未发现数据库 $DB_PATH，执行初始化..."
    python scripts/init_db.py --path "$DB_PATH"
fi

exec "$@"

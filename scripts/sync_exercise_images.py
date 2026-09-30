"""一次性同步 exerciseapi 全部动作示范图到本地目录。

背景（重要）：
    exerciseapi 的 images 字段是**相对路径**（如 "Barbell_Squat/0.jpg"），
    官方不公开固定图片域名（见 https://exerciseapi.dev/llms.txt：
    "prepend your own image base URL"）。因此本脚本拆成两步：

      1) 枚举：通过 MCP 搜索（按 12 个分类 + 主要肌群）尽力拉取全部动作，
         收集所有相对图片路径（去重）；
      2) 下载：从 --source-base（必填）下载每个相对路径，保持目录结构
         存入 --dest；已存在且非空的文件默认跳过（可断点续跑）。

    source-base 需由你提供：在任何能看到真实示范图的地方（浏览器开发者
    工具抓到的图片 URL、官方支持回复等）取域名，如
        https://your-image-host/
    本脚本不会猜测或编造源域名——猜不出正确域名，宁可不给。

用法：
    # 先确保 MCP 桥接可用
    make mcp-up

    # 仅枚举，查看会下载多少张（不下载）
    uv run python scripts/sync_exercise_images.py --dry-run

    # 全量下载到 ./data/exercise_images
    uv run python scripts/sync_exercise_images.py \\
        --source-base https://your-image-host/ \\
        --dest ./data/exercise_images

下载完成后，在 .env 设置：
    EXERCISEAPI_IMAGE_BASE=./data/exercise_images   # 本地直接用
    # 或把该目录整体传到 R2 / GitHub Pages 后填对应 https 域名
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 让脚本能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_dotenv  # noqa: E402
from app.tools.exercise_tools import search_exercises  # noqa: E402

# exerciseapi 共 12 个分类（见 app/tools/schemas.py CATEGORIES）
CATEGORIES = [
    "strength", "calisthenics", "yoga", "pilates", "mobility",
    "physical_therapy", "plyometrics", "stretching", "conditioning",
    "olympic_weightlifting", "powerlifting", "strongman",
]
# 再按主要肌群补一轮，覆盖分类分页（每类上限 100）可能漏掉的动作
MUSCLES = [
    "chest", "back", "shoulders", "biceps", "triceps", "quads",
    "hamstrings", "glutes", "abs", "calves", "forearms",
]

PAGE_SIZE = 100
MAX_WORKERS = 6
RETRIES = 2
TIMEOUT = 30


async def _collect_image_paths() -> tuple[set[str], int]:
    """枚举全部动作，返回 (相对图片路径集合, 去重后的动作数)。"""
    paths: set[str] = set()
    exercise_names: set[str] = set()

    async def pull(**kwargs) -> None:
        try:
            result = await search_exercises(limit=PAGE_SIZE, **kwargs)
        except Exception as exc:  # 单轮失败不应中断整体
            print(f"  ! 检索失败 {kwargs}: {exc}")
            return
        for item in result.get("items", []):
            exercise_names.add(item.get("name", ""))
            for rel in item.get("images", []):
                if rel:
                    paths.add(rel)

    await asyncio.gather(*(pull(category=c) for c in CATEGORIES))
    await asyncio.gather(*(pull(muscle=m) for m in MUSCLES))
    return paths, len(exercise_names)


def _download_one(rel: str, source_base: str, dest: Path) -> tuple[str, str]:
    """下载单张图片；返回 (相对路径, 状态 ok/skip/error:原因)。"""
    target = dest / rel
    if target.exists() and target.stat().st_size > 0:
        return rel, "skip"

    url = source_base + rel
    last_err = ""
    for attempt in range(RETRIES + 1):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "exercise-image-sync/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            if not data:
                raise ValueError("empty body")
            target.write_bytes(data)
            return rel, "ok"
        except Exception as exc:  # noqa: BLE001 - 记录后重试
            last_err = str(exc)
            time.sleep(0.5 * (attempt + 1))
    return rel, f"error:{last_err}"


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 exerciseapi 动作示范图")
    parser.add_argument("--source-base", default=os.getenv("EXERCISEAPI_IMAGE_SOURCE_BASE", ""),
                        help="图片源域名（末尾 / 可省略）；官方不公开，需自行提供")
    parser.add_argument("--dest", default="./data/exercise_images", help="本地保存目录")
    parser.add_argument("--dry-run", action="store_true", help="只枚举不下载")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    load_dotenv()

    print("① 枚举动作与图片路径（通过 MCP，约需 1-2 分钟）…")
    paths, n_exercises = asyncio.run(_collect_image_paths())
    print(f"   去重后动作 {n_exercises} 个，待同步图片 {len(paths)} 张")

    if not paths:
        print("   没有可同步的图片（MCP 是否启动？make mcp-up）。")
        return 1

    if args.dry_run:
        print("② --dry-run：不下载。前 10 条相对路径：")
        for rel in sorted(paths)[:10]:
            print(f"   - {rel}")
        return 0

    if not args.source_base:
        print("② 缺少 --source-base。")
        print("   官方不公开图片域名，本脚本不猜测。请提供真实源域名，例如：")
        print("   uv run python scripts/sync_exercise_images.py "
              "--source-base https://your-image-host/")
        return 2

    source_base = args.source_base.strip()
    if not source_base.endswith("/"):
        source_base += "/"
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    print(f"② 下载 {len(paths)} 张：{source_base} -> {dest}（workers={args.workers}）")
    n_ok = n_skip = n_err = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_download_one, rel, source_base, dest): rel
                   for rel in sorted(paths)}
        for i, future in enumerate(as_completed(futures), 1):
            rel, status = future.result()
            if status == "ok":
                n_ok += 1
            elif status == "skip":
                n_skip += 1
            else:
                n_err += 1
                failures.append(f"{rel}  {status}")
            if i % 25 == 0 or i == len(paths):
                print(f"   进度 {i}/{len(paths)}  新下载 {n_ok} 跳过 {n_skip} 失败 {n_err}")

    if failures:
        print(f"③ 完成，但 {n_err} 张失败，可重新运行本脚本续传（已下载会跳过）：")
        for line in failures[:20]:
            print(f"   - {line}")
    else:
        print(f"③ 全部完成：新下载 {n_ok}，已存在跳过 {n_skip}。")
        print("   可在 .env 设置 EXERCISEAPI_IMAGE_BASE 指向该目录或其托管域名。")
    return 0 if n_err == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())

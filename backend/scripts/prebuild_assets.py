#!/usr/bin/env python3
"""
批量预制世界模板图像素材（欧式卡通/绘本风）。

用法（在 backend 目录下）:
  python scripts/prebuild_assets.py
  python scripts/prebuild_assets.py --template missing_merchant_medieval
  python scripts/prebuild_assets.py --template all --force

环境变量:
  ENABLE_AI_IMAGES=true
  IMAGE_API_KEY 或 OPENAI_API_KEY
  ASSET_GENERATION_MODEL=dall-e-3  （默认）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")


async def _run(template_id: str, force: bool) -> dict[str, int]:
    from engine.image_assets import ensure_image_dirs, ensure_placeholder_file, ensure_template_assets, is_ai_images_enabled
    from engine.world_templates import GLOBAL_STYLE_GUARDRAIL, list_templates
    from storage.db import init_db

    if not is_ai_images_enabled():
        print("ENABLE_AI_IMAGES 未启用，跳过生成。")
        return {"total": 0, "completed": 0, "skipped": 0, "failed": 0}

    ensure_image_dirs()
    ensure_placeholder_file()
    await init_db()

    print(f"画风护栏: {GLOBAL_STYLE_GUARDRAIL[:80]}...")
    print(f"模板: {template_id}  force={force}\n")

    stats = await ensure_template_assets(
        template_id,
        force=force,
        include_player_from_state=True,
    )
    return stats


async def main() -> int:
    from engine.world_templates import list_templates

    parser = argparse.ArgumentParser(description="批量预制模板图像（storybook 卡通绘本风）")
    parser.add_argument(
        "--template",
        default="all",
        help="模板 id，或 all（默认全部）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新生成（删除已有哈希文件后重绘）",
    )
    args = parser.parse_args()

    ids = [t["id"] for t in list_templates()]
    if args.template != "all":
        if args.template not in ids:
            print(f"未知模板: {args.template}，可选: {', '.join(ids)}")
            return 1
        target_ids = [args.template]
    else:
        target_ids = ids

    total_stats = {"total": 0, "completed": 0, "skipped": 0, "failed": 0}
    for tid in target_ids:
        print("=" * 60)
        stats = await _run(tid, args.force)
        for k in total_stats:
            total_stats[k] += stats.get(k, 0)
        print(f"完成 {tid}: {stats}\n")

    print("=" * 60)
    print("合计:", total_stats)
    print(f"图片目录: {BACKEND_ROOT / 'storage' / 'images'}")
    if total_stats["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

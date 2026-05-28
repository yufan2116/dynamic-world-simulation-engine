"""按模板动态生成图像、MD5 永久缓存、同步 URL 查询。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from engine.llm_config import get_image_api_key, get_image_base_url, get_image_model
from storage import db

logger = logging.getLogger(__name__)

IMAGE_ROOT = Path(__file__).resolve().parent.parent / "storage" / "images"
PLACEHOLDER_URL = "/static/images/placeholder.png"
_CONCURRENCY = int(os.getenv("IMAGE_GENERATION_CONCURRENCY", "3"))


def _generation_model() -> str:
    return os.getenv("ASSET_GENERATION_MODEL") or get_image_model()


def _pick_image_size(model: str, asset_type: str) -> str:
    """gpt-image 系列不支持 1792x1024，宽幅用 1536x1024。"""
    if model.startswith("gpt-image"):
        return "1536x1024" if asset_type in ("background", "scene") else "1024x1024"
    return "1792x1024" if asset_type in ("background", "scene") else "1024x1024"

_URL_CACHE: dict[str, str] = {}
_gen_semaphore: asyncio.Semaphore | None = None


def is_ai_images_enabled() -> bool:
    return os.getenv("ENABLE_AI_IMAGES", "true").strip().lower() in ("1", "true", "yes")


def ensure_image_dirs() -> None:
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_placeholder_file() -> None:
    ensure_image_dirs()
    path = IMAGE_ROOT / "placeholder.png"
    if path.is_file():
        return
    # 最小 PNG
    path.write_bytes(
        bytes(
            [
                0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
                0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
                0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE, 0x00, 0x00, 0x00,
                0x0C, 0x49, 0x44, 0x41, 0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
                0x00, 0x03, 0x01, 0x01, 0x00, 0x18, 0xDD, 0x8D, 0xB4, 0x00, 0x00, 0x00,
                0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
            ]
        )
    )


def hash_prompt(prompt: str) -> str:
    return hashlib.md5(prompt.strip().encode("utf-8")).hexdigest()


def file_path_for_hash(prompt_hash: str) -> Path:
    return IMAGE_ROOT / f"{prompt_hash}.png"


def public_url_for_hash(prompt_hash: str) -> str:
    return f"/static/images/{prompt_hash}.png"


def placeholder_url() -> str:
    return PLACEHOLDER_URL


def get_image_url(prompt_hash: str | None) -> str | None:
    """同步：若本地/内存缓存存在则返回 URL，否则 None。"""
    if not prompt_hash:
        return None
    if prompt_hash in _URL_CACHE:
        return _URL_CACHE[prompt_hash]
    path = file_path_for_hash(prompt_hash)
    if path.is_file():
        url = public_url_for_hash(prompt_hash)
        _URL_CACHE[prompt_hash] = url
        return url
    return None


def cache_url(prompt_hash: str, url: str) -> None:
    _URL_CACHE[prompt_hash] = url


async def warm_url_cache_from_db() -> None:
    rows = await db.list_image_assets()
    for row in rows:
        h = row["prompt_hash"]
        path = file_path_for_hash(h)
        if path.is_file():
            cache_url(h, public_url_for_hash(h))


async def _download_url(temp_url: str, out_path: Path) -> None:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(temp_url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)


async def _call_dalle(prompt: str, asset_type: str) -> Path | None:
    if not is_ai_images_enabled():
        return None
    api_key = get_image_api_key()
    if not api_key:
        logger.warning("未配置图像 API Key，跳过生成")
        return None

    model = _generation_model()
    size = _pick_image_size(model, asset_type)
    base_url = get_image_base_url()

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "prompt": prompt[:3900],
                    "n": 1,
                    "size": size,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            if not items:
                return None
            item = items[0]
            temp_url = item.get("url")
            b64_json = item.get("b64_json")
            prompt_hash = hash_prompt(prompt)
            out_path = file_path_for_hash(prompt_hash)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if temp_url and str(temp_url).startswith("http"):
                await _download_url(str(temp_url), out_path)
                return out_path
            if b64_json:
                out_path.write_bytes(base64.b64decode(b64_json))
                return out_path
    except httpx.HTTPStatusError as e:
        logger.error(
            "图像 API 错误 model=%s size=%s: %s",
            model,
            size,
            e.response.text[:500] if e.response else e,
        )
    except Exception as e:
        logger.error("图像生成异常: %s", e)
    return None


def _get_semaphore() -> asyncio.Semaphore:
    global _gen_semaphore
    if _gen_semaphore is None:
        _gen_semaphore = asyncio.Semaphore(_CONCURRENCY)
    return _gen_semaphore


def clear_cached_image(prompt_hash: str) -> None:
    """删除本地文件与内存缓存（用于 --force 重新生成）。"""
    _URL_CACHE.pop(prompt_hash, None)
    path = file_path_for_hash(prompt_hash)
    if path.is_file():
        path.unlink()


async def get_or_generate(
    prompt: str,
    asset_type: str,
    *,
    on_ready: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    entity_id: str | None = None,
    force: bool = False,
) -> tuple[str, str]:
    """
    返回 (prompt_hash, public_url)。
    有缓存则立即返回；否则生成（受 ENABLE_AI_IMAGES 控制），失败则占位图。
    """
    prompt_hash = hash_prompt(prompt)
    if force:
        clear_cached_image(prompt_hash)

    existing = get_image_url(prompt_hash)
    if existing and not force:
        return prompt_hash, existing

    async with _get_semaphore():
        if force:
            clear_cached_image(prompt_hash)
        existing = get_image_url(prompt_hash)
        if existing and not force:
            return prompt_hash, existing

        try:
            path = await _call_dalle(prompt, asset_type)
            if path and path.is_file():
                url = public_url_for_hash(prompt_hash)
                cache_url(prompt_hash, url)
                await db.save_image_asset(
                    prompt_hash, prompt, asset_type, f"images/{prompt_hash}.png"
                )
                if on_ready and entity_id:
                    await on_ready(
                        {
                            "entity_id": entity_id,
                            "url": url,
                            "prompt_hash": prompt_hash,
                        }
                    )
                return prompt_hash, url
        except Exception as e:
            logger.error("图像生成失败 hash=%s: %s", prompt_hash, e)

    return prompt_hash, placeholder_url()


async def ensure_template_assets(
    template_id: str,
    *,
    state: Any | None = None,
    on_ready: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    extra_prompts: list[tuple[str, str, str, str]] | None = None,
    force: bool = False,
    include_player_from_state: bool = True,
) -> dict[str, int]:
    """
    遍历模板 NPC/地点提示词并 get_or_generate。
    extra_prompts: [(entity_id, prompt, asset_type, name), ...]
    返回统计 completed / skipped / failed / total。
    """
    from engine.world_templates import (
        build_image_entity_registry,
        create_initial_game_state,
        get_template,
    )

    tpl = get_template(template_id)
    jobs: list[tuple[str, str, str]] = []

    if include_player_from_state:
        src_state = state if state is not None else create_initial_game_state(template_id)
        registry = build_image_entity_registry(template_id, src_state)
        for eid, ent in registry.items():
            jobs.append((eid, ent["prompt"], ent["type"]))
    else:
        for npc in tpl.get("npcs", []):
            from engine.world_templates import build_portrait_prompt

            eid = npc.get("entity_id") or f"npc:{npc['name']}"
            prompt = build_portrait_prompt(npc, tpl["art_style"])
            jobs.append((eid, prompt, "portrait"))

        for loc in tpl.get("locations", []):
            from engine.world_templates import build_background_prompt

            eid = loc.get("entity_id") or f"loc:{loc['name']}"
            prompt = build_background_prompt(loc, tpl["art_style"])
            jobs.append((eid, prompt, "background"))

    if extra_prompts:
        for eid, prompt, atype, _name in extra_prompts:
            jobs.append((eid, prompt, atype))

    total = len(jobs)
    completed = 0
    skipped = 0
    failed = 0

    async def _notify_progress() -> None:
        if on_ready:
            await on_ready(
                {
                    "type": "progress",
                    "completed": completed + skipped,
                    "total": total,
                    "failed": failed,
                }
            )

    await _notify_progress()

    for eid, prompt, atype in jobs:
        ph = hash_prompt(prompt)
        if not force and get_image_url(ph):
            skipped += 1
            if on_ready:
                url = get_image_url(ph) or placeholder_url()
                await on_ready(
                    {
                        "entity_id": eid,
                        "url": url,
                        "prompt_hash": ph,
                    }
                )
            await _notify_progress()
            continue

        _ph, url = await get_or_generate(
            prompt, atype, on_ready=on_ready, entity_id=eid, force=force
        )
        if url != placeholder_url():
            completed += 1
        else:
            failed += 1
        await _notify_progress()

    return {
        "total": total,
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
    }


def collect_template_jobs(template_id: str, state: Any | None = None) -> list[tuple[str, str, str]]:
    """从模板 + 可选游戏状态收集全部 (entity_id, prompt, type)。"""
    from engine.world_templates import (
        build_image_entity_registry,
        get_template,
    )

    if state is not None:
        registry = build_image_entity_registry(template_id, state)
        return [
            (eid, ent["prompt"], ent["type"])
            for eid, ent in registry.items()
        ]

    tpl = get_template(template_id)
    jobs: list[tuple[str, str, str]] = []
    for npc in tpl.get("npcs", []):
        from engine.world_templates import build_portrait_prompt

        eid = npc.get("entity_id") or f"npc:{npc['name']}"
        jobs.append((eid, build_portrait_prompt(npc, tpl["art_style"]), "portrait"))
    for loc in tpl.get("locations", []):
        from engine.world_templates import build_background_prompt

        eid = loc.get("entity_id") or f"loc:{loc['name']}"
        jobs.append((eid, build_background_prompt(loc, tpl["art_style"]), "background"))
    return jobs

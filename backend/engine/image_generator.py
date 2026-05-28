"""图像生成 — 兼容 OpenAI Images API（/v1/images/generations）。"""
from __future__ import annotations

import hashlib
import os
import base64
from pathlib import Path
from typing import Literal

import httpx

from engine.llm_config import get_image_api_key, get_image_base_url, get_image_model
from engine.world_templates import finalize_image_prompt, get_art_style
from storage import db

ImageKind = Literal["portrait", "background", "npc"]

class ImageGenerationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


# 本地静态资源目录：backend/storage/images/
IMAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"
IMAGE_DIR = IMAGE_ROOT / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(kind: ImageKind, identifier: str, style: str) -> str:
    raw = f"{kind}|{identifier}|{style}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:20]
    return f"{kind}:{digest}"


def _finalize_prompt(prompt: str, style: str | None) -> str:
    """追加模板画风 + 全局绘本风护栏。"""
    base = prompt.strip().rstrip(".")
    art = get_art_style(style if style and len(style) > 20 else None)
    return finalize_image_prompt(f"{base}, {art}")


def _local_image_path(cache_key: str) -> Path:
    """根据缓存键生成稳定文件名（避免在 Windows 使用冒号等非法字符）。"""
    file_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
    return IMAGE_DIR / f"{file_hash}.png"


async def _call_openai_images(
    prompt: str,
    *,
    size: str = "1024x1024",
) -> dict[str, str | None]:
    """调用 OpenAI Image API（/v1/images/generations），返回 {url, b64_json}。"""
    api_key = get_image_api_key()
    if not api_key:
        raise ImageGenerationError("未配置 IMAGE_API_KEY（需要可用的 OpenAI 图像 Key）", status_code=503)
    base_url = get_image_base_url()
    model = get_image_model()
    full_prompt = prompt if len(prompt) <= 3900 else prompt[:3900]

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "n": 1,
                    "size": size,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            if not items:
                raise ImageGenerationError("图像服务未返回 data（可能是上游错误）", status_code=503)
            item = items[0]
            # dall-e 系列通常返回 url；gpt-image 系列通常返回 b64_json
            return {"url": item.get("url"), "b64_json": item.get("b64_json")}
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        # 尽量把上游错误信息透出，便于排查（额度不足/Key 无效/区域网络问题等）
        text = ""
        try:
            text = e.response.text
        except Exception:
            text = ""
        if status in (401, 403):
            raise ImageGenerationError(f"图像服务鉴权失败（{status}）：请检查 IMAGE_API_KEY 是否有效。{text}", status_code=status)
        if status == 429:
            raise ImageGenerationError(f"图像服务被限流/额度不足（429）：{text}", status_code=429)
        raise ImageGenerationError(f"图像服务返回错误（{status}）：{text}", status_code=503)
    except httpx.RequestError as e:
        raise ImageGenerationError(f"连接图像服务失败：{e}", status_code=503)


async def _download_to_local(temp_url: str, cache_key: str) -> str | None:
    """
    从临时 URL 下载图像到本地 storage/images，并返回对应的本地静态 URL。

    返回示例："/static/images/xxxxxxxx.png"
    """
    path = _local_image_path(cache_key)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(temp_url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
    except Exception:
        return None

    # FastAPI 中通过 app.mount("/static", StaticFiles(directory="storage"), ...) 暴露
    return f"/static/images/{path.name}"


async def generate_portrait(
    description: str,
    style: str | None = None,
    *,
    use_cache: bool = True,
    cache_identifier: str | None = None,
) -> dict[str, str | None]:
    """生成角色肖像。返回 { url, cache_key, cached }。"""
    style = style or os.getenv("IMAGE_STYLE", "medieval fantasy")
    ident = cache_identifier or description[:80]
    key = _cache_key("portrait", ident, style)

    if use_cache:
        cached = await db.get_cached_image(key)
        if cached:
            return {"url": cached, "cache_key": key, "cached": True}

    prompt = _finalize_prompt(
        f"Character portrait bust, fantasy RPG hero: {description}",
        style,
    )
    img = await _call_openai_images(prompt, size="1024x1024")
    temp_url = img.get("url")
    if temp_url and temp_url.startswith("http"):
        local_url = await _download_to_local(temp_url, key)
        final_url = local_url or temp_url
        await db.save_cached_image(key, "portrait", final_url, prompt, style)
        return {"url": final_url, "cache_key": key, "cached": False}

    b64_json = img.get("b64_json")
    if b64_json:
        try:
            path = _local_image_path(key)
            path.write_bytes(base64.b64decode(b64_json))
            local_url = f"/static/images/{path.name}"
            await db.save_cached_image(key, "portrait", local_url, prompt, style)
            return {"url": local_url, "cache_key": key, "cached": False}
        except Exception as e:
            raise ImageGenerationError(f"图像解码/落盘失败：{e}", status_code=503) from e
    return {"url": None, "cache_key": key, "cached": False}


async def generate_background(
    location_description: str,
    style: str | None = None,
    *,
    location_key: str | None = None,
    use_cache: bool = True,
) -> dict[str, str | None]:
    """生成场景背景（宽幅）。"""
    style = style or os.getenv("IMAGE_STYLE", "medieval fantasy")
    ident = location_key or location_description[:80]
    key = _cache_key("background", ident, style)

    if use_cache:
        cached = await db.get_cached_image(key)
        if cached:
            return {"url": cached, "cache_key": key, "cached": True}

    prompt = _finalize_prompt(
        f"Wide cinematic environment background for fantasy RPG, no characters in foreground: "
        f"{location_description}",
        style,
    )
    img = await _call_openai_images(prompt, size="1792x1024")
    temp_url = img.get("url")
    if temp_url and temp_url.startswith("http"):
        local_url = await _download_to_local(temp_url, key)
        final_url = local_url or temp_url
        await db.save_cached_image(key, "background", final_url, prompt, style)
        return {"url": final_url, "cache_key": key, "cached": False}

    b64_json = img.get("b64_json")
    if b64_json:
        try:
            path = _local_image_path(key)
            path.write_bytes(base64.b64decode(b64_json))
            local_url = f"/static/images/{path.name}"
            await db.save_cached_image(key, "background", local_url, prompt, style)
            return {"url": local_url, "cache_key": key, "cached": False}
        except Exception as e:
            raise ImageGenerationError(f"图像解码/落盘失败：{e}", status_code=503) from e
    return {"url": None, "cache_key": key, "cached": False}


async def generate_npc_portrait(
    npc_name: str,
    visual_hint: str,
    style: str | None = None,
    *,
    use_cache: bool = True,
) -> dict[str, str | None]:
    """生成 NPC 小头像。"""
    style = style or os.getenv("IMAGE_STYLE", "medieval fantasy")
    key = _cache_key("npc", npc_name, style)

    if use_cache:
        cached = await db.get_cached_image(key)
        if cached:
            return {"url": cached, "cache_key": key, "cached": True}

    prompt = _finalize_prompt(
        f"NPC portrait avatar, fantasy RPG character {npc_name}: {visual_hint}",
        style,
    )
    img = await _call_openai_images(prompt, size="1024x1024")
    temp_url = img.get("url")
    if temp_url and temp_url.startswith("http"):
        local_url = await _download_to_local(temp_url, key)
        final_url = local_url or temp_url
        await db.save_cached_image(key, "npc", final_url, prompt, style)
        return {"url": final_url, "cache_key": key, "cached": False}

    b64_json = img.get("b64_json")
    if b64_json:
        try:
            path = _local_image_path(key)
            path.write_bytes(base64.b64decode(b64_json))
            local_url = f"/static/images/{path.name}"
            await db.save_cached_image(key, "npc", local_url, prompt, style)
            return {"url": local_url, "cache_key": key, "cached": False}
        except Exception as e:
            raise ImageGenerationError(f"图像解码/落盘失败：{e}", status_code=503) from e
    return {"url": None, "cache_key": key, "cached": False}

"""LLM / 图像 API 环境变量（兼容 DeepSeek OpenAI 格式）。"""
from __future__ import annotations

import os


def _normalize_api_key(key: str | None) -> str | None:
    if not key:
        return None
    key = key.strip()
    # 常见误填：sk-sk-xxx
    if key.startswith("sk-sk-"):
        key = "sk-" + key[6:]
    return key or None


def get_llm_api_key() -> str | None:
    """叙事、意图解析：优先 DEEPSEEK_API_KEY，其次 OPENAI_API_KEY。"""
    return _normalize_api_key(
        os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    )


def get_llm_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com").rstrip("/")


def get_llm_model() -> str:
    return os.getenv("MODEL_NAME", "deepseek-v4-flash")


def get_image_api_key() -> str | None:
    """图像生成：仅使用 IMAGE_API_KEY 或 OPENAI_API_KEY（DeepSeek 不支持绘图）。"""
    return _normalize_api_key(
        os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
    )


def get_image_base_url() -> str:
    return os.getenv("IMAGE_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def get_image_model() -> str:
    return os.getenv("IMAGE_MODEL", "dall-e-3")


def is_llm_configured() -> bool:
    return bool(get_llm_api_key())


def is_image_configured() -> bool:
    key = get_image_api_key()
    if not key:
        return False
    # DeepSeek Key 不能用于 OpenAI 图像接口
    base = get_image_base_url()
    if "deepseek" in base.lower():
        return False
    return True

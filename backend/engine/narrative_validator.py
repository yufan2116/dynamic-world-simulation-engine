"""Narrative Validator — 叙事输出安全回退。"""

from __future__ import annotations

import re
from typing import Any

from engine.text_sanitizer import (
    FORBIDDEN_SUBSTRINGS,
    SAFE_FALLBACK,
    contains_forbidden,
    is_truncated,
    sanitize_player_text,
)
from engine.world_state import GameState

PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    "TODO",
    "FIXME",
    "{{",
    "}}",
    "placeholder",
    "TBD",
    "…",
)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def validate_narrative(
    narrative_html: str,
    state: GameState,
    *,
    intent: dict[str, Any] | None = None,
    allowed_locations: set[str] | None = None,
) -> tuple[str, bool]:
    """返回 (safe_narrative, passed)。不合格时使用 safe fallback。"""
    plain = _strip_html(narrative_html).strip()
    if not plain:
        return _wrap_fallback(SAFE_FALLBACK), False

    if contains_forbidden(plain):
        return _wrap_fallback(SAFE_FALLBACK), False

    for p in PLACEHOLDER_PATTERNS:
        if p.lower() in plain.lower():
            return _wrap_fallback(SAFE_FALLBACK), False

    if is_truncated(plain[-80:] if len(plain) > 80 else plain):
        return _wrap_fallback(SAFE_FALLBACK), False

    cleaned = sanitize_player_text(plain, state)
    if not cleaned:
        return _wrap_fallback(SAFE_FALLBACK), False

    if allowed_locations:
        for loc in allowed_locations:
            if loc and len(loc) >= 2 and loc in plain and loc not in allowed_locations:
                return _wrap_fallback(SAFE_FALLBACK), False

    target = (intent or {}).get("target")
    if target and isinstance(target, str):
        # 叙事完全偏离行动目标（简单启发）
        if target not in ("environment", "hidden_details", "overheard_group") and target not in plain:
            if len(plain) < 40:
                return _wrap_fallback(SAFE_FALLBACK), False

    for term in FORBIDDEN_SUBSTRINGS:
        if term in plain:
            return _wrap_fallback(SAFE_FALLBACK), False

    return narrative_html, True


def _wrap_fallback(text: str) -> str:
    safe = sanitize_player_text(text) or SAFE_FALLBACK
    return f'<p class="narrative-fallback">{safe}</p>'

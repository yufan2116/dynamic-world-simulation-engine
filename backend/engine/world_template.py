"""向后兼容 — 委托至 world_templates。"""
from __future__ import annotations

from typing import Any

from engine.world_templates import (
    DEFAULT_TEMPLATE_ID,
    get_art_style,
    get_template,
    list_templates,
)


def load_world_template(template_id: str | None = None) -> dict[str, Any]:
    return get_template(template_id or DEFAULT_TEMPLATE_ID)


def get_style_description(style: str | None = None, template_id: str | None = None) -> str:
    if template_id:
        return get_art_style(template_id)
    if style and style in _template_ids():
        return get_art_style(style)
    return get_art_style(None)


def _template_ids() -> set[str]:
    return {t["id"] for t in list_templates()}


def get_default_style() -> str:
    return DEFAULT_TEMPLATE_ID


def get_location_description(location: str, template_id: str | None = None) -> str:
    tpl = get_template(template_id)
    for loc in tpl.get("locations", []):
        if loc.get("name") == location:
            return loc.get("description", location)
    return f"fantasy RPG location: {location}"


def get_npc_visual_hint(npc_name: str, template_id: str | None = None) -> str:
    tpl = get_template(template_id)
    for npc in tpl.get("npcs", []):
        if npc.get("name") == npc_name:
            return npc.get("description", npc_name)
    return f"fantasy NPC named {npc_name}, portrait bust"

"""结构化开场叙事 — 从模板 narrative_style 渲染，非硬编码分支。"""
from __future__ import annotations

from engine.world_state import GameState
from engine.world_template_manager import (
    DEFAULT_TEMPLATE_ID,
    get_narrative_style,
    get_template_manifest,
    resolve_template_id,
)


def _equipment_str(state: GameState) -> str:
    return "、".join(state.player.equipment)


def _fill_template(html: str, state: GameState, chapter_title: str) -> str:
    p = state.player
    return (
        html.replace("{player_name}", p.name)
        .replace("{player_class}", p.class_name)
        .replace("{equipment}", _equipment_str(state))
        .replace("{chapter_title}", chapter_title)
    )


def get_opening_prologue(state: GameState, template_id: str | None = None) -> str:
    tid = resolve_template_id(template_id or state.flags.get("template_id"))
    style = get_narrative_style(tid)
    raw = style.get("prologue_html", "")
    tpl = get_template_manifest(tid)
    if not raw:
        return (
            f"<p class=\"chapter-epigraph\">序</p>"
            f"<p><strong>{state.player.name}</strong>抵达{tpl.get('name', '未知之地')}。</p>"
        )
    return _fill_template(raw, state, tpl.get("chapter_title", "第一章"))


def get_opening_narrative(state: GameState, template_id: str | None = None) -> str:
    tid = resolve_template_id(template_id or state.flags.get("template_id") or DEFAULT_TEMPLATE_ID)
    tpl = get_template_manifest(tid)
    style = get_narrative_style(tid)
    chapter = tpl.get("chapter_title", "第一章")
    raw = style.get("opening_html", "")
    if not raw:
        return (
            f"<p class=\"chapter-epigraph\">{chapter}</p>"
            f"<p>你站在<strong>{state.location}</strong>，四周景象已然清晰可触。</p>"
        )
    return _fill_template(raw, state, chapter)

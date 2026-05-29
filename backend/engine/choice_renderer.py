"""内嵌式选项渲染 — 将 available_actions 转为 CRPG 叙事续接选项。"""
from __future__ import annotations

import html
import json
import re
from typing import Any

from engine.action_generator import CATEGORIES
from engine.narrative_formatter import (
    format_choice_transition,
    format_inline_choices,
    format_narrative_html,
    humanize_action_label,
)
from engine.world_state import GameState

_SKILL_PREFIX: dict[str, str] = {
    "wis": "感知",
    "cha": "魅力",
    "dex": "敏捷",
    "str": "力量",
    "int": "智力",
    "con": "体质",
}

_TONE_FROM_CATEGORY: dict[str, str] = {
    "investigate": "investigative",
    "social": "social",
    "stealth": "stealthy",
    "survival": "practical",
    "free": "freeform",
}

_ENCOUNTER_TRANSITIONS: dict[str, str] = {
    "suspicious_guard": "托马斯没有继续说下去。空气里只剩下火把燃烧的噼啪声。",
    "guard_confession": "托马斯压低声音，目光仍扫向仓库方向。",
    "desperate_plea": "艾琳娜望着你，等你的回应。",
    "inn_gossip": "酒馆里的低语暂歇，等你开口。",
    "bandit_negotiation": "瓦里克打量着你，手指敲着刀柄。",
    "warehouse_probe": "仓库里一片安静，下一步由你决定。",
    "forest_trail": "林间风声盖住了远处的声响。",
    "bandit_confrontation": "对峙仍在继续——",
    "village_unrest": "村民们屏息看着这场交锋。",
    "sect_crisis": "云长老停下话语，等你表态。",
    "ambient_scene": "风吹过村口，火把在潮湿空气里轻轻摇晃。",
    "travel_transition": "路在前方延伸。",
    "rest_break": "短暂的歇息后，你打算——",
}


def choice_transition_line(encounter: dict[str, Any] | None) -> str:
    if not encounter:
        return "你打算——"
    et = encounter.get("encounter_type", "ambient_scene")
    return format_choice_transition(str(et)) or _ENCOUNTER_TRANSITIONS.get(et, "你打算——")


def _skill_bracket(tags: list[str]) -> str:
    for tag in tags:
        if tag in _SKILL_PREFIX:
            return f"[{_SKILL_PREFIX[tag]}] "
    if "perception" in tags:
        return "[感知] "
    return ""


def _narrative_choice_text(
    act: dict[str, Any],
    state: GameState,
    encounter: dict[str, Any] | None,
) -> str:
    """把系统 label 润色为扮演式选项文案（优先已有 narrative label）。"""
    intent = act.get("intent") if isinstance(act.get("intent"), dict) else {}
    label = humanize_action_label(
        (act.get("label") or act.get("input") or "").strip(),
        state=state,
        source_fact=str(act.get("source_fact") or ""),
        category=str(act.get("category") or ""),
        target=str(intent.get("target") or ""),
    )
    if label.startswith("[") and re.search(r"[\u4e00-\u9fff]", label):
        return label

    tags = act.get("tags") or []
    prefix = _skill_bracket(tags)
    cat = act.get("category", "investigate")

    if cat == "stealth" and "偷听" in label:
        label = label.replace("偷听守卫谈话", "趁守卫转身，偷听他们的低声交谈")
    elif cat == "investigate" and state.location == "仓库" and "翻查" in label:
        label = "趁无人注意，检查货箱旁的泥脚印与破损木箱"

    if prefix and not label.startswith("["):
        return f"{prefix}{label}"
    return label or "[感知] 继续观察四周"


def _estimate_risk(act: dict[str, Any], encounter: dict[str, Any] | None) -> str:
    if not act.get("unlocked", True):
        return "blocked"
    base = (encounter or {}).get("risk", "medium")
    cat = act.get("category", "")
    if cat == "stealth" and base == "medium":
        return "medium"
    if cat == "social" and (encounter or {}).get("encounter_type") == "suspicious_guard":
        return "medium"
    if cat == "investigate":
        return "low" if base == "low" else "medium"
    return base if base in ("low", "medium", "high") else "medium"


def _score_action(act: dict[str, Any], encounter: dict[str, Any] | None) -> int:
    if not act.get("unlocked", True):
        return -100
    score = 10
    cat = act.get("category", "")
    et = (encounter or {}).get("encounter_type", "")
    target = (encounter or {}).get("dialogue_target")
    aid = act.get("id", "")

    if cat == "social" and target and target in aid:
        score += 25
    if et == "suspicious_guard" and cat == "stealth":
        score += 15
    if et == "desperate_plea" and "艾琳娜" in aid:
        score += 20
    if et == "warehouse_probe" and cat == "investigate":
        score += 18
    if "opening" in (act.get("tags") or []):
        score += 30
    if "unlock" in (act.get("tags") or []):
        score += 5
    return score


def build_investigation_inline_choices(
    state: GameState,
    available_actions: dict[str, Any],
    *,
    encounter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """调查模式：固定 5 条行动全部展示，已完成/未解锁项置灰并注明原因。"""
    grouped = available_actions.get("grouped") or {}
    order = ("social", "investigate", "survival", "stealth")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for cat in order:
        for act in grouped.get(cat, []) or []:
            if not isinstance(act, dict):
                continue
            aid = str(act.get("id") or "")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            unlocked = bool(act.get("unlocked", True))
            lock_reason = act.get("lock_reason")
            if not unlocked and lock_reason == "已调查过":
                continue
            gameplay = act.get("gameplay") if isinstance(act.get("gameplay"), dict) else None
            out.append({
                "id": aid,
                "text": _narrative_choice_text(act, state, encounter),
                "input": act.get("input", "") or act.get("label", ""),
                "intent_payload": act.get("intent") if isinstance(act.get("intent"), dict) else {},
                "tone": _TONE_FROM_CATEGORY.get(act.get("category", ""), "neutral"),
                "risk": _estimate_risk(act, encounter),
                "category": act.get("category"),
                "gameplay": gameplay,
                "disabled": not unlocked,
                "lock_reason": lock_reason if not unlocked else None,
            })
    return out


def build_inline_choices(
    state: GameState,
    encounter: dict[str, Any] | None,
    scene_graph: dict[str, Any] | None,
    available_actions: dict[str, Any],
    *,
    max_choices: int = 5,
) -> list[dict[str, Any]]:
    """
    输入 scene_graph / encounter / available_actions，输出叙事化选项列表。
    """
    _ = scene_graph
    candidates: list[dict[str, Any]] = []
    grouped = available_actions.get("grouped") or {}

    for cat in CATEGORIES:
        if cat == "free":
            continue
        for act in grouped.get(cat, []):
            if not isinstance(act, dict):
                continue
            if not act.get("unlocked", True):
                continue
            inp = act.get("input") or ""
            if not inp:
                continue
            candidates.append(act)

    candidates.sort(key=lambda a: _score_action(a, encounter), reverse=True)
    picked = candidates[:max_choices]

    out: list[dict[str, Any]] = []
    for act in picked:
        gameplay = act.get("gameplay") if isinstance(act.get("gameplay"), dict) else None
        out.append({
            "id": act.get("id", ""),
            "text": _narrative_choice_text(act, state, encounter),
            "input": act.get("input", ""),
            "intent_payload": act.get("intent") if isinstance(act.get("intent"), dict) else {},
            "source": act.get("source") if isinstance(act.get("source"), dict) else None,
            "source_hint": "",
            "tone": _TONE_FROM_CATEGORY.get(act.get("category", ""), "neutral"),
            "risk": _estimate_risk(act, encounter),
            "category": act.get("category"),
            "gameplay": gameplay,
        })

    out.append({
        "id": "free_input",
        "text": "用你自己的话描述下一步……",
        "input": "",
        "tone": "freeform",
        "risk": "low",
        "category": "free",
        "is_free": True,
    })
    return out


def format_choices_html(
    choices: list[dict[str, Any]],
    *,
    transition: str = "",
    prompt: str = "你现在可以：",
) -> str:
    """生成嵌入叙事流的选项 HTML（含 data-input 供前端解析）。"""
    if not choices:
        return ""

    parts: list[str] = ['<div class="choice-block">']
    if transition:
        parts.append(f'<p class="choice-transition">{html.escape(transition)}</p>')
    parts.append(f'<p class="choice-prompt">{html.escape(prompt)}</p>')
    parts.append('<ol class="choice-list">')

    for i, ch in enumerate(choices, start=1):
        if ch.get("is_free"):
            parts.append(
                f'<li class="choice-item choice-free" data-choice-id="{html.escape(ch["id"])}" '
                f'data-free="true">'
                f'<span class="choice-index">{i}.</span> '
                f'<span class="choice-text">{html.escape(ch["text"])}</span></li>'
            )
        else:
            inp = html.escape(ch.get("input", ""), quote=True)
            intent_payload = ""
            if isinstance(ch.get("intent_payload"), dict):
                intent_payload = html.escape(json.dumps(ch["intent_payload"], ensure_ascii=False), quote=True)
            parts.append(
                f'<li class="choice-item" data-choice-id="{html.escape(ch["id"])}" '
                f'data-input="{inp}" data-intent="{intent_payload}">'
                f'<span class="choice-index">{i}.</span> '
                f'<span class="choice-text">{html.escape(ch["text"])}</span></li>'
            )

    parts.append("</ol></div>")
    return "\n".join(parts)


def package_narrative_choices(
    state: GameState,
    narrative_html: str,
    available_actions: dict[str, Any],
    *,
    encounter: dict[str, Any] | None = None,
    scene_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """打包叙事 + 内嵌选项（日志用完整 HTML，API 可拆分字段）。"""
    if encounter is None:
        from engine.encounter_state import build_encounter_state

        encounter = build_encounter_state(state, {}, {}, None)
    if scene_graph is None:
        from engine.scene_graph import build_scene_graph

        scene_graph = build_scene_graph(state, {}, {})

    transition = choice_transition_line(encounter)
    choices = build_inline_choices(state, encounter, scene_graph, available_actions)
    choices = format_inline_choices(choices, state)
    polished = format_narrative_html(narrative_html, state)
    choices_html = format_choices_html(choices, transition=transition)

    return {
        "narrative": polished,
        "narrative_with_choices": (polished.rstrip() + "\n" + choices_html).strip(),
        "choice_transition": transition,
        "inline_choices": choices,
    }

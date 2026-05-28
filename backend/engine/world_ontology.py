"""世界语义层 — 模板专属术语、UI 词汇、经济/危机/叙事语义。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from engine.world_state import GameState
from engine.world_template_manager import load_world_template, resolve_template_id

DEFAULT_TERMS: dict[str, Any] = {
    "core": {
        "currency": "钱币",
        "settlement": "聚落",
        "danger": "危险",
        "economy": "经济",
        "authority": "当局",
        "crisis": "危机",
        "tension": "紧张度",
    },
    "ui": {
        "world_panel_title": "世界态势",
        "world_pulse": "世界脉搏",
        "world_pulse_empty": "世界尚在沉睡……",
        "tension_meter": "社会紧张",
        "conflict_meter": "冲突风险",
        "crisis_block_title": "危机",
        "crisis_pressure": "危机压力",
        "suspicious_clues": "可疑线索",
        "current_quest": "当前任务",
        "search_window": "追查窗口",
        "event_categories": {
            "world": "世界",
            "rumor": "传闻",
            "npc": "人物",
            "system": "系统",
            "crisis": "危机",
            "economy": "经济",
            "faction": "派系",
        },
    },
    "economy": {"metrics": [], "events": []},
    "crisis": {
        "status_labels": {},
        "level_labels": {},
        "risk_notes": {},
        "tension_summary": "局势未明",
    },
    "clue_vocabulary": [],
    "rumor_auto": [],
}


@lru_cache(maxsize=8)
def load_world_terms(template_id: str) -> dict[str, Any]:
    tid = resolve_template_id(template_id)
    try:
        bundle = load_world_template(tid)
        terms = bundle.get("world_terms")
        if isinstance(terms, dict) and terms:
            return terms
    except (KeyError, FileNotFoundError):
        pass
    path_terms = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "data"
        / "world_templates"
        / tid
        / "world_terms.json"
    )
    if path_terms.is_file():
        import json

        with open(path_terms, encoding="utf-8") as f:
            return json.load(f)
    return {**DEFAULT_TERMS, "id": tid}


def get_ontology(template_id: str | None) -> dict[str, Any]:
    """完整语义包：terms + ui_theme 引用键。"""
    terms = load_world_terms(template_id or "")
    tid = resolve_template_id(template_id)
    return {"template_id": tid, "terms": terms, "core": terms.get("core", {}), "ui": terms.get("ui", {})}


def attach_ontology_to_state(state: GameState) -> dict[str, Any]:
    tid = resolve_template_id(state.flags.get("template_id"))
    onto = get_ontology(tid)
    state.flags["world_ontology"] = onto
    state.flags["template_id"] = tid
    return onto


def ontology_for_state(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("world_ontology")
    if isinstance(raw, dict) and raw.get("terms"):
        return raw
    return attach_ontology_to_state(state)


def ui_label(state: GameState, key: str, default: str = "") -> str:
    ui = ontology_for_state(state).get("ui") or {}
    return str(ui.get(key, default or key))


def core_term(state: GameState, key: str, default: str = "") -> str:
    core = ontology_for_state(state).get("core") or {}
    return str(core.get(key, default or key))


def crisis_labels(state: GameState) -> dict[str, Any]:
    terms = ontology_for_state(state).get("terms") or {}
    return terms.get("crisis") or {}


def economy_spec(state: GameState) -> dict[str, Any]:
    terms = ontology_for_state(state).get("terms") or {}
    return terms.get("economy") or {"metrics": [], "events": []}


def init_economy_from_ontology(state: GameState) -> dict[str, Any]:
    spec = economy_spec(state)
    eco: dict[str, Any] = {}
    for m in spec.get("metrics", []):
        if isinstance(m, dict) and m.get("key"):
            eco[str(m["key"])] = int(m.get("initial", 50))
    if not eco:
        eco = {"tavern_income": 100, "grain_price": 10}
    state.flags["economy"] = eco
    return eco


def tension_value(state: GameState) -> int:
    flags = state.flags
    tid = resolve_template_id(flags.get("template_id"))
    if tid == "xianxia_forbidden_land":
        return int(flags.get("tension", flags.get("spiritual_pollution", flags.get("village_panic", 40))))
    return int(flags.get("village_panic", 35))


def set_tension_value(state: GameState, value: int) -> None:
    v = max(0, min(100, int(value)))
    tid = resolve_template_id(state.flags.get("template_id"))
    if tid == "xianxia_forbidden_land":
        state.flags["tension"] = v
        state.flags["spiritual_pollution"] = v
    else:
        state.flags["village_panic"] = v


def format_economy_line(state: GameState) -> str | None:
    eco = state.flags.get("economy")
    if not isinstance(eco, dict):
        return None
    metrics = economy_spec(state).get("metrics", [])
    if not metrics:
        return None
    parts: list[str] = []
    for m in metrics[:2]:
        if not isinstance(m, dict):
            continue
        key = str(m.get("key", ""))
        label = str(m.get("label", key))
        if key in eco:
            parts.append(f"{label} {eco[key]}")
    return " · ".join(parts) if parts else None


def pick_clue(state: GameState) -> str:
    import random

    vocab = (ontology_for_state(state).get("terms") or {}).get("clue_vocabulary") or []
    if vocab:
        return random.choice(vocab)
    return "可疑痕迹"


def is_xianxia(state: GameState) -> bool:
    return resolve_template_id(state.flags.get("template_id")) == "xianxia_forbidden_land"


def resolve_role_label(state: GameState, role_key: str | None, npc_name: str | None = None) -> str:
    """将内部 role 键转为界面显示用中文称谓。"""
    if not role_key:
        return "路人"
    profiles = state.flags.get("npc_profiles")
    if npc_name and isinstance(profiles, dict):
        prof = profiles.get(npc_name)
        if isinstance(prof, dict) and prof.get("role_label"):
            return str(prof["role_label"])
    terms = ontology_for_state(state).get("terms") or {}
    labels = terms.get("role_labels") or {}
    if role_key in labels:
        return str(labels[role_key])
    if any("\u4e00" <= c <= "\u9fff" for c in role_key):
        return role_key
    return _ROLE_LABELS_FALLBACK.get(role_key, role_key.replace("_", " "))


_ROLE_LABELS_FALLBACK: dict[str, str] = {
    "guard": "村庄守卫",
    "innkeeper": "酒馆掌柜",
    "merchant daughter": "商人之女",
    "bandit leader": "强盗首领",
    "elder": "道长",
    "disciple": "宗门弟子",
    "sword_cultivator": "女剑修",
    "rogue_cultivator": "黑衣散修",
    "ancient_spirit": "古修残魂",
}

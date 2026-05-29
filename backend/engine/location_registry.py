"""地点注册表 — 所有方向/地点文案必须来自此处，禁止“某个方向”等占位符。"""

from __future__ import annotations

from typing import Any

from engine.world_state import GameState
from engine.world_template_manager import resolve_template_id

MEDIEVAL_REGISTRY: dict[str, str] = {
    "village_gate": "村口",
    "村口": "村口",
    "tavern": "酒馆",
    "酒馆": "酒馆",
    "old_warehouse": "旧仓库",
    "仓库": "旧仓库",
    "black_forest": "黑森林",
    "森林小路": "森林小路",
    "road_north": "北侧道路",
    "forest_path": "森林小路",
}

XIANXIA_REGISTRY: dict[str, str] = {
    "mountain_gate_ruins": "山门遗迹",
    "山门遗迹": "山门遗迹",
    "山门": "山门遗迹",
    "sword_forest": "断剑石林",
    "断剑石林": "断剑石林",
    "sealed_altar": "封印祭坛",
    "封印祭坛": "封印祭坛",
    "spirit_rift": "灵气裂隙",
    "灵气裂隙": "灵气裂隙",
    "藏经阁": "藏经阁",
    "禁地裂谷": "禁地裂谷",
}

# 未公开地点的对外表述（禁止“某个方向/某处/仓库方向”）
VAGUE_LOCATION_PHRASES: dict[str, str] = {
    "warehouse": "村口外侧",
    "仓库方向": "村口外侧",
    "old_warehouse": "村口外侧",
    "tavern": "酒馆门口",
    "black_forest": "村外小路方向",
    "forest": "村外林间",
}


def get_location_registry(state: GameState) -> dict[str, str]:
    tid = resolve_template_id(state.flags.get("template_id"))
    if "xianxia" in tid:
        return dict(XIANXIA_REGISTRY)
    return dict(MEDIEVAL_REGISTRY)


def is_location_public(state: GameState, loc_key_or_name: str) -> bool:
    """地点是否已对玩家公开（可在叙事/选项中直呼其名）。"""
    facts = state.flags.get("player_known_facts") or {}
    if not isinstance(facts, dict):
        return False
    known_locs = facts.get("known_locations") or []
    if not isinstance(known_locs, list):
        return False
    reg = get_location_registry(state)
    key = loc_key_or_name.strip()
    display = reg.get(key, key)
    return display in known_locs or key in known_locs


def resolve_location_display(state: GameState, loc_key_or_name: str) -> str:
    """解析为玩家可见地点名；未公开则返回安全表述。"""
    reg = get_location_registry(state)
    key = (loc_key_or_name or "").strip()
    if not key:
        return "当前地点"
    display = reg.get(key, reg.get(key.replace("方向", ""), key))
    if is_location_public(state, display):
        return display
    vague = VAGUE_LOCATION_PHRASES.get(key) or VAGUE_LOCATION_PHRASES.get(
        key.replace("方向", "")
    )
    if vague:
        return vague
    if "仓库" in key or display == "旧仓库":
        return VAGUE_LOCATION_PHRASES.get("warehouse", "村口外侧")
    return "村外一侧"


def resolve_direction_phrase(state: GameState, direction_key: str) -> str:
    """如 warehouse_direction → 若仓库未公开则“村口外侧”，否则“旧仓库方向”。"""
    dk = (direction_key or "").strip().lower()
    if not dk:
        return ""
    base = dk.replace("_direction", "").replace("方向", "")
    if base in ("warehouse", "old_warehouse", "warehouse"):
        if is_location_public(state, "旧仓库"):
            return "旧仓库方向"
        return VAGUE_LOCATION_PHRASES.get("warehouse", "村口外侧")
    if is_location_public(state, base):
        disp = resolve_location_display(state, base)
        return f"{disp}方向"
    return VAGUE_LOCATION_PHRASES.get(base, "村外一侧")

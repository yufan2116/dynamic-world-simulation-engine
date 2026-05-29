"""NPC State Model — Simulation Architecture V2."""

from __future__ import annotations

from typing import Any

from engine.world_state import GameState, NPCState

NAME_TO_ID: dict[str, str] = {
    "托马斯": "thomas",
    "艾琳娜": "elena",
    "米拉": "mira",
    "瓦里克": "varick",
}

ID_TO_NAME: dict[str, str] = {v: k for k, v in NAME_TO_ID.items()}

LOCATION_TO_SLOT: dict[str, str] = {
    "村口": "village_gate",
    "酒馆": "tavern",
    "仓库": "warehouse",
    "森林小路": "forest_trail",
}


def npc_id_from_name(name: str) -> str:
    n = str(name).strip()
    if n in NAME_TO_ID:
        return NAME_TO_ID[n]
    return n.lower().replace(" ", "_")


def npc_name_from_id(npc_id: str) -> str:
    return ID_TO_NAME.get(npc_id, npc_id)


def _default_profiles() -> dict[str, dict[str, Any]]:
    return {
        "thomas": {
            "id": "thomas",
            "name": "托马斯",
            "role": "村庄守卫",
            "location": "village_gate",
            "faction": "village_guard",
            "personality": ["警惕", "疲惫", "责任感强"],
            "goals": ["维持村口秩序", "避免村民恐慌"],
            "fears": ["失职被追责", "仓库事件暴露"],
            "current_emotion": "tense",
            "current_activity": "guarding_gate",
            "relationships": {
                "player": {"trust": 0, "suspicion": 20, "attitude": "neutral"}
            },
            "knowledge": [
                {
                    "id": "knows_extra_patrol",
                    "text": "今夜村口外侧会加派巡逻",
                    "visibility_to_player": "hidden",
                    "sensitivity": 30,
                    "topic_id": "extra_patrol",
                },
                {
                    "id": "knows_night_noise_outer",
                    "text": "昨夜村口外侧有短促撞击与脚步声",
                    "visibility_to_player": "hidden",
                    "sensitivity": 50,
                    "topic_id": "last_night_disturbance",
                },
            ],
            "secrets": [
                {
                    "id": "warehouse_sensitive_topic",
                    "text": "托马斯知道昨夜仓库方向有人影晃动",
                    "sensitivity": 70,
                    "topic_id": "last_night_disturbance",
                    "reveal_conditions": {
                        "trust_min": 30,
                        "suspicion_max": 45,
                        "dice_success": True,
                    },
                },
                {
                    "id": "patrol_reason_secret",
                    "text": "加派巡逻是因为队长怀疑走私货物被劫",
                    "sensitivity": 55,
                    "topic_id": "extra_patrol",
                    "reveal_conditions": {
                        "trust_min": 45,
                        "dice_success": True,
                    },
                },
            ],
        },
        "elena": {
            "id": "elena",
            "name": "艾琳娜",
            "role": "商人之女",
            "location": "village_gate",
            "faction": "villager",
            "personality": ["坚韧", "悲伤", "焦急"],
            "goals": ["找到父亲马库斯"],
            "fears": ["永远失去父亲"],
            "current_emotion": "distressed",
            "current_activity": "pleading_in_square",
            "relationships": {
                "player": {"trust": 25, "suspicion": 5, "attitude": "hopeful"}
            },
            "knowledge": [
                {
                    "id": "knows_father_warehouse",
                    "text": "父亲昨夜说去仓库清点货物",
                    "visibility_to_player": "public",
                    "sensitivity": 10,
                    "topic_id": "missing_father",
                },
            ],
            "secrets": [
                {
                    "id": "father_left_time",
                    "text": "父亲约在黄昏离开酒馆前往仓库",
                    "sensitivity": 20,
                    "topic_id": "missing_father",
                    "reveal_conditions": {"trust_min": 15},
                },
            ],
        },
        "mira": {
            "id": "mira",
            "name": "米拉",
            "role": "酒馆老板娘",
            "location": "tavern",
            "faction": "villager",
            "personality": ["务实", "善良", "忧虑"],
            "goals": ["维持酒馆生意", "帮助艾琳娜"],
            "fears": ["村庄衰落"],
            "current_emotion": "anxious",
            "current_activity": "watching_from_curtain",
            "relationships": {
                "player": {"trust": 15, "suspicion": 8, "attitude": "cautious"}
            },
            "knowledge": [
                {
                    "id": "saw_elena_plea",
                    "text": "米拉看见艾琳娜在广场求助时一直观察门外",
                    "visibility_to_player": "hidden",
                    "sensitivity": 25,
                    "topic_id": "missing_father",
                },
                {
                    "id": "heard_marcus_last_drink",
                    "text": "马库斯失踪前在酒馆喝过一杯",
                    "visibility_to_player": "hidden",
                    "sensitivity": 15,
                    "topic_id": "missing_father",
                },
            ],
            "secrets": [],
        },
    }


def ensure_npc_states(state: GameState) -> dict[str, dict[str, Any]]:
    """初始化/同步 flags.npc_states。"""
    raw = state.flags.get("npc_states")
    if not isinstance(raw, dict):
        raw = {}
    defaults = _default_profiles()
    for nid, prof in defaults.items():
        if nid not in raw:
            raw[nid] = _deep_copy_profile(prof)
    for name, npc in state.npcs.items():
        nid = npc_id_from_name(name)
        slot = LOCATION_TO_SLOT.get(npc.location, npc.location)
        entry = raw.get(nid)
        if not isinstance(entry, dict):
            entry = _deep_copy_profile(defaults.get(nid, {"id": nid, "name": name}))
            raw[nid] = entry
        entry["name"] = name
        entry["location"] = slot
        rel = entry.setdefault("relationships", {}).setdefault("player", {})
        if isinstance(rel, dict):
            av = int(npc.attitude_value)
            rel["trust"] = int(rel.get("trust", av))
            rel["suspicion"] = int(rel.get("suspicion", max(0, 20 - av // 2)))
            rel["attitude"] = _attitude_label(av)
        if npc.memories:
            entry.setdefault("memories", list(npc.memories))
    state.flags["npc_states"] = raw
    return raw


def _deep_copy_profile(prof: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(prof)


def _attitude_label(attitude_value: int) -> str:
    if attitude_value >= 30:
        return "friendly"
    if attitude_value <= -20:
        return "hostile"
    return "neutral"


def get_npc_state(state: GameState, npc_id_or_name: str) -> dict[str, Any] | None:
    states = ensure_npc_states(state)
    nid = npc_id_from_name(npc_id_or_name)
    if nid in states:
        return states[nid]
    if npc_id_or_name in states:
        return states[npc_id_or_name]
    return None


def get_player_relationship(npc: dict[str, Any]) -> dict[str, Any]:
    rel = (npc.get("relationships") or {}).get("player")
    if isinstance(rel, dict):
        return rel
    return {"trust": 0, "suspicion": 20, "attitude": "neutral"}


def apply_npc_state_changes(state: GameState, changes: list[dict[str, Any]]) -> None:
    states = ensure_npc_states(state)
    for ch in changes:
        if not isinstance(ch, dict):
            continue
        nid = str(ch.get("npc_id") or "")
        if not nid:
            continue
        npc = states.get(nid)
        if not isinstance(npc, dict):
            continue
        rel = npc.setdefault("relationships", {}).setdefault("player", {})
        if "trust_delta" in ch:
            rel["trust"] = int(rel.get("trust", 0)) + int(ch["trust_delta"])
        if "suspicion_delta" in ch:
            rel["suspicion"] = int(rel.get("suspicion", 0)) + int(ch["suspicion_delta"])
        if ch.get("emotion"):
            npc["current_emotion"] = str(ch["emotion"])
        if ch.get("activity"):
            npc["current_activity"] = str(ch["activity"])
        rel["trust"] = max(-100, min(100, int(rel.get("trust", 0))))
        rel["suspicion"] = max(0, min(100, int(rel.get("suspicion", 0))))
        # 同步到 legacy NPCState
        name = npc_name_from_id(nid)
        if name in state.npcs:
            state.npcs[name].attitude_value = int(rel["trust"])
            state.npcs[name].attitude = rel.get("attitude", "中立")


def npc_present_at_location(state: GameState, npc_id: str) -> bool:
    name = npc_name_from_id(npc_id)
    for n in state.npc_at_location():
        if n.name == name:
            return True
    return False


def visible_npc_entries(state: GameState, scene_graph: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """当前场景可见 NPC 的 npc_state 条目。"""
    states = ensure_npc_states(state)
    names = {n.name for n in state.npc_at_location()}
    if scene_graph:
        for vn in scene_graph.get("visible_npcs") or []:
            if isinstance(vn, dict) and vn.get("name"):
                names.add(str(vn["name"]))
    out: list[dict[str, Any]] = []
    for nid, data in states.items():
        if data.get("name") in names:
            out.append(data)
    return out

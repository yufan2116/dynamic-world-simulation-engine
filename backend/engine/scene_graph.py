"""场景图 — 从世界状态组装 CRPG 场景，供叙事层使用（禁止 LLM 编造新实体）。"""
from __future__ import annotations

from typing import Any

from engine.npc_ai import NPC_PROFILES, _ensure_profiles
from engine.npc_dialogue_tree import resolve_npc_dialogue_behavior
from engine.world_state import GameState, NPCState
from engine.world_ontology import crisis_labels, is_xianxia, tension_value
from engine.world_template_manager import get_scene_defaults, resolve_template_id
from engine.world_templates import (
    all_locations_for_state,
    get_template,
    location_connections_for_state,
)

_ROLE_LABELS: dict[str, str] = {
    "guard": "村庄守卫",
    "innkeeper": "酒馆老板娘",
    "merchant daughter": "商人之女",
    "bandit leader": "强盗首领",
    "elder": "道长",
    "disciple": "宗门弟子",
    "antagonist": "邪修",
    "sword_cultivator": "女剑修",
    "rogue_cultivator": "黑衣散修",
    "ancient_spirit": "古修残魂",
}

# 扩展人格描述（比 npc_ai 单行 personality 更利于稳定对白）
_PERSONALITY_DETAIL: dict[str, str] = {
    "托马斯": "警惕、疲惫、责任感强；说话短句、公事公办",
    "米拉": "务实善良；说话直接、带关切",
    "艾琳娜": "坚韧但悲伤；说话急促、带恳求",
    "瓦里克": "残忍狡诈；说话嘲弄、威胁",
    "云长老": "威严克制；说话简练、带训诫",
    "林师妹": "焦虑认真；说话快、易紧张",
    "血煞道人": "阴冷傲慢；说话慢、带讥讽",
}


def _template_npc_roles(state: GameState) -> dict[str, str]:
    from engine.world_ontology import resolve_role_label

    profiles = state.flags.get("npc_profiles")
    out: dict[str, str] = {}
    if isinstance(profiles, dict):
        for name, prof in profiles.items():
            if isinstance(prof, dict) and prof.get("role_label"):
                out[name] = str(prof["role_label"])
    tid = resolve_template_id(state.flags.get("template_id"))
    tpl = get_template(tid)
    for npc in tpl.get("npcs", []):
        name = npc["name"]
        if name in out:
            continue
        role_key = npc.get("role", "")
        out[name] = resolve_role_label(state, role_key, name)
    return out


def _location_meta(state: GameState) -> dict[str, Any]:
    tid = resolve_template_id(state.flags.get("template_id"))
    loc = state.location
    by_tpl = get_scene_defaults(tid)
    return by_tpl.get(loc, {
        "lighting": f"{state.time_of_day}天光",
        "soundscape": [state.weather, "环境杂音"],
        "interactive_objects": ["地面", "空气"],
        "player_position": f"{loc}中央",
        "npc_positions": {},
    })


def _infer_emotion(npc: NPCState, state: GameState, name: str) -> str:
    profiles = state.flags.get("npc_profiles")
    if isinstance(profiles, dict):
        prof = profiles.get(name, {})
        if isinstance(prof, dict) and prof.get("current_emotion"):
            return str(prof["current_emotion"])
    val = npc.attitude_value
    panic = int(state.flags.get("village_panic", state.flags.get("tension", 35)))
    if val <= -40:
        return "敌意"
    if val >= 40:
        return "信任"
    if name == "艾琳娜" and panic > 50:
        return "焦急"
    if name == "托马斯" and state.flags.get("warehouse_noise"):
        return "紧张"
    if name == "米拉" and panic > 45:
        return "忧虑"
    if name == "瓦里克":
        return "戒备"
    if npc.attitude in ("冷淡", "敌对"):
        return "警惕"
    return "平静"


def _infer_current_action(
    name: str,
    npc: NPCState,
    profile: dict[str, Any],
    state: GameState,
) -> str:
    seeded = state.flags.get("npc_current_actions")
    if isinstance(seeded, dict) and name in seeded:
        return str(seeded[name])
    if state.flags.get("guard_patrol_active") and name == "托马斯":
        return "召集同伴，强调仓库方向加派哨岗"
    if name == "艾琳娜" and int(state.flags.get("village_panic", 0)) > 45:
        return "向路人打听父亲下落"
    if name == "米拉" and state.flags.get("clue_found"):
        return "在吧台后低声与酒客交谈"
    if name == "托马斯" and state.location == "仓库":
        return "检查货箱与脚印"
    if name == "托马斯" and state.location == "村口":
        return "站在村口观察人群与进出者"
    if name == "瓦里克" and state.flags.get("varick_revealed"):
        return "在林间注视来访者"
    slot = state.time_of_day
    schedule: dict[str, str] = profile.get("schedule", {})
    if schedule.get(slot) == npc.location:
        goals = {
            "托马斯": "巡逻并留意异常",
            "米拉": "照看酒馆与客人",
            "艾琳娜": "等待父亲消息",
        }
        return goals.get(name, f"在{npc.location}处理日常事务")
    return f"在{npc.location}停留"


def _build_visible_npc(
    state: GameState,
    npc: NPCState,
    meta: dict[str, Any],
    roles: dict[str, str],
    intent: dict[str, Any],
    changes: dict[str, Any],
) -> dict[str, Any]:
    profiles = _ensure_profiles(state)
    profile = profiles.get(npc.name, NPC_PROFILES.get(npc.name, {}))
    positions: dict[str, str] = meta.get("npc_positions", {})
    personality = _PERSONALITY_DETAIL.get(
        npc.name,
        profile.get("personality", "中立"),
    )
    dialogue = resolve_npc_dialogue_behavior(state, npc, intent, changes)

    return {
        "name": npc.name,
        "role": roles.get(npc.name, profile.get("faction", "角色")),
        "personality": personality,
        "goal": profile.get("goal", ""),
        "fear": profile.get("fear", ""),
        "emotion": _infer_emotion(npc, state, npc.name),
        "attitude": npc.attitude,
        "attitude_to_player": npc.attitude,
        "current_action": _infer_current_action(npc.name, npc, profile, state),
        "position": positions.get(npc.name, f"{state.location}内"),
        "recent_memory": npc.memories[-3:] if npc.memories else [],
        "conversational_behavior": {
            "active_branch": dialogue["active_branch"],
            "behaviors": dialogue["behaviors"],
            "behavior_hints": dialogue["behavior_hints"],
            "is_dialogue_target": dialogue["is_dialogue_target"],
        },
    }


def _current_tension(state: GameState) -> str:
    tid = resolve_template_id(state.flags.get("template_id"))
    panic = int(state.flags.get("village_panic", state.flags.get("tension", 35)))
    danger = state.flags.get("danger_level", "中")
    if is_xianxia(state):
        crisis = state.flags.get("crisis") or {}
        pressure = float(crisis.get("pressure", 18)) if isinstance(crisis, dict) else 18.0
        base = crisis_labels(state).get("tension_summary", "葬仙渊结界不稳")
        parts = []
        if state.flags.get("clue_found"):
            parts.append("残留灵痕已确认")
        if state.flags.get("seal_inspected"):
            parts.append("封印阵纹遭触动")
        if tension_value(state) >= 55:
            parts.append("灵气污染加剧")
        if not parts:
            return f"{base}（异变压力 {pressure:.0f}）；危险：{danger}"
        return f"{base}；{'；'.join(parts)}"
    parts = []
    if state.flags.get("clue_found"):
        parts.append("失踪案线索已暴露")
    if state.flags.get("thomas_alerted"):
        parts.append("守卫对玩家高度警觉")
    if state.flags.get("warehouse_noise"):
        parts.append("仓库方向曾有异常声响")
    if panic >= 60:
        parts.append("村民恐慌上升")
    base = crisis_labels(state).get("tension_summary", "商人马库斯失踪，村庄不安")
    if not parts:
        return f"{base}；危险等级：{danger}"
    return f"{base}；{'；'.join(parts)}"


def build_scene_graph(
    state: GameState,
    intent: dict[str, Any],
    changes: dict[str, Any],
) -> dict[str, Any]:
    """从世界状态构建场景图；不引入状态中不存在的 NPC/地点。"""
    meta = _location_meta(state)
    roles = _template_npc_roles(state)
    visible = [
        _build_visible_npc(state, n, meta, roles, intent, changes)
        for n in state.npc_at_location()
    ]
    conns = location_connections_for_state(state)
    neighbors = conns.get(state.location, [])
    objects = list(meta.get("interactive_objects", []))
    for nb in neighbors:
        tag = f"通往{nb}的小路"
        if tag not in objects and nb in all_locations_for_state(state):
            objects.append(tag)

    clock = state.flags.get("clock", state.time_of_day)
    return {
        "location": state.location,
        "time": f"第{state.day}天 {clock}（{state.time_of_day}）",
        "weather": state.weather,
        "lighting": meta.get("lighting", ""),
        "soundscape": meta.get("soundscape", []),
        "visible_npcs": visible,
        "interactive_objects": objects,
        "current_tension": _current_tension(state),
        "player_position": meta.get("player_position", f"{state.location}内"),
        "player_action_summary": intent.get("raw_input") or intent.get("action_type", ""),
    }

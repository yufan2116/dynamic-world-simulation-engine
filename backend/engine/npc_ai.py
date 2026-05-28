"""NPC Utility AI — 目标驱动的自主行动（确定性）。"""
from __future__ import annotations

from typing import Any

from engine.npc_memory import add_memory, update_npc_from_action
from engine.world_state import GameState

# NPC 扩展档案（存于 flags.npc_profiles）
NPC_PROFILES: dict[str, dict[str, Any]] = {
    "托马斯": {
        "goal": "保护村庄、查明仓库异动",
        "personality": "谨慎忠诚",
        "fear": "失职被问责",
        "faction": "村庄守卫",
        "schedule": {"清晨": "村口", "正午": "仓库", "傍晚": "村口", "深夜": "村口"},
    },
    "米拉": {
        "goal": "维持酒馆生意、帮助艾琳娜",
        "personality": "务实善良",
        "fear": "村庄衰落",
        "faction": "村民",
        "schedule": {"清晨": "酒馆", "正午": "酒馆", "傍晚": "酒馆", "深夜": "酒馆"},
    },
    "艾琳娜": {
        "goal": "找到父亲马库斯",
        "personality": "坚韧悲伤",
        "fear": "永远失去父亲",
        "faction": "村民",
        "schedule": {"清晨": "酒馆", "正午": "村口", "傍晚": "酒馆", "深夜": "酒馆"},
    },
    "瓦里克": {
        "goal": "控制商路与走私货物",
        "personality": "残忍狡诈",
        "fear": "被王国骑兵围剿",
        "faction": "强盗",
        "schedule": {"清晨": "森林小路", "正午": "森林小路", "傍晚": "森林小路", "深夜": "森林小路"},
    },
    "云长老": {
        "goal": "维持宗门秩序、查明封印异动",
        "personality": "威严克制",
        "fear": "禁地彻底失控",
        "faction": "青云宗",
        "schedule": {"清晨": "山门", "正午": "山门", "傍晚": "藏经阁", "深夜": "山门"},
    },
    "林师妹": {
        "goal": "协助查探藏经阁封印",
        "personality": "焦虑认真",
        "fear": "同门遇险",
        "faction": "青云宗",
        "schedule": {"清晨": "藏经阁", "正午": "藏经阁", "傍晚": "藏经阁", "深夜": "山门"},
    },
    "血煞道人": {
        "goal": "破坏封印、夺取灵物",
        "personality": "阴冷傲慢",
        "fear": "宗门围剿",
        "faction": "邪修",
        "schedule": {"清晨": "禁地裂谷", "正午": "禁地裂谷", "傍晚": "禁地裂谷", "深夜": "禁地裂谷"},
    },
}


def _ensure_profiles(state: GameState) -> dict[str, dict[str, Any]]:
    stored = state.flags.get("npc_profiles")
    if not isinstance(stored, dict):
        stored = {}
    for name, profile in NPC_PROFILES.items():
        if name not in stored:
            stored[name] = profile.copy()
    state.flags["npc_profiles"] = stored
    return stored


def _utility_patrol(state: GameState, name: str) -> float:
    if name != "托马斯":
        return 0.0
    return 40.0 if state.flags.get("warehouse_noise") or state.flags.get("bandit_raid") else 15.0


def _utility_gossip(state: GameState, name: str) -> float:
    if name == "米拉":
        return 35.0 if int(state.flags.get("village_panic", 0)) > 40 else 20.0
    return 10.0 if name == "艾琳娜" else 0.0


def _utility_seek_help(state: GameState, name: str) -> float:
    if name != "艾琳娜":
        return 0.0
    crisis = state.flags.get("crisis")
    urgency = int(crisis.get("pressure", 20)) if isinstance(crisis, dict) else 20
    return 25.0 + urgency * 0.35


def _utility_ambush(state: GameState, name: str) -> float:
    if name != "瓦里克" or not state.flags.get("varick_revealed"):
        return 0.0
    return 50.0 if state.flags.get("clue_found") else 20.0


def _utility_follow_schedule(state: GameState, name: str, profile: dict[str, Any]) -> float:
    slot = state.time_of_day
    schedule: dict[str, str] = profile.get("schedule", {})
    target_loc = schedule.get(slot)
    if not target_loc:
        return 5.0
    npc = state.npcs.get(name)
    if npc and npc.location != target_loc:
        return 30.0
    return 5.0


def tick_npc_ai(state: GameState) -> list[dict[str, Any]]:
    """每个世界 Tick，NPC 选择并执行一项自主行动。"""
    events: list[dict[str, Any]] = []
    profiles = _ensure_profiles(state)

    for name, profile in profiles.items():
        if name not in state.npcs:
            continue
        npc = state.npcs[name]
        if not npc.present and name == "瓦里克" and not state.flags.get("varick_revealed"):
            continue

        actions = {
            "schedule": _utility_follow_schedule(state, name, profile),
            "patrol": _utility_patrol(state, name),
            "gossip": _utility_gossip(state, name),
            "seek_help": _utility_seek_help(state, name),
            "ambush": _utility_ambush(state, name),
        }
        best_action = max(actions, key=actions.get)
        score = actions[best_action]
        if score < 12:
            continue

        if best_action == "schedule":
            slot = state.time_of_day
            target = profile.get("schedule", {}).get(slot)
            if target and npc.location != target:
                old = npc.location
                npc.location = target
                add_memory(npc, f"{name}按日程从{old}前往{target}。")
                if name == "托马斯" and target == "仓库":
                    events.append({
                        "type": "npc_action",
                        "text": f"【NPC】托马斯率队前往仓库巡逻。",
                        "npc": name,
                    })
                elif name == "艾琳娜" and target == "村口":
                    events.append({
                        "type": "npc_action",
                        "text": "【NPC】艾琳娜在村口徘徊，向路人打听父亲下落。",
                        "npc": name,
                    })

        elif best_action == "patrol":
            state.flags["guard_patrol_active"] = True
            add_memory(npc, "托马斯加强了仓库方向的巡逻。")
            events.append({
                "type": "npc_action",
                "text": "【NPC】托马斯在村口召集同伴，强调今夜仓库方向加派哨岗。",
                "npc": name,
            })

        elif best_action == "gossip" and name == "米拉":
            from engine.rumor_network import add_rumor

            if state.flags.get("clue_found"):
                add_rumor(
                    state,
                    "米拉私下说：马库斯恐怕卷入了一笔不该碰的买卖。",
                    "酒馆",
                    known_by=["米拉"],
                )
            events.append({
                "type": "npc_action",
                "text": "【NPC】米拉在酒馆低声与酒客交谈，神色忧虑。",
                "npc": name,
            })

        elif best_action == "seek_help":
            update_npc_from_action(
                state, name, memory="艾琳娜四处寻求帮助，情绪濒临崩溃。", attitude_delta=0
            )
            state.flags["village_panic"] = min(
                100, int(state.flags.get("village_panic", 35)) + 3
            )
            events.append({
                "type": "npc_action",
                "text": "【NPC】艾琳娜抓住每一位过路人的衣袖，恳求帮忙寻找父亲。",
                "npc": name,
            })

        elif best_action == "ambush":
            events.append({
                "type": "npc_action",
                "text": "【NPC】森林深处传来口哨声——瓦里克的人在集结。",
                "npc": name,
            })

    return events[:2]

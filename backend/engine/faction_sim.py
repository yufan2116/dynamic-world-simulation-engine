"""派系模拟 — 资源、战略行动、世界张力。"""
from __future__ import annotations

from typing import Any

from engine.world_state import GameState

FACTION_IDS = ["村庄守卫", "村民", "强盗"]


def _ensure_factions(state: GameState) -> dict[str, dict[str, Any]]:
    raw = state.flags.get("factions")
    if not isinstance(raw, dict):
        raw = {}
    if raw:
        state.flags["factions"] = raw
        return raw
    defaults = {
        "村庄守卫": {"power": 55, "aggression": 20, "goal": "维持秩序", "mood": "警戒"},
        "村民": {"power": 40, "aggression": 5, "goal": "求安", "mood": "恐慌"},
        "强盗": {"power": 35, "aggression": 60, "goal": "控制商路", "mood": "伺机而动"},
    }
    for fid, d in defaults.items():
        raw[fid] = d.copy()
    state.flags["factions"] = raw
    return raw


def tick_factions(state: GameState) -> list[dict[str, Any]]:
    """每世界 Tick 更新派系并可能触发事件。"""
    events: list[dict[str, Any]] = []
    factions = _ensure_factions(state)
    from engine.world_template_manager import resolve_template_id

    tid = resolve_template_id(state.flags.get("template_id"))
    if tid == "xianxia_forbidden_land":
        return _tick_xianxia_factions(state, factions, events)

    guard = factions.get("村庄守卫")
    bandits = factions.get("强盗")
    villagers = factions.get("村民")
    if not guard or not bandits or not villagers:
        return events

    panic = int(state.flags.get("village_panic", 35))
    clue = state.flags.get("clue_found", False)

    # 恐慌削弱村民，强化守卫动员
    villagers["power"] = max(10, int(villagers["power"]) - panic // 30)
    guard["power"] = min(100, int(guard["power"]) + (5 if panic > 50 else 0))

    if not clue:
        bandits["power"] = min(100, int(bandits["power"]) + 3)
        if int(bandits["power"]) > 45:
            bandits["mood"] = "蠢蠢欲动"
        crisis = state.flags.get("crisis") or {}
        cp = float(crisis.get("pressure", 0)) if isinstance(crisis, dict) else 0
        if cp >= 35 and not state.flags.get("faction_warned_bandits"):
            state.flags["faction_warned_bandits"] = True
            events.append({
                "type": "faction",
                "text": "【派系】强盗势力在森林集结，商路风险上升。",
            })

    if int(bandits["power"]) > int(guard["power"]) + 15 and not state.flags.get("bandit_raid"):
        state.flags["bandit_raid"] = True
        state.flags["village_panic"] = min(100, panic + 15)
        state.weather = "阴云"
        events.append({
            "type": "faction",
            "text": "【派系】强盗袭扰仓库外围，守卫紧急增援——村庄进入高度戒备。",
        })
        state.faction_reputation["村庄守卫"] = state.faction_reputation.get("村庄守卫", 0) - 5

    if clue and int(bandits["power"]) > 50:
        guard["mood"] = "主动清剿"
        events.append({
            "type": "faction",
            "text": "【派系】村庄守卫开始组织清剿森林小路。",
        })

    # 同步声望与派系力量（轻量）
    state.faction_reputation["村庄守卫"] = min(100, max(-100, int(guard["power"]) - 15))
    state.faction_reputation["强盗"] = min(100, max(-100, int(bandits["power"]) - 55))
    state.faction_reputation["村民"] = min(100, max(-100, int(villagers["power"]) - 10))

    state.flags["war_risk"] = min(
        100, max(0, int(bandits["power"]) - int(guard["power"]) + 30)
    )
    return events


def _tick_xianxia_factions(
    state: GameState,
    factions: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """仙侠模板派系 tick — 宗门/散修/邪修/遗脉。"""
    taixu = factions.get("太虚宗", {})
    rogue = factions.get("散修盟", {})
    evil = factions.get("禁地邪修", {})
    tension = int(state.flags.get("tension", state.flags.get("spiritual_pollution", 40)))
    crisis = state.flags.get("crisis") or {}
    pressure = float(crisis.get("pressure", tension)) if isinstance(crisis, dict) else float(tension)

    if taixu:
        taixu["power"] = min(100, int(taixu.get("power", 60)) + (3 if pressure > 50 else 0))
        if pressure > 55 and not state.flags.get("faction_sect_alert"):
            state.flags["faction_sect_alert"] = True
            events.append({
                "type": "faction",
                "text": "【派系】太虚宗加强禁地外围巡查，弟子出入需验令牌。",
            })
    if evil:
        evil["power"] = min(100, int(evil.get("power", 30)) + 2)
        if int(evil.get("power", 30)) > 40 and not state.flags.get("faction_evil_stir"):
            state.flags["faction_evil_stir"] = True
            events.append({
                "type": "faction",
                "text": "【派系】禁地邪修势力躁动，灵气裂隙方向异光频现。",
            })
    if rogue:
        rogue["mood"] = "戒备" if pressure > 45 else rogue.get("mood", "谨慎")

    state.flags["tension"] = min(100, tension + (2 if pressure > 60 else 0))
    state.flags["war_risk"] = min(100, max(0, int(evil.get("power", 30)) - int(taixu.get("power", 60)) + 40))
    return events

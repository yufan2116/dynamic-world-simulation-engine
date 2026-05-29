"""谣言网络 — 起源、传播、可信度、NPC 可知范围。"""
from __future__ import annotations

import uuid
from typing import Any

from engine.world_ontology import is_xianxia, ontology_for_state, tension_value
from engine.world_state import GameState
from engine.world_state import ensure_player_known_facts
from engine.player_knowledge import ensure_player_knowledge
from engine.world_templates import location_connections_for_state


def _ensure_rumor_id(rumor: dict[str, Any]) -> str:
    rid = rumor.get("id")
    if rid:
        return str(rid)
    rid = uuid.uuid4().hex[:8]
    rumor["id"] = rid
    return rid


def _ensure_rumor_source(rumor: dict[str, Any]) -> None:
    # 兼容旧字段：origin（传播起点）仍保留；禁止 location 作为玩家可见来源
    origin = str(rumor.get("origin") or rumor.get("heard_at_location") or "村口")
    rumor.setdefault("origin", origin)
    st = str(rumor.get("source_type") or "").strip().lower()
    if not st or st == "location":
        rumor["source_type"] = "overheard_conversation"
        rumor.setdefault("source_id", "villagers_whisper")
        rumor.setdefault("source_label", "低声交谈的村民")
    else:
        rumor.setdefault("source_type", st)
        rumor.setdefault("source_id", rumor.get("source_id") or origin)
        rumor.setdefault("source_label", rumor.get("source_label") or rumor.get("source_id"))
    rumor.setdefault("visibility", "local")  # public | local | discovered | hidden
    rumor.setdefault("known_to_player", False)
    rumor.setdefault("first_heard_turn", None)
    rumor.setdefault("heard_at_location", None)


def _ensure_rumors(state: GameState) -> list[dict[str, Any]]:
    raw = state.flags.get("rumors")
    if not isinstance(raw, list):
        raw = []
    for rumor in raw:
        if isinstance(rumor, dict):
            _ensure_rumor_id(rumor)
            _ensure_rumor_source(rumor)
    state.flags["rumors"] = raw
    return raw


def add_rumor(
    state: GameState,
    text: str,
    origin: str,
    *,
    credibility: float = 0.7,
    known_by: list[str] | None = None,
    source_type: str = "location",
    source_id: str | None = None,
    source_label: str | None = None,
    visibility: str = "local",
    known_to_player: bool = False,
) -> dict[str, Any]:
    rumors = _ensure_rumors(state)
    rumor = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "origin": origin,
        "spread_to": [origin],
        "credibility": credibility,
        "known_by": known_by or [],
        "age_ticks": 0,
        "source_type": source_type,
        "source_id": source_id or origin,
        "source_label": source_label or (source_id or origin),
        "visibility": visibility,
        "known_to_player": known_to_player,
        "first_heard_turn": None,
        "heard_at_location": None,
    }
    rumors.append(rumor)
    if len(rumors) > 20:
        state.flags["rumors"] = rumors[-20:]
    return rumor


def tick_rumors(state: GameState) -> list[dict[str, Any]]:
    """谣言扩散一个 Tick。"""
    events: list[dict[str, Any]] = []
    rumors = _ensure_rumors(state)
    player_loc = state.location

    for rumor in rumors:
        if not isinstance(rumor, dict):
            continue
        rid = _ensure_rumor_id(rumor)
        rumor["age_ticks"] = int(rumor.get("age_ticks", 0)) + 1
        spread = list(rumor.get("spread_to", []))
        origin = rumor.get("origin", "村口")
        graph = location_connections_for_state(state)
        for neighbor in graph.get(origin, []):
            if neighbor not in spread and rumor["age_ticks"] >= 1:
                spread.append(neighbor)
        for loc in spread:
            for other_loc in graph.get(loc, []):
                if other_loc not in spread and rumor["age_ticks"] >= 2:
                    spread.append(other_loc)
        rumor["spread_to"] = spread

        # 玩家所在地点可「听到」新谣言
        if player_loc in spread and rumor["age_ticks"] <= 3:
            heard_key = f"heard_{rid}"
            if not state.flags.get(heard_key):
                state.flags[heard_key] = True
                # 标记为玩家已知（source-grounded）
                rumor["known_to_player"] = True
                rumor["heard_at_location"] = player_loc
                turn = int(state.flags.get("last_turn", 1) or 1)
                rumor["first_heard_turn"] = rumor.get("first_heard_turn") or turn
                facts = ensure_player_known_facts(state)
                known_rumors = facts.get("known_rumors") if isinstance(facts, dict) else []
                entry = {
                    "id": rid,
                    "text": str(rumor.get("text", "")),
                    "source_type": str(rumor.get("source_type", "npc")),
                    "source_label": str(rumor.get("source_label", "")),
                    "heard_at_turn": turn,
                    "heard_at_location": player_loc,
                }
                if isinstance(known_rumors, list):
                    if not any(isinstance(x, dict) and x.get("id") == rid for x in known_rumors):
                        known_rumors.append(entry)
                pk = ensure_player_knowledge(state)
                if not any(isinstance(x, dict) and x.get("id") == rid for x in pk.get("rumors", [])):
                    pk["rumors"].append(
                        {
                            "id": rid,
                            "text": entry["text"],
                            "source": entry["source_label"],
                            "source_type": entry["source_type"],
                            "source_label": entry["source_label"],
                        }
                    )
                events.append({
                    "type": "rumor",
                    "text": f"【传闻·{player_loc}】{rumor.get('source_label','')}：{rumor.get('text', '')}".strip("："),
                    "rumor_id": rid,
                })

    terms = (ontology_for_state(state).get("terms") or {})
    tension = tension_value(state)
    prefix = "【流闻】" if is_xianxia(state) else "【传闻】"
    for i, spec in enumerate(terms.get("rumor_auto") or []):
        if not isinstance(spec, dict):
            continue
        flag = f"rumor_auto_{i}"
        if state.flags.get(flag):
            continue
        min_p = spec.get("min_panic", spec.get("min_tension", 0))
        if min_p and tension < int(min_p):
            continue
        cond_flag = spec.get("when_flag")
        if cond_flag and not state.flags.get(cond_flag):
            continue
        origin = state.location if spec.get("origin_from_location") else spec.get("origin", state.location)
        add_rumor(state, spec.get("text", ""), origin, credibility=float(spec.get("credibility", 0.6)))
        state.flags[flag] = True

    if not is_xianxia(state):
        if state.flags.get("warehouse_noise") and not state.flags.get("rumor_warehouse_noise"):
            add_rumor(
                state,
                "昨夜村口外侧传来短促的撞击与脚步声。",
                "村口",
                credibility=0.6,
                source_type="overheard_conversation",
                source_id="night_watch",
                source_label="夜间巡逻的守卫",
                visibility="local",
            )
            state.flags["rumor_warehouse_noise"] = True
        if state.flags.get("bandit_raid") and not state.flags.get("rumor_bandit_raid"):
            add_rumor(
                state,
                "仓库外围发生冲突，守卫伤亡情况不明。",
                "村口",
                credibility=0.85,
                source_type="event",
                source_id="guard_report",
                source_label="守卫通报",
                visibility="public",
                known_to_player=True,
            )
            state.flags["rumor_bandit_raid"] = True

    return events[:2]


def rumors_at_location(state: GameState, location: str) -> list[dict[str, Any]]:
    rumors = _ensure_rumors(state)
    return [r for r in rumors if location in r.get("spread_to", [])]


def npc_knows_rumor(npc_name: str, rumor: dict[str, Any], npc_location: str) -> bool:
    if npc_name in rumor.get("known_by", []):
        return True
    return npc_location in rumor.get("spread_to", [])

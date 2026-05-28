"""轻量经济模拟 — 指标与事件文案由 world_terms 驱动。"""
from __future__ import annotations

from typing import Any

from engine.world_ontology import economy_spec, init_economy_from_ontology, is_xianxia, tension_value
from engine.world_state import GameState


def _ensure_economy(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("economy")
    if not isinstance(raw, dict) or not raw:
        return init_economy_from_ontology(state)
    state.flags["economy"] = raw
    return raw


def tick_economy(state: GameState) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    eco = _ensure_economy(state)
    spec = economy_spec(state)
    tension = tension_value(state)

    if is_xianxia(state):
        return _tick_xianxia_economy(state, eco, spec, tension, events)

    panic = tension
    bandit_raid = state.flags.get("bandit_raid", False)

    income = int(eco.get("tavern_income", 100))
    income = max(20, income - panic // 5 - (25 if bandit_raid else 0))
    eco["tavern_income"] = income

    grain = int(eco.get("grain_price", 10))
    if bandit_raid or not eco.get("trade_route_open", True):
        grain = min(50, grain + 3)
        eco["trade_route_open"] = not bandit_raid
    else:
        grain = max(8, grain - 1)
    eco["grain_price"] = grain

    for ev in spec.get("events", []):
        if not isinstance(ev, dict):
            continue
        flag = ev.get("flag")
        if flag and not state.flags.get(flag):
            triggered = False
            if flag == "mira_struggling" and income < 40:
                triggered = True
            elif flag == "mira_debt_crisis" and int(eco.get("mira_debt", 0)) >= 50:
                triggered = True
            if triggered:
                state.flags[flag] = True
                if flag == "mira_struggling":
                    eco["mira_debt"] = int(eco.get("mira_debt", 0)) + 10
                events.append({"type": "economy", "text": ev.get("text", "")})

    state.flags["economy"] = eco
    return events


def _tick_xianxia_economy(
    state: GameState,
    eco: dict[str, Any],
    spec: dict[str, Any],
    tension: int,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    vein = int(eco.get("spirit_vein_stability", 68))
    vein = max(10, vein - tension // 8)
    eco["spirit_vein_stability"] = vein

    pills = int(eco.get("pill_circulation", 52))
    pills = max(15, pills - (5 if tension > 50 else 2))
    eco["pill_circulation"] = pills

    pollution = int(eco.get("spirit_pollution", 38))
    pollution = min(100, pollution + (3 if tension > 45 else 1))
    eco["spirit_pollution"] = pollution
    state.flags["tension"] = pollution
    state.flags["spiritual_pollution"] = pollution

    seal = int(eco.get("seal_integrity", 45))
    seal = max(5, seal - (4 if state.flags.get("faction_evil_stir") else 2))
    eco["seal_integrity"] = seal

    for ev in spec.get("events", []):
        if not isinstance(ev, dict):
            continue
        flag = ev.get("flag")
        if not flag or state.flags.get(flag):
            continue
        triggered = False
        if flag == "vein_unstable" and vein < 45:
            triggered = True
        elif flag == "pill_shortage" and pills < 35:
            triggered = True
        elif flag == "seal_crack_spread" and seal < 30:
            triggered = True
        if triggered:
            state.flags[flag] = True
            events.append({"type": "economy", "text": ev.get("text", "")})

    state.flags["economy"] = eco
    return events

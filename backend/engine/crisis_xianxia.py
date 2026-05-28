"""仙侠模板危机升级 — 禁地异变，非商人失踪案语义。"""
from __future__ import annotations

import random
from typing import Any

from engine.rumor_network import add_rumor
from engine.world_ontology import crisis_labels, ontology_for_state, pick_clue, tension_value
from engine.world_state import GameState

TIER_THRESHOLDS = [20, 40, 60, 80]


def _ensure_crisis(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("crisis")
    if not isinstance(raw, dict):
        raw = {}
    defaults: dict[str, Any] = {
        "pressure": 18.0,
        "prev_pressure": 18.0,
        "max_tier_reached": 0,
        "case_status": "missing",
        "location_hint": None,
        "search_window": 100,
        "recent_anomalies": [],
        "suspicious_clues": [],
        "risk_notes": [],
        "fired_event_ids": [],
        "investigation_score": 0,
    }
    for k, v in defaults.items():
        raw.setdefault(k, v if not isinstance(v, list) else list(v))
    state.flags["crisis"] = raw
    return raw


def _faction_power(state: GameState, name: str) -> int:
    factions = state.flags.get("factions") or {}
    if isinstance(factions, dict) and name in factions:
        return int(factions[name].get("power", 40))
    return max(10, min(100, state.faction_reputation.get(name, 0) + 50))


def compute_crisis_pressure(state: GameState) -> float:
    crisis = _ensure_crisis(state)
    if crisis.get("case_status") == "resolved":
        return 0.0
    if crisis.get("case_status") == "dead":
        return min(100.0, float(crisis.get("pressure", 85)))

    labels = crisis_labels(state)
    sect = _faction_power(state, labels.get("faction_primary", "太虚宗"))
    evil = _faction_power(state, labels.get("faction_hostile", "禁地邪修"))
    tension = tension_value(state)
    pollution = int(state.flags.get("spirit_pollution", tension))

    pressure = 12.0
    inv = int(crisis.get("investigation_score", 0))
    if state.flags.get("clue_found"):
        inv += 20
    if state.flags.get("seal_inspected"):
        inv += 15
    pressure -= inv * 0.4

    if evil > sect:
        pressure += (evil - sect) * 0.5
    pressure += tension * 0.25 + pollution * 0.15
    pressure += min(12.0, len(state.flags.get("rumors") or []) * 1.5)

    return max(0.0, min(100.0, pressure))


def _tier_for_pressure(pressure: float) -> int:
    for t in reversed(TIER_THRESHOLDS):
        if pressure >= t:
            return t
    return 0


def _pressure_level(pressure: float) -> str:
    if pressure < 25:
        return "stable"
    if pressure < 45:
        return "rising"
    if pressure < 65:
        return "volatile"
    if pressure < 82:
        return "severe"
    return "critical"


def _append_clue(state: GameState, text: str) -> None:
    crisis = _ensure_crisis(state)
    clues = list(crisis.get("suspicious_clues", []))
    if text not in clues:
        clues.append(text)
    crisis["suspicious_clues"] = clues[-8:]


def _append_risk(state: GameState, key: str) -> None:
    notes = crisis_labels(state).get("risk_notes") or {}
    text = notes.get(key, key)
    crisis = _ensure_crisis(state)
    risks = list(crisis.get("risk_notes", []))
    if text not in risks:
        risks.append(text)
    crisis["risk_notes"] = risks[-6:]


def tick_crisis_xianxia(state: GameState) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    crisis = _ensure_crisis(state)
    terms = ontology_for_state(state).get("terms") or {}
    crisis_events = terms.get("crisis_events") or []

    prev = float(crisis.get("pressure", 18.0))
    pressure = compute_crisis_pressure(state)
    crisis["prev_pressure"] = prev
    crisis["pressure"] = pressure

    fired = set(crisis.get("fired_event_ids") or [])
    for ev in crisis_events:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("id")
        tier = int(ev.get("tier", 20))
        if not eid or eid in fired:
            continue
        if pressure >= tier and prev < tier:
            crisis["fired_event_ids"] = list(fired | {eid})
            fired.add(eid)
            clue = pick_clue(state)
            _append_clue(state, clue)
            if ev.get("text"):
                events.append({"type": "crisis", "text": ev["text"], "event_id": eid})
            crisis["case_status"] = "clue_surface"
            add_rumor(
                state,
                f"山门流闻：{clue}，或与弟子失踪有关。",
                state.location,
                credibility=0.65,
            )
            break

    level = _pressure_level(pressure)
    crisis["level"] = level
    if level == "rising":
        _append_risk(state, "case_worsening")
    if _faction_power(state, "禁地邪修") > _faction_power(state, "太虚宗"):
        _append_risk(state, "hostile_activity")
    if int(crisis.get("search_window", 100)) < 40:
        _append_risk(state, "window_shrinking")

    state.flags["crisis"] = crisis
    state.flags["quest_urgency"] = int(min(100, pressure))
    return events[:2]

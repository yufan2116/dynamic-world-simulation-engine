"""世界滴答 — 编排派系、谣言、NPC AI、经济与动态危机。"""
from __future__ import annotations

from typing import Any

from engine.crisis_escalation import tick_crisis_escalation
from engine.economy_sim import tick_economy
from engine.faction_sim import tick_factions
from engine.npc_ai import tick_npc_ai
from engine.rumor_network import tick_rumors
from engine.world_state import GameState

TIME_SLOTS = ["凌晨", "清晨", "正午", "傍晚", "深夜"]
MINUTES_PER_SLOT = 360


def _minutes_to_label(total: int) -> tuple[int, str, str]:
    day = total // 1440 + 1
    m = total % 1440
    hour, minute = m // 60, m % 60
    slot_idx = min(len(TIME_SLOTS) - 1, m // MINUTES_PER_SLOT)
    return day, TIME_SLOTS[slot_idx], f"{hour:02d}:{minute:02d}"


def get_world_minutes(state: GameState) -> int:
    return int(state.flags.get("world_minutes", 480))


def advance_world_time(state: GameState, minutes: int = 30) -> dict[str, Any]:
    after = get_world_minutes(state) + minutes
    state.flags["world_minutes"] = after
    day, slot, clock = _minutes_to_label(after)
    prev_day = state.day
    state.day = day
    state.time_of_day = slot
    state.flags["clock"] = clock
    return {
        "minutes_advanced": minutes,
        "clock": clock,
        "day": day,
        "time_of_day": slot,
        "day_changed": day != prev_day,
    }


def _ensure_pressure(state: GameState) -> None:
    state.flags.setdefault("village_panic", 35)
    state.flags.setdefault("danger_level", "中")
    state.flags.setdefault("war_risk", 25)


def _update_village_pressure(state: GameState) -> None:
    """村庄恐慌由危机与社会状态驱动，非固定天数。"""
    _ensure_pressure(state)
    crisis = state.flags.get("crisis") or {}
    crisis_pressure = float(crisis.get("pressure", 12)) if isinstance(crisis, dict) else 12.0
    panic = int(state.flags.get("village_panic", 35))
    # 缓慢漂移 + 危机耦合
    drift = 1 + int(crisis_pressure // 25)
    panic = min(100, panic + drift)
    state.flags["village_panic"] = panic
    if panic >= 70:
        state.flags["danger_level"] = "高"
    elif panic >= 45:
        state.flags["danger_level"] = "中"
    else:
        state.flags["danger_level"] = "低"


def _dedupe_events(events: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in events:
        key = e.get("text", "")[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
        if len(out) >= limit:
            break
    return out


def run_world_ticks(state: GameState, ticks: int = 1) -> list[dict[str, Any]]:
    """运行完整世界模拟滴答。"""
    all_events: list[dict[str, Any]] = []
    for _ in range(ticks):
        all_events.extend(tick_crisis_escalation(state))
        _update_village_pressure(state)
        all_events.extend(tick_factions(state))
        all_events.extend(tick_npc_ai(state))
        all_events.extend(tick_rumors(state))
        all_events.extend(tick_economy(state))
        if int(state.flags.get("village_panic", 0)) >= 65:
            all_events.append({
                "type": "pressure",
                "text": "【压力】村民闭门不出，广场上空无一人。",
            })
    return _dedupe_events(all_events, limit=4)


def format_world_briefing(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    lines = "".join(
        f"<p class=\"world\">{e['text']}</p>" for e in events
    )
    return f"<div class='world-briefing'>{lines}</div>"


def format_offline_summary(summary: list[str]) -> str:
    if not summary:
        return ""
    items = "".join(f"<li>{s}</li>" for s in summary if s)
    return (
        f"<div class='offline-summary'>"
        f"<p class='chapter-epigraph'>你离开期间，世界并未停歇</p>"
        f"<ul>{items}</ul></div>"
    )

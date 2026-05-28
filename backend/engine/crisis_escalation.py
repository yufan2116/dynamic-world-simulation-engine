"""动态危机升级 — 失踪商人案由世界状态驱动，非固定天数剧本。"""
from __future__ import annotations

import random
from typing import Any, Callable

from engine.npc_memory import add_memory, update_npc_from_action
from engine.rumor_network import add_rumor
from engine.world_ontology import crisis_labels, is_xianxia, ontology_for_state, ui_label
from engine.world_state import GameState

# 危机等级阈值
TIER_THRESHOLDS = [20, 40, 60, 80]

MERCHANT_STATUS_LABELS = {
    "missing": "下落不明",
    "clue_surface": "出现新线索",
    "injured": "受伤但存活",
    "relocated": "被转移他处",
    "plea_letter": "留下求救讯息",
    "rescue_window_narrow": "救援窗口收窄",
    "dead": "确认遇难",
    "resolved": "案情已破",
}

LEVEL_LABELS = {
    "stable": "局势尚可",
    "rising": "失踪案正在恶化",
    "volatile": "局势动荡",
    "severe": "危机加剧",
    "critical": "濒临失控",
}


def _ensure_crisis(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("crisis")
    if not isinstance(raw, dict):
        raw = {}
    defaults: dict[str, Any] = {
        "pressure": 12.0,
        "prev_pressure": 12.0,
        "max_tier_reached": 0,
        "merchant_status": "missing",
        "merchant_location_hint": None,
        "search_window": 100,
        "recent_anomalies": [],
        "suspicious_clues": [],
        "risk_notes": [],
        "fired_event_ids": [],
        "player_rest_ticks": 0,
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
    rep = state.faction_reputation.get(name, 0)
    return max(10, min(100, rep + 50))


def _rumor_activity(state: GameState) -> int:
    rumors = state.flags.get("rumors") or []
    if not isinstance(rumors, list):
        return 0
    return len(rumors) + sum(len(r.get("spread_to", [])) for r in rumors if isinstance(r, dict))


def _night_or_storm(state: GameState) -> float:
    bonus = 0.0
    if state.time_of_day in ("凌晨", "深夜"):
        bonus += 6.0
    if state.weather in ("暴雨", "阴云", "浓雾", "薄雾"):
        bonus += 4.0
    if state.location in ("森林小路", "仓库"):
        bonus += 5.0
    return bonus


def compute_crisis_pressure(state: GameState) -> float:
    """多变量合成 crisis_pressure（0~100），非 day_count。"""
    crisis = _ensure_crisis(state)
    if crisis.get("merchant_status") == "resolved":
        return 0.0
    if crisis.get("merchant_status") == "dead":
        return min(100.0, float(crisis.get("pressure", 80)))

    guard = _faction_power(state, "村庄守卫")
    bandits = _faction_power(state, "强盗")
    panic = int(state.flags.get("village_panic", 35))
    rumors = _rumor_activity(state)

    pressure = 8.0
    # 调查进展（负向压力）
    inv = int(crisis.get("investigation_score", 0))
    if state.flags.get("clue_found"):
        inv += 25
    if state.flags.get("warehouse_searched"):
        inv += 10
    if state.flags.get("guard_info"):
        inv += 8
    pressure -= inv * 0.35

    # 派系失衡
    if bandits > guard:
        pressure += (bandits - guard) * 0.45
    else:
        pressure -= min(8.0, (guard - bandits) * 0.15)

    # 社会恐慌与谣言
    pressure += panic * 0.22
    pressure += min(15.0, rumors * 1.2)

    # 玩家拖延（休息 tick）
    pressure += int(crisis.get("player_rest_ticks", 0)) * 1.5

    # 世界自主响应不足时压力升
    if not state.flags.get("guard_patrol_active") and not state.flags.get("clue_found"):
        pressure += 4.0

    # 环境危险
    pressure += _night_or_storm(state)

    # 强盗袭扰已发生
    if state.flags.get("bandit_raid"):
        pressure += 10.0

    return round(max(0.0, min(100.0, pressure)), 1)


def _pressure_level(pressure: float) -> str:
    if pressure < 25:
        return "stable"
    if pressure < 45:
        return "rising"
    if pressure < 65:
        return "volatile"
    if pressure < 85:
        return "severe"
    return "critical"


def _tier_for_pressure(pressure: float) -> int:
    tier = 0
    for t in TIER_THRESHOLDS:
        if pressure >= t:
            tier = t
    return tier


def record_player_rest(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    crisis["player_rest_ticks"] = int(crisis.get("player_rest_ticks", 0)) + 1
    _append_risk_note(state, "搜索窗口正在缩小")


def record_investigation_progress(state: GameState, amount: int = 5) -> None:
    crisis = _ensure_crisis(state)
    crisis["investigation_score"] = int(crisis.get("investigation_score", 0)) + amount
    crisis["search_window"] = min(100, int(crisis.get("search_window", 100)) + 3)


def _append_anomaly(state: GameState, text: str) -> None:
    crisis = _ensure_crisis(state)
    anomalies: list[str] = list(crisis.get("recent_anomalies", []))
    anomalies.append(text)
    crisis["recent_anomalies"] = anomalies[-8:]


def _append_clue(state: GameState, text: str) -> None:
    crisis = _ensure_crisis(state)
    clues: list[str] = list(crisis.get("suspicious_clues", []))
    if text not in clues:
        clues.append(text)
    crisis["suspicious_clues"] = clues[-10:]


def _append_risk_note(state: GameState, text: str) -> None:
    crisis = _ensure_crisis(state)
    notes: list[str] = list(crisis.get("risk_notes", []))
    if text not in notes:
        notes.append(text)
    crisis["risk_notes"] = notes[-6:]


def _event_fired(state: GameState, event_id: str) -> bool:
    crisis = _ensure_crisis(state)
    fired: list[str] = list(crisis.get("fired_event_ids", []))
    return event_id in fired


def _mark_event_fired(state: GameState, event_id: str) -> None:
    crisis = _ensure_crisis(state)
    fired: list[str] = list(crisis.get("fired_event_ids", []))
    if event_id not in fired:
        fired.append(event_id)
    crisis["fired_event_ids"] = fired


# --- 危机事件定义 ---
CrisisEvent = dict[str, Any]


def _evt(
    eid: str,
    tier: int,
    text: str,
    apply_fn: Callable[[GameState], None],
    *,
    condition: Callable[[GameState], bool] | None = None,
    repeatable: bool = False,
) -> CrisisEvent:
    return {
        "id": eid,
        "tier": tier,
        "text": text,
        "apply": apply_fn,
        "condition": condition or (lambda _s: True),
        "repeatable": repeatable,
    }


def _apply_merchant_clue(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    crisis["merchant_status"] = "clue_surface"
    _append_clue(state, "马库斯在仓库留下一枚带划痕的银币")
    add_rumor(state, "有人声称在仓库发现属于马库斯的银币。", "仓库", credibility=0.75)
    _append_anomaly(state, "仓库角落发现一枚带划痕的银币")


def _apply_bandit_relocate(state: GameState) -> None:
    state.flags["bandit_relocated"] = True
    if "瓦里克" in state.npcs:
        state.npcs["瓦里克"].location = "森林小路"
    _append_risk_note(state, "强盗活动区域正在转移")
    _append_anomaly(state, "森林小路的脚印指向更深处的营地")


def _apply_villager_blood(state: GameState) -> None:
    _append_clue(state, "村民在村口附近发现可疑血迹")
    add_rumor(state, "村口湿土上有新鲜血迹，来源不明。", "村口", credibility=0.65)
    state.flags["village_panic"] = min(100, int(state.flags.get("village_panic", 35)) + 8)
    _append_anomaly(state, "几名村民在湿土上发现了尚未干涸的血迹")


def _apply_guard_search_fail(state: GameState) -> None:
    update_npc_from_action(
        state,
        "托马斯",
        memory="组织搜索队失败，未发现商人踪迹。",
        attitude_delta=-3,
    )
    _append_anomaly(state, "守卫搜索队空手而归")
    _append_risk_note(state, "官方搜索未能取得进展")


def _apply_mira_rumor(state: GameState) -> None:
    add_rumor(
        state,
        "米拉私下说：马库斯失踪前与陌生人有秘密交易。",
        "酒馆",
        known_by=["米拉"],
        credibility=0.55,
    )
    add_memory(state.npcs["米拉"], "米拉向酒客透露马库斯可能有隐秘交易。")
    _append_anomaly(state, "米拉在酒馆后堂与熟客低声交谈")


def _apply_plea_letter(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    crisis["merchant_status"] = "plea_letter"
    _append_clue(state, "森林小路发现马库斯的求救信残页")
    state.flags["plea_letter_found"] = True
    _append_anomaly(state, "一名樵夫在森林边沿捡到残破的求救信")


def _apply_bandit_conflict(state: GameState) -> None:
    factions = state.flags.get("factions") or {}
    if isinstance(factions, dict) and "强盗" in factions:
        factions["强盗"]["power"] = max(15, int(factions["强盗"].get("power", 35)) - 12)
        factions["强盗"]["mood"] = "内讧"
    _append_anomaly(state, "森林深处传来争吵与刀剑声——强盗内部似乎起了冲突")


def _apply_merchant_injured(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    crisis["merchant_status"] = "injured"
    crisis["merchant_location_hint"] = "森林营地"
    _append_clue(state, "有猎人看见受伤商人被带往森林营地")
    add_rumor(state, "猎人声称看见一名受伤商人被押入黑森林。", "森林小路", credibility=0.5)
    _append_risk_note(state, "失踪者可能仍存活，但处境危险")


def _apply_merchant_relocated(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    crisis["merchant_status"] = "relocated"
    crisis["merchant_location_hint"] = "旧仓库地下"
    state.flags["merchant_hidden_location"] = "仓库"
    _append_clue(state, "货物堆下方发现短暂停留的痕迹")
    _append_risk_note(state, "新的线索可能正在消失")


def _apply_merchant_dead(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    # 仅当 bandits strong + low investigation + high panic
    crisis["merchant_status"] = "dead"
    _append_anomaly(state, "黑森林边缘发现属于马库斯的个人物品")
    add_rumor(state, "林边发现商人的行囊，本人仍无下落。", "森林小路", credibility=0.7)
    state.flags["village_panic"] = min(100, int(state.flags.get("village_panic", 35)) + 12)
    for q in state.quests:
        if q.id == "missing_merchant" and q.status == "active":
            q.description = "马库斯恐已遇难，但真相仍未查明——艾琳娜需要你继续调查。"


def _apply_rescue_window(state: GameState) -> None:
    crisis = _ensure_crisis(state)
    crisis["merchant_status"] = "rescue_window_narrow"
    crisis["search_window"] = max(15, int(crisis.get("search_window", 100)) - 25)
    _append_risk_note(state, "最佳救援窗口正在缩小")
    _append_risk_note(state, "新的线索可能正在消失")


def _can_merchant_die(state: GameState) -> bool:
    crisis = _ensure_crisis(state)
    bandits = _faction_power(state, "强盗")
    guard = _faction_power(state, "村庄守卫")
    inv = int(crisis.get("investigation_score", 0))
    return (
        bandits > guard + 10
        and inv < 15
        and float(crisis.get("pressure", 0)) >= 78
        and not state.flags.get("clue_found")
    )


CRISIS_EVENTS: list[CrisisEvent] = [
    _evt("clue_silver", 20, "【危机】商人在仓库留下了新的痕迹——一枚带划痕的银币。", _apply_merchant_clue),
    _evt("bandit_relocate", 20, "【危机】强盗似乎正在转移据点，森林里的足迹改了方向。", _apply_bandit_relocate),
    _evt("villager_blood", 40, "【危机】村民在湿土上发现了可疑的血迹。", _apply_villager_blood),
    _evt("guard_search_fail", 40, "【危机】守卫组织的搜索队一无所获，士气受挫。", _apply_guard_search_fail),
    _evt("mira_rumor", 40, "【危机】米拉听到了关于马库斯秘密交易的新传闻。", _apply_mira_rumor),
    _evt("plea_letter", 60, "【危机】森林边沿发现马库斯留下的求救信残页。", _apply_plea_letter),
    _evt("bandit_conflict", 60, "【危机】强盗内部爆发冲突，森林深处传来厮杀声。", _apply_bandit_conflict),
    _evt("merchant_injured", 60, "【危机】有目击者称看见受伤的商人被押入森林。", _apply_merchant_injured,
         condition=lambda s: not _event_fired(s, "merchant_dead")),
    _evt("merchant_relocated", 60, "【危机】线索表明商人可能被转移——痕迹指向旧仓库深处。", _apply_merchant_relocated),
    _evt("rescue_window", 60, "【危机】失踪案正在恶化，救援窗口明显收窄。", _apply_rescue_window, repeatable=True),
    _evt("merchant_dead", 80, "【危机】林边发现商人行囊，失踪案恐已走向最坏结局。", _apply_merchant_dead,
         condition=_can_merchant_die),
    _evt("missed_window", 80, "【危机】你或许错过了最佳救援时机——但真相仍可追查。", _apply_rescue_window,
         condition=lambda s: int(_ensure_crisis(s).get("investigation_score", 0)) >= 10),
]


def _pick_tier_event(state: GameState, tier: int, pressure: float) -> CrisisEvent | None:
    eligible = [
        e for e in CRISIS_EVENTS
        if e["tier"] == tier
        and e["condition"](state)
        and (e.get("repeatable") or not _event_fired(state, e["id"]))
    ]
    if not eligible:
        return None
    # 压力越高，越倾向高影响事件（同 tier 内按 id 权重简化：shuffle with pressure bias）
    random.shuffle(eligible)
    return eligible[0]


def tick_crisis_escalation(state: GameState) -> list[dict[str, Any]]:
    """每个 World Tick 更新 crisis_pressure 并可能触发分级事件。"""
    if is_xianxia(state):
        from engine.crisis_xianxia import tick_crisis_xianxia

        return tick_crisis_xianxia(state)

    events: list[dict[str, Any]] = []
    crisis = _ensure_crisis(state)

    prev = float(crisis.get("pressure", 12.0))
    pressure = compute_crisis_pressure(state)
    crisis["prev_pressure"] = prev
    crisis["pressure"] = pressure

    # 搜索窗口随压力收缩（调查可减缓）
    shrink = max(0, int(pressure // 15) - int(crisis.get("investigation_score", 0)) // 8)
    if shrink > 0 and crisis.get("merchant_status") not in ("dead", "resolved"):
        crisis["search_window"] = max(5, int(crisis.get("search_window", 100)) - shrink)

    tier = _tier_for_pressure(pressure)
    max_tier = int(crisis.get("max_tier_reached", 0))

    # 跨阈值触发该 tier 事件
    for t in TIER_THRESHOLDS:
        if pressure >= t and (prev < t or t > max_tier):
            picked = _pick_tier_event(state, t, pressure)
            if picked:
                picked["apply"](state)
                if not picked.get("repeatable"):
                    _mark_event_fired(state, picked["id"])
                events.append({"type": "crisis", "text": picked["text"], "event_id": picked["id"]})
                crisis["max_tier_reached"] = max(max_tier, t)
                max_tier = int(crisis.get("max_tier_reached", 0))

    # 高压持续：小概率重复 ambient 危机
    if pressure >= 55 and random.random() < 0.15:
        ambient = _pick_tier_event(state, 40 if pressure < 70 else 60, pressure)
        if ambient and ambient.get("repeatable"):
            ambient["apply"](state)
            events.append({"type": "crisis", "text": ambient["text"], "event_id": ambient["id"]})

    # 动态 risk notes（非倒计时文案）
    level = _pressure_level(pressure)
    crisis["level"] = level
    if level == "rising" and "失踪案正在恶化" not in crisis.get("risk_notes", []):
        _append_risk_note(state, "失踪案正在恶化")
    if _faction_power(state, "强盗") > _faction_power(state, "村庄守卫"):
        _append_risk_note(state, "强盗活动加剧")
    if int(crisis.get("search_window", 100)) < 40:
        _append_risk_note(state, "搜索窗口正在缩小")

    state.flags["crisis"] = crisis
    # 同步旧字段供兼容（不再用于 day 逻辑）
    state.flags["quest_urgency"] = int(min(100, pressure))

    return events[:2]


def get_crisis_ui(state: GameState) -> dict[str, Any]:
    """供 API / 前端展示，不含固定倒计时。"""
    if is_xianxia(state):
        from engine.crisis_xianxia import compute_crisis_pressure as x_pressure
        from engine.crisis_xianxia import _ensure_crisis as x_ensure
        from engine.crisis_xianxia import _pressure_level as x_level

        crisis = x_ensure(state)
        pressure = float(crisis.get("pressure", x_pressure(state)))
        level = x_level(pressure)
        cl = crisis_labels(state)
        status_labels = cl.get("status_labels") or {}
        level_labels = cl.get("level_labels") or {}
        status = str(crisis.get("case_status", "missing"))
    else:
        crisis = _ensure_crisis(state)
        pressure = float(crisis.get("pressure", compute_crisis_pressure(state)))
        level = _pressure_level(pressure)
        cl = crisis_labels(state)
        status_labels = cl.get("status_labels") or MERCHANT_STATUS_LABELS
        level_labels = cl.get("level_labels") or LEVEL_LABELS
        status = str(crisis.get("merchant_status", "missing"))

    search_w = int(crisis.get("search_window", 100))
    if search_w >= 70:
        window_label = "尚可追查"
    elif search_w >= 40:
        window_label = "正在收窄"
    else:
        window_label = ui_label(state, "search_window", "窗口收窄") + " · 紧迫"

    onto = ontology_for_state(state)
    return {
        "pressure": round(pressure, 1),
        "level": level,
        "level_label": level_labels.get(level, LEVEL_LABELS.get(level, "未知")),
        "merchant_status": status,
        "merchant_status_label": status_labels.get(status, "未知"),
        "search_window": search_w,
        "search_window_label": window_label,
        "recent_anomalies": list(crisis.get("recent_anomalies", []))[-5:],
        "suspicious_clues": list(crisis.get("suspicious_clues", []))[-5:],
        "risk_notes": list(crisis.get("risk_notes", []))[-4:],
        "merchant_location_hint": crisis.get("merchant_location_hint")
        or crisis.get("location_hint"),
        "ontology": onto.get("ui", {}),
        "crisis_title": ui_label(state, "crisis_block_title", "危机"),
    }

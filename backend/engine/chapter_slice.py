"""《失踪的商人》Vertical Slice — 调查路线、结局触发与会话总结（非新模拟子系统）。"""
from __future__ import annotations

from typing import Any

from engine.crisis_escalation import _ensure_crisis, compute_crisis_pressure
from engine.world_state import GameState, ensure_player_known_facts

# 三条调查路线对应 NPC
ROUTE_NPCS = ("托马斯", "米拉", "艾琳娜")
ROUTE_KEYS = ("thomas", "mira", "elena")

ENDING_IDS = ("rescue_success", "remains_found", "truth_buried")

# 可发现线索目录（用于总结页「发现/错过」）
CLUE_CATALOG: list[dict[str, str]] = [
    {"id": "clue_guard_shadow_old_warehouse", "label": "守卫提及昨夜可疑人影与旧仓库", "route": "thomas"},
    {"id": "fact_thomas_acknowledged_night_activity", "label": "托马斯承认村口外侧有异常动静", "route": "thomas"},
    {"id": "clue_marcus_last_seen_near_warehouse", "label": "马库斯最后出现在仓库方向", "route": "mira"},
    {"id": "fact_elena_father_promise", "label": "艾琳娜：父亲答应今晚回来", "route": "elena"},
    {"id": "clue_marcus_last_seen", "label": "仓库附近发现马库斯最后踪迹", "route": "mira"},
    {"id": "plea_letter_found", "label": "森林边沿的求救信残页", "route": "thomas"},
]

ENDING_COPY: dict[str, dict[str, str]] = {
    "rescue_success": {
        "title": "马库斯还活着",
        "subtitle": "你在窗口关闭前找到了他",
        "epigraph": "结局 · 救援成功",
        "body": (
            "<p>森林营地的火光在雨雾里摇晃。马库斯蜷缩在货箱后，手腕被麻绳勒出血痕，"
            "却仍死死攥着那枚带划痕的银币。</p>"
            "<p class=\"dialogue\">「我以为……再也见不到艾琳娜了。」</p>"
            "<p>你把斗篷披在他肩上，押着残余的绑匪退回村口。艾琳娜的哭声终于变成了笑，"
            "托马斯向你点头——这一次，没有回避你的目光。</p>"
        ),
    },
    "remains_found": {
        "title": "太迟了",
        "subtitle": "你只找到了他留下的东西",
        "epigraph": "结局 · 遗体未寻获",
        "body": (
            "<p>林边的泥土被雨水泡软。破损行囊、撕裂的账本、一枚熟悉的银币——"
            "一切都指向同一个人，却再也没有他的呼吸。</p>"
            "<p>艾琳娜跪在广场中央，发不出声音。米拉别过脸，把一杯烈酒推到你面前，"
            "却什么也没说。托马斯低声下令封锁现场，眼中是压抑的怒火与疲惫。</p>"
            "<p><em>真相的一部分随马库斯一同埋进了黑森林的泥里。</em></p>"
        ),
    },
    "truth_buried": {
        "title": "被掩盖的真相",
        "subtitle": "村庄选择遗忘，而你也默许了",
        "epigraph": "结局 · 真相被掩盖",
        "body": (
            "<p>酒馆后堂的烛火只照见半张脸。米拉把一封信塞进你手里，字迹潦草："
            "马库斯不是「失踪」，而是被送走——为了平息一场不该被村民知道的交易。</p>"
            "<p>托马斯在广场上宣布「搜寻无果，全员撤回」。没有人再提起仓库，"
            "没有人再提起黑森林。艾琳娜被劝回家「静养」，她的问题被礼貌地打断。</p>"
            "<p><em>雷文福德恢复平静。平静得像什么都没发生过。</em></p>"
        ),
    },
}


def is_vertical_slice(state: GameState) -> bool:
    if state.flags.get("vertical_slice_demo"):
        return True
    seed = str(state.flags.get("seed_id") or "")
    return seed == "ravenford_demo"


def _routes(state: GameState) -> dict[str, int]:
    raw = state.flags.get("slice_routes")
    if not isinstance(raw, dict):
        raw = {"thomas": 0, "mira": 0, "elena": 0}
        state.flags["slice_routes"] = raw
    for k in ROUTE_KEYS:
        raw.setdefault(k, 0)
    return raw


def _npc_attitude(state: GameState, name: str) -> int:
    npc = state.npcs.get(name)
    return int(npc.attitude_value) if npc else 0


def _known_fact_ids(state: GameState) -> set[str]:
    ids: set[str] = set()
    facts = ensure_player_known_facts(state)
    for bucket in ("known_facts", "player_facing_facts"):
        arr = facts.get(bucket)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    if state.flags.get("clue_found"):
        ids.add("clue_marcus_last_seen")
    if state.flags.get("plea_letter_found"):
        ids.add("plea_letter_found")
    if state.flags.get("guard_info"):
        ids.add("clue_guard_shadow_old_warehouse")
    pk = state.flags.get("player_knowledge")
    if isinstance(pk, dict):
        for bucket in ("facts", "clues", "observations"):
            for item in pk.get(bucket) or []:
                if isinstance(item, dict) and item.get("id"):
                    ids.add(str(item["id"]))
    return ids


def track_slice_turn(
    state: GameState,
    intent: dict[str, Any],
    changes: dict[str, Any],
    *,
    player_action_display: str = "",
    turn: int = 0,
) -> None:
    """记录调查路线进度与关键选择（仅 vertical slice）。"""
    if not is_vertical_slice(state):
        return

    action = str(intent.get("action_type") or "")
    target = str(intent.get("target") or "")
    routes = _routes(state)
    succeeded = bool(changes.get("check_succeeded", True))

    route_map = {"托马斯": "thomas", "米拉": "mira", "艾琳娜": "elena"}
    if target in route_map and action in ("talk", "persuade", "investigate"):
        key = route_map[target]
        if succeeded:
            routes[key] = min(5, int(routes.get(key, 0)) + 1)
        state.flags[f"slice_route_{key}_touched"] = True

    choices: list[dict[str, Any]] = list(state.flags.get("slice_choices") or [])
    label = (player_action_display or intent.get("description") or "").strip()
    if label and len(choices) < 24:
        choices.append({"turn": turn, "label": label[:120]})
    state.flags["slice_choices"] = choices
    state.flags["slice_turn_count"] = int(state.flags.get("slice_turn_count") or 0) + 1


def _min_turns_for_ending(state: GameState) -> int:
    return 8 if is_vertical_slice(state) else 12


def _force_turn(state: GameState) -> int:
    return 18 if is_vertical_slice(state) else 28


def evaluate_chapter_ending(state: GameState, turn: int) -> str | None:
    """根据危机、线索、信任与世界状态判定结局；已完结则返回既有 id。"""
    if not is_vertical_slice(state):
        return None
    existing = state.flags.get("chapter_ending_id")
    if existing in ENDING_IDS:
        return str(existing)

    min_turns = _min_turns_for_ending(state)
    if turn < min_turns and int(state.flags.get("slice_turn_count") or 0) < min_turns:
        return None

    crisis = _ensure_crisis(state)
    pressure = float(crisis.get("pressure", compute_crisis_pressure(state)))
    inv = int(crisis.get("investigation_score", 0))
    status = str(crisis.get("merchant_status", "missing"))
    search_w = int(crisis.get("search_window", 100))
    routes = _routes(state)
    known = _known_fact_ids(state)

    thomas_r = int(routes.get("thomas", 0))
    mira_r = int(routes.get("mira", 0))
    elena_r = int(routes.get("elena", 0))
    routes_active = sum(1 for v in (thomas_r, mira_r, elena_r) if v > 0)

    att_thomas = _npc_attitude(state, "托马斯")
    att_mira = _npc_attitude(state, "米拉")
    att_elena = _npc_attitude(state, "艾琳娜")

    clues_count = sum(1 for c in CLUE_CATALOG if c["id"] in known or c["id"].replace("clue_", "") in str(state.flags))

    # —— 救援成功 ——
    rescue_ok = (
        inv >= 18
        and routes_active >= 2
        and thomas_r >= 1
        and mira_r >= 1
        and status in ("injured", "relocated", "plea_letter", "rescue_window_narrow", "clue_surface")
        and status != "dead"
        and pressure < 82
        and (
            state.location in ("森林小路", "仓库", "村口")
            or state.flags.get("plea_letter_found")
            or state.flags.get("clue_found")
        )
    )
    if rescue_ok:
        return "rescue_success"

    # —— 仅找到遗物/确认遇难 ——
    remains_ok = (
        status == "dead"
        or (pressure >= 78 and search_w < 35)
        or (status in ("dead",) and clues_count < 3)
    )
    if remains_ok and not rescue_ok:
        return "remains_found"

    # —— 真相被掩盖 ——
    cover_ok = (
        mira_r >= 2
        and inv < 22
        and (thomas_r == 0 or att_thomas < 5)
        and _event_fired(state, "mira_rumor")
        and pressure >= 45
    )
    if cover_ok and not rescue_ok:
        return "truth_buried"

    # 演示：超时强制收束（避免无限局）
    if turn >= _force_turn(state) or int(state.flags.get("slice_turn_count") or 0) >= _force_turn(state):
        if inv >= 15 and routes_active >= 2:
            return "rescue_success"
        if status == "dead" or pressure >= 70:
            return "remains_found"
        return "truth_buried"

    return None


def _event_fired(state: GameState, event_id: str) -> bool:
    crisis = _ensure_crisis(state)
    fired = crisis.get("fired_event_ids") or []
    return event_id in fired if isinstance(fired, list) else False


def apply_chapter_ending(state: GameState, ending_id: str) -> str:
    """写入结局状态并返回结局叙事 HTML。"""
    crisis = _ensure_crisis(state)
    copy = ENDING_COPY.get(ending_id, ENDING_COPY["remains_found"])

    if ending_id == "rescue_success":
        crisis["merchant_status"] = "resolved"
        for q in state.quests:
            if q.id == "missing_merchant":
                q.status = "completed"
                q.description = "马库斯已获救，艾琳娜终于松了一口气。"
    elif ending_id == "remains_found":
        crisis["merchant_status"] = "dead"
        for q in state.quests:
            if q.id == "missing_merchant":
                q.status = "failed"
                q.description = "马库斯恐已遇难——村庄接受了最坏的可能。"
    else:
        crisis["merchant_status"] = "resolved"
        state.flags["truth_buried"] = True
        for q in state.quests:
            if q.id == "missing_merchant":
                q.status = "completed"
                q.description = "官方口径：搜寻无果。你知道的更多，却选择沉默。"

    crisis["pressure"] = max(0.0, float(crisis.get("pressure", 0)) - 30)
    state.flags["crisis"] = crisis
    state.flags["chapter_ending_id"] = ending_id
    state.flags["chapter_complete"] = True
    state.flags["game_phase"] = "chapter_complete"

    return (
        f"<div class=\"chapter-ending\">"
        f"<p class=\"chapter-epigraph\">{copy['epigraph']}</p>"
        f"<h2 class=\"ending-title\">{copy['title']}</h2>"
        f"<p class=\"ending-subtitle\"><em>{copy['subtitle']}</em></p>"
        f"{copy['body']}"
        f"</div>"
    )


def build_session_summary(state: GameState) -> dict[str, Any]:
    """Session Summary — 供 Chapter Complete UI。"""
    ending_id = str(state.flags.get("chapter_ending_id") or "")
    copy = ENDING_COPY.get(ending_id, {})
    known = _known_fact_ids(state)
    crisis = _ensure_crisis(state)

    discovered: list[str] = []
    for item in CLUE_CATALOG:
        if item["id"] in known:
            discovered.append(item["label"])

    choices = list(state.flags.get("slice_choices") or [])[-12:]
    timeline = [
        {"turn": int(c.get("turn") or i + 1), "title": str(c.get("label") or "").strip()}
        for i, c in enumerate(choices)
        if isinstance(c, dict) and str(c.get("label") or "").strip()
    ]

    chapter = state.flags.get("seed_chapter")
    if not isinstance(chapter, dict):
        chapter = {"number": 1, "title": "失踪的商人"}

    ending_summary = str(copy.get("subtitle") or "").strip()
    body = str(copy.get("body") or "").strip()
    if body:
        import re as _re

        plain = _re.sub(r"<[^>]+>", " ", body)
        ending_summary = (ending_summary + " " + _re.sub(r"\s+", " ", plain).strip()).strip()

    def _npc_summary(name: str) -> dict[str, str]:
        val = _npc_attitude(state, name)
        if val >= 40:
            return {"name": name, "status": "信任", "detail": "愿意向你透露更多内情"}
        if val >= 15:
            return {"name": name, "status": "中立", "detail": "保持礼貌，有所保留"}
        return {"name": name, "status": "戒备", "detail": "尚未完全向你敞开心扉"}

    turns_played = int(state.flags.get("slice_turn_count") or 0)

    return {
        "chapter": chapter,
        "ending": {
            "title": copy.get("title", "未知结局"),
            "subtitle": copy.get("subtitle", ""),
            "epigraph": copy.get("epigraph", ""),
            "summary": ending_summary,
        },
        "ending_summary": ending_summary,
        "timeline": timeline,
        "clue_cards": [{"text": t} for t in discovered],
        "npc_relationships": [_npc_summary(name) for name in ROUTE_NPCS if name in state.npcs],
        "player_stats": {
            "turns": turns_played,
            "clues_found": len(discovered),
            "crisis_label": (
                "较低"
                if float(crisis.get("pressure", 0)) < 35
                else "紧张"
                if float(crisis.get("pressure", 0)) < 65
                else "危急"
            ),
        },
        "turns_played": turns_played,
    }


def package_chapter_complete_response(state: GameState) -> dict[str, Any]:
    return {
        "chapter_complete": True,
        "session_summary": build_session_summary(state),
    }

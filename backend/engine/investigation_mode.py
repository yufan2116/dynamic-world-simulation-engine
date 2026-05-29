"""《失踪的商人》调查游戏模式 — 6 回合、资源、线索、胜负（非开放叙事）。"""
from __future__ import annotations

from typing import Any

from engine.rule_engine import DiceRollInfo, RollOutcome, outcome_succeeds
from engine.world_state import GameState

MAX_TURNS = 6
INITIAL_STAMINA = 3
PRESSURE_PER_TURN = 10

KEY_CLUES: list[dict[str, str]] = [
    {"id": "clue_elena_last_seen", "label": "艾琳娜：父亲昨夜去了仓库"},
    {"id": "clue_patrol_anomaly", "label": "托马斯：昨夜巡逻异常"},
    {"id": "clue_mira_saw_guard", "label": "米拉：看见守卫深夜调动"},
    {"id": "clue_muddy_tracks", "label": "村口：泥泞脚印指向黑森林"},
    {"id": "clue_forest_trail", "label": "黑森林：马库斯被带往营地"},
]

ENDING_COPY: dict[str, dict[str, str]] = {
    "ending_rescue": {
        "title": "救出马库斯",
        "subtitle": "你在危机爆发前闯入了森林营地",
        "epigraph": "结局 A · 救援成功",
        "body": (
            "<p>绑匪尚未撤离。马库斯被麻绳捆在货箱后，意识模糊却仍活着。</p>"
            "<p class=\"dialogue\">「我以为……再也见不到艾琳娜了。」</p>"
            "<p>你把商人带回村口。艾琳娜扑进父亲怀里，托马斯第一次向你正式敬礼。</p>"
        ),
    },
    "ending_truth_dead": {
        "title": "真相大白，但太迟了",
        "subtitle": "你找到了马库斯，却只来得及合上他的眼睛",
        "epigraph": "结局 B · 商人遇难",
        "body": (
            "<p>森林营地只剩余火与血迹。马库斯的行囊在一旁，人却已无声息。</p>"
            "<p>艾琳娜跪在广场中央，发不出完整的句子。你知道真相，"
            "却再也无法把父亲还带给她。</p>"
        ),
    },
    "ending_buried": {
        "title": "真相被掩盖",
        "subtitle": "回合耗尽，村庄选择遗忘",
        "epigraph": "结局 C · 调查无果",
        "body": (
            "<p>托马斯宣布搜寻结束，米拉关上了酒馆后堂的门。"
            "艾琳娜被劝回家「静养」，她的问题被礼貌地打断。</p>"
            "<p><em>雷文福德恢复平静。平静得像马库斯从未存在过。</em></p>"
        ),
    },
    "ending_trap": {
        "title": "误入陷阱",
        "subtitle": "线索不足便闯入黑森林",
        "epigraph": "结局 D · 森林陷阱",
        "body": (
            "<p>林间的绊索猛然收紧。你摔进泥坑，耳边是强盗的哨声与笑声。</p>"
            "<p>当你挣扎着退回村口，马库斯的下落仍是一片迷雾——"
            "而村庄的耐心，已经耗尽。</p>"
        ),
    },
}

ACTION_DEFS: list[dict[str, Any]] = [
    {
        "id": "inv_ask_elena",
        "label": "询问艾琳娜父亲最后去向",
        "skill": "交涉",
        "category": "social",
        "ability": "WIS",
        "dc": 10,
        "location": "村口",
        "cost": "1 回合",
        "reward_hint": "关键线索：父亲最后去向",
        "risk_hint": "失败：艾琳娜信任 -1",
        "clue_id": "clue_elena_last_seen",
        "success_narrative": (
            "<p class=\"result\">艾琳娜哽咽着说：父亲昨夜答应去<strong>仓库</strong>清点货物，"
            "雨太大，再也没回来。</p>"
        ),
        "fail_narrative": (
            "<p class=\"result\">艾琳娜别过脸去，只能反复说「昨晚没回来」，给不出更多细节。</p>"
        ),
        "on_success": {"clue": "clue_elena_last_seen", "elena_trust": 1},
        "on_fail": {"elena_trust": -1},
    },
    {
        "id": "inv_ask_thomas",
        "label": "询问托马斯昨夜巡逻情况",
        "skill": "交涉",
        "category": "social",
        "ability": "CHA",
        "dc": 12,
        "location": "村口",
        "cost": "1 回合",
        "reward_hint": "关键线索：巡逻异常",
        "risk_hint": "失败：托马斯疑心 +1",
        "clue_id": "clue_patrol_anomaly",
        "success_narrative": (
            "<p class=\"result\">托马斯压低声音：昨夜<strong>旧仓库方向</strong>有人影，"
            "他已加派哨岗，但上面不让声张。</p>"
        ),
        "fail_narrative": (
            "<p class=\"result\">托马斯手按剑柄：「昨夜的事与你无关。」他不再开口。</p>"
        ),
        "on_success": {"clue": "clue_patrol_anomaly", "thomas_trust": 1},
        "on_fail": {"thomas_suspicion": 1},
    },
    {
        "id": "inv_observe_gate",
        "label": "检查村口泥地痕迹",
        "skill": "感知",
        "category": "investigate",
        "ability": "WIS",
        "dc": 11,
        "location": "村口",
        "cost": "1 回合",
        "reward_hint": "关键线索：泥泞脚印",
        "risk_hint": "失败：体力 -1",
        "clue_id": "clue_muddy_tracks",
        "success_narrative": (
            "<p class=\"result\">泥地里留着车辙与凌乱脚印，方向指向<strong>黑森林</strong>，"
            "边缘有拖拽痕迹。</p>"
        ),
        "fail_narrative": (
            "<p class=\"result\">雨水冲刷了大部分痕迹，你只能确认有人深夜经过村口。</p>"
        ),
        "on_success": {"clue": "clue_muddy_tracks"},
        "on_fail": {"stamina": -1},
    },
    {
        "id": "inv_tavern_mira",
        "label": "在酒馆向米拉打听消息",
        "skill": "交涉",
        "category": "social",
        "ability": "CHA",
        "dc": 11,
        "location": "酒馆",
        "cost": "1 回合",
        "reward_hint": "关键线索：米拉观察",
        "risk_hint": "失败：米拉信任 -1",
        "clue_id": "clue_mira_saw_guard",
        "success_narrative": (
            "<p class=\"result\">米拉凑近你：她看见<strong>守卫深夜调动</strong>，"
            "马库斯最后一趟也往仓库方向去了。</p>"
        ),
        "fail_narrative": (
            "<p class=\"result\">米拉摇头：「我现在没心情聊这个。」</p>"
        ),
        "on_success": {"clue": "clue_mira_saw_guard", "mira_trust": 1},
        "on_fail": {"mira_trust": -1},
    },
    {
        "id": "inv_go_forest",
        "label": "前往黑森林追踪下落",
        "skill": "行动",
        "category": "survival",
        "ability": "DEX",
        "dc": 0,
        "location": "森林小路",
        "cost": "1 回合",
        "reward_hint": "触发最终结局",
        "risk_hint": "需至少 3 条关键线索",
        "clue_id": "clue_forest_trail",
        "min_clues": 3,
        "requires_roll": False,
        "success_narrative": (
            "<p class=\"result\">你沿脚印深入黑森林，在营地边缘发现了被押送的商人——"
            "真相就在眼前。</p>"
        ),
        "fail_narrative": "",
    },
]

WAIT_ACTION_ID = "inv_wait"


def is_investigation_mode(state: GameState) -> bool:
    """调查模式已停用；统一使用 demo_story_mode + /game/new-demo。"""
    return False


def _inv(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("investigation")
    if not isinstance(raw, dict):
        raw = {}
        state.flags["investigation"] = raw
    return raw


def _sync_npc_attitudes_from_investigation(state: GameState) -> None:
    """将调查信任同步到 NPC 态度，供关系图与立绘展示。"""
    inv = _inv(state)
    mapping = {
        "托马斯": ("thomas_trust", "thomas_suspicion"),
        "艾琳娜": ("elena_trust", None),
        "米拉": ("mira_trust", None),
    }
    for name, (trust_key, susp_key) in mapping.items():
        npc = state.npcs.get(name)
        if not npc:
            continue
        trust = int(inv.get(trust_key, 0))
        susp = int(inv.get(susp_key or "", 0) or 0) if susp_key else 0
        npc.attitude_value = trust * 12 - susp * 8
        if trust >= 2:
            npc.attitude = "友好"
        elif trust >= 1:
            npc.attitude = "中立"
        elif susp >= 1:
            npc.attitude = "怀疑"
        else:
            npc.attitude = "警惕" if name == "托马斯" else "悲伤" if name == "艾琳娜" else "忧虑"


def init_investigation_game(state: GameState) -> None:
    raise RuntimeError("investigation_mode 已停用，请使用 POST /game/new-demo 启动演示")
    state.flags["investigation"] = {
        "remaining_turns": MAX_TURNS,
        "max_turns": MAX_TURNS,
        "stamina": INITIAL_STAMINA,
        "crisis_pressure": 22,
        "thomas_trust": 0,
        "elena_trust": 1,
        "mira_trust": 0,
        "thomas_suspicion": 0,
        "discovered_clues": [],
        "choices_log": [],
        "completed_actions": [],
        "seen_interactions": [],
    }
    state.location = "村口"
    crisis = state.flags.get("crisis")
    if isinstance(crisis, dict):
        crisis["pressure"] = 22.0
    _sync_npc_attitudes_from_investigation(state)


def get_discovered_clues(state: GameState) -> list[str]:
    inv = _inv(state)
    clues = inv.get("discovered_clues")
    return list(clues) if isinstance(clues, list) else []


def _add_clue(inv: dict[str, Any], clue_id: str) -> None:
    clues = inv.setdefault("discovered_clues", [])
    if clue_id not in clues:
        clues.append(clue_id)


def _clue_count(inv: dict[str, Any]) -> int:
    return len(inv.get("discovered_clues") or [])


def _apply_delta(inv: dict[str, Any], delta: dict[str, Any]) -> None:
    for key, val in delta.items():
        if key == "clue":
            _add_clue(inv, str(val))
            continue
        if key in inv and isinstance(val, int):
            inv[key] = int(inv.get(key, 0)) + val


def _site_action_ids() -> set[str]:
    return {str(a["id"]) for a in ACTION_DEFS if a["id"] != "inv_go_forest"}


def count_unlocked_investigation_actions(state: GameState) -> int:
    from engine.investigation_board import build_investigation_board

    board = build_investigation_board(state)
    return sum(
        1
        for ent in board.get("entities") or []
        for it in ent.get("interactions") or []
        if it.get("unlocked")
    )


def get_investigation_guidance(state: GameState) -> str:
    from engine.investigation_board import get_board_guidance

    return get_board_guidance(state)


def get_investigation_ui(state: GameState) -> dict[str, Any]:
    from engine.investigation_board import board_clues_for_ui, build_investigation_board

    inv = _inv(state)
    clues_ui = board_clues_for_ui(state)
    board = build_investigation_board(state)
    discovered = [c for c in clues_ui if c.get("found")]
    return {
        "remaining_turns": int(inv.get("remaining_turns", 0)),
        "max_turns": int(inv.get("max_turns", MAX_TURNS)),
        "stamina": int(inv.get("stamina", 0)),
        "crisis_pressure": int(inv.get("crisis_pressure", 0)),
        "thomas_trust": int(inv.get("thomas_trust", 0)),
        "elena_trust": int(inv.get("elena_trust", 0)),
        "mira_trust": int(inv.get("mira_trust", 0)),
        "thomas_suspicion": int(inv.get("thomas_suspicion", 0)),
        "clues_found": len(discovered),
        "clues_total": len(clues_ui),
        "clues": clues_ui,
        "chapter_complete": bool(state.flags.get("chapter_complete")),
        "guidance": get_investigation_guidance(state),
        "board": board,
    }


def _action_def(action_id: str) -> dict[str, Any] | None:
    for a in ACTION_DEFS:
        if a["id"] == action_id:
            return a
    return None


_LEGACY_INV_TO_INT = {
    "inv_ask_elena": "int_elena_father",
    "inv_ask_thomas": "int_thomas_patrol",
    "inv_observe_gate": "int_gate_mud",
    "inv_tavern_mira": "int_mira_gossip",
    "inv_go_forest": "int_forest_enter",
}


def resolve_investigation_action_id(
    *,
    action_id: str | None = None,
    intent_payload: dict[str, Any] | None = None,
    player_text: str = "",
) -> str | None:
    """解析调查行动 id（持久板 int_* 优先，兼容旧 inv_*）。"""
    from engine.investigation_board import resolve_board_action_id

    resolved = resolve_board_action_id(
        action_id=action_id,
        intent_payload=intent_payload,
        player_text=player_text,
    )
    if resolved:
        return resolved
    if action_id and str(action_id).startswith("inv_"):
        return _LEGACY_INV_TO_INT.get(str(action_id), str(action_id))
    if isinstance(intent_payload, dict):
        target = intent_payload.get("target")
        if target and str(target).startswith("inv_"):
            return _LEGACY_INV_TO_INT.get(str(target), str(target))
    return None


def build_investigation_actions(state: GameState) -> dict[str, Any]:
    """生成固定调查行动列表（含消耗/风险提示）。"""
    inv = _inv(state)
    completed = set(inv.get("completed_actions") or [])
    clue_count = _clue_count(inv)
    remaining = int(inv.get("remaining_turns", 0))
    stamina = int(inv.get("stamina", 0))
    done = bool(state.flags.get("chapter_complete"))

    grouped: dict[str, list[dict[str, Any]]] = {
        "social": [],
        "investigate": [],
        "survival": [],
    }
    labels = {
        "investigate": "调查",
        "social": "交涉",
        "stealth": "隐匿",
        "survival": "生存",
        "free": "自由",
    }

    for act in ACTION_DEFS:
        aid = act["id"]
        unlocked = True
        lock_reason = None
        if done:
            unlocked = False
            lock_reason = "章节已结束"
        elif remaining <= 0:
            unlocked = False
            lock_reason = "回合已用尽"
        elif aid in completed:
            unlocked = False
            lock_reason = "已调查过"
        elif aid == "inv_go_forest" and clue_count < int(act.get("min_clues", 3)):
            unlocked = False
            lock_reason = f"需要至少 {act.get('min_clues', 3)} 条关键线索（当前 {clue_count}）"
        elif stamina <= 0 and aid == "inv_observe_gate":
            unlocked = False
            lock_reason = "体力不足"

        skill = act.get("skill", "感知")
        label = f"[{skill}] {act['label']}"
        cat = str(act.get("category", "investigate"))
        entry = {
            "id": aid,
            "label": label,
            "input": act["label"],
            "category": cat,
            "description": f"消耗：{act.get('cost', '1 回合')}",
            "unlocked": unlocked,
            "lock_reason": lock_reason,
            "tags": [cat],
            "intent": {
                "action_type": "investigate" if cat == "investigate" else "talk",
                "target": aid,
                "ability": act.get("ability", "WIS"),
                "dc": act.get("dc", 12),
                "requires_roll": act.get("requires_roll", True),
            },
            "gameplay": {
                "cost": act.get("cost", "1 回合"),
                "reward": act.get("reward_hint", ""),
                "risk": act.get("risk_hint", ""),
            },
        }
        grouped.setdefault(cat, []).append(entry)

    flat = [a["input"] for arr in grouped.values() for a in arr if a.get("unlocked")]

    if not done and remaining > 0 and not flat:
        wait = {
            "id": WAIT_ACTION_ID,
            "label": "[生存] 暂缓调查，观望局势",
            "input": "暂缓调查，观望局势",
            "category": "survival",
            "description": "消耗 1 回合，危机压力上升",
            "unlocked": True,
            "lock_reason": None,
            "tags": ["survival"],
            "intent": {
                "action_type": "wait",
                "target": WAIT_ACTION_ID,
                "ability": "CON",
                "dc": 0,
                "requires_roll": False,
            },
            "gameplay": {},
        }
        grouped.setdefault("survival", []).append(wait)
        flat.append(wait["input"])

    return {
        "grouped": grouped,
        "category_labels": labels,
        "flat_inputs": flat,
    }


def evaluate_ending(state: GameState, *, forest_attempt: bool = False) -> str | None:
    if state.flags.get("chapter_ending_id"):
        return str(state.flags["chapter_ending_id"])

    inv = _inv(state)
    clues = _clue_count(inv)
    pressure = int(inv.get("crisis_pressure", 0))
    remaining = int(inv.get("remaining_turns", 0))

    if forest_attempt and clues < 3:
        return "ending_trap"

    if forest_attempt and clues >= 3:
        if clues >= 4 and pressure < 70:
            return "ending_rescue"
        return "ending_truth_dead"

    if remaining <= 0:
        if clues >= 4 and pressure < 70:
            return "ending_rescue"
        if clues >= 3:
            return "ending_truth_dead"
        return "ending_buried"

    return None


def apply_ending(state: GameState, ending_id: str) -> str:
    copy = ENDING_COPY.get(ending_id, ENDING_COPY["ending_buried"])
    state.flags["chapter_ending_id"] = ending_id
    state.flags["chapter_complete"] = True
    state.flags["game_phase"] = "chapter_complete"
    for q in state.quests:
        if q.id == "missing_merchant":
            q.status = "completed" if ending_id == "ending_rescue" else "failed"
    return (
        f"<div class=\"chapter-ending\">"
        f"<p class=\"chapter-epigraph\">{copy['epigraph']}</p>"
        f"<h2 class=\"ending-title\">{copy['title']}</h2>"
        f"<p class=\"ending-subtitle\"><em>{copy['subtitle']}</em></p>"
        f"{copy['body']}"
        f"</div>"
    )


def build_session_summary(state: GameState) -> dict[str, Any]:
    inv = _inv(state)
    ending_id = str(state.flags.get("chapter_ending_id") or "")
    copy = ENDING_COPY.get(ending_id, {})
    discovered_ids = set(get_discovered_clues(state))
    discovered = [c["label"] for c in KEY_CLUES if c["id"] in discovered_ids]
    missed = [c["label"] for c in KEY_CLUES if c["id"] not in discovered_ids]

    return {
        "chapter": state.flags.get("seed_chapter") or {"number": 1, "title": "失踪的商人"},
        "ending": {
            "id": ending_id,
            "title": copy.get("title", ""),
            "subtitle": copy.get("subtitle", ""),
            "epigraph": copy.get("epigraph", ""),
        },
        "key_choices": list(inv.get("choices_log") or [])[-12:],
        "clues": {"discovered": discovered, "missed": missed},
        "investigation_routes": [],
        "npc_relationships": [
            {"name": "托马斯", "attitude": "信任", "value": int(inv.get("thomas_trust", 0))},
            {"name": "艾琳娜", "attitude": "信任", "value": int(inv.get("elena_trust", 0))},
            {"name": "米拉", "attitude": "信任", "value": int(inv.get("mira_trust", 0))},
        ],
        "world_changes": [
            f"剩余回合：{inv.get('remaining_turns', 0)}/{inv.get('max_turns', MAX_TURNS)}",
            f"危机压力：{inv.get('crisis_pressure', 0)}",
            f"体力：{inv.get('stamina', 0)}",
            f"关键线索：{len(discovered)}/{len(KEY_CLUES)}",
            f"托马斯疑心：{inv.get('thomas_suspicion', 0)}",
        ],
        "turns_played": MAX_TURNS - int(inv.get("remaining_turns", 0)),
        "seed_id": state.flags.get("seed_id"),
        "investigation_final": get_investigation_ui(state),
    }


def resolve_investigation_action(
    state: GameState,
    action_id: str,
    *,
    succeeded: bool,
    player_label: str = "",
    turn: int = 0,
) -> dict[str, Any]:
    """执行一次调查行动，消耗回合，返回 changes + narrative 片段。"""
    inv = _inv(state)

    if action_id == WAIT_ACTION_ID:
        parts = [
            f'<p class="player-action">你选择：<strong>「{player_label or "暂缓调查，观望局势"}」</strong></p>',
            '<p class="scene">你在村口与酒馆之间徘徊，村民窃窃私语，'
            "黑森林方向的雾气越来越浓。</p>",
        ]
        inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
        inv["crisis_pressure"] = min(100, int(inv.get("crisis_pressure", 0)) + PRESSURE_PER_TURN)
        log = inv.setdefault("choices_log", [])
        log.append(
            {
                "turn": turn,
                "label": player_label or "暂缓调查",
                "success": True,
                "clues_after": _clue_count(inv),
            }
        )
        crisis = state.flags.get("crisis")
        if isinstance(crisis, dict):
            crisis["pressure"] = float(inv.get("crisis_pressure", 22))
        ending_id = evaluate_ending(state)
        if ending_id:
            parts.append(apply_ending(state, ending_id))
        return {
            "narrative": "\n".join(parts),
            "changes": {
                "investigation": dict(inv),
                "chapter_complete": bool(state.flags.get("chapter_complete")),
            },
            "ending_id": ending_id or state.flags.get("chapter_ending_id"),
        }

    act = _action_def(action_id)
    if not act:
        return {
            "narrative": "<p class=\"scene\">你无法执行该行动。</p>",
            "changes": {},
            "ending_id": None,
        }

    forest = action_id == "inv_go_forest"
    parts: list[str] = [
        f'<p class="player-action">你选择：<strong>「{player_label or act["label"]}」</strong></p>'
    ]

    if forest:
        clues = _clue_count(inv)
        if clues < 3:
            ending_id = evaluate_ending(state, forest_attempt=True)
            assert ending_id
            parts.append(act.get("fail_narrative") or "<p class=\"result\">线索不足，你在林中迷失了方向。</p>")
            parts.append(apply_ending(state, ending_id))
            inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
            return {
                "narrative": "\n".join(parts),
                "changes": {"investigation": dict(inv), "chapter_complete": True},
                "ending_id": ending_id,
            }
        _add_clue(inv, "clue_forest_trail")
        parts.append(act["success_narrative"])
        inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
        inv.setdefault("completed_actions", []).append(action_id)
        inv["crisis_pressure"] = min(100, int(inv.get("crisis_pressure", 0)) + PRESSURE_PER_TURN)
        ending_id = evaluate_ending(state, forest_attempt=True)
        if ending_id:
            parts.append(apply_ending(state, ending_id))
            return {
                "narrative": "\n".join(parts),
                "changes": {"investigation": dict(inv), "chapter_complete": True},
                "ending_id": ending_id,
            }

    # 常规行动：消耗回合
    inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
    inv.setdefault("completed_actions", []).append(action_id)
    inv["crisis_pressure"] = min(100, int(inv.get("crisis_pressure", 0)) + PRESSURE_PER_TURN)

    if succeeded:
        parts.append(act["success_narrative"])
        _apply_delta(inv, act.get("on_success") or {})
    else:
        parts.append(act.get("fail_narrative") or "<p class=\"result\">行动未能取得进展。</p>")
        _apply_delta(inv, act.get("on_fail") or {})

    if int(inv.get("stamina", 0)) < 0:
        inv["stamina"] = 0

    log = inv.setdefault("choices_log", [])
    log.append(
        {
            "turn": turn,
            "label": player_label or act["label"],
            "success": succeeded,
            "clues_after": _clue_count(inv),
        }
    )

    crisis = state.flags.get("crisis")
    if isinstance(crisis, dict):
        crisis["pressure"] = float(inv.get("crisis_pressure", 22))

    _sync_npc_attitudes_from_investigation(state)

    ending_id = evaluate_ending(state)
    if ending_id:
        parts.append(apply_ending(state, ending_id))

    pressure_line = int(inv.get("crisis_pressure", 0))
    if pressure_line >= 70 and not state.flags.get("chapter_complete"):
        parts.append('<p class="world">远处传来急促的哨声，黑森林里的局势正在恶化。</p>')
    elif int(inv.get("remaining_turns", 0)) <= 1 and not state.flags.get("chapter_complete"):
        parts.append('<p class="scene">时间所剩无几，你必须做出最后的选择。</p>')

    return {
        "narrative": "\n".join(parts),
        "changes": {
            "investigation": dict(inv),
            "check_succeeded": succeeded,
            "chapter_complete": bool(state.flags.get("chapter_complete")),
        },
        "ending_id": ending_id or state.flags.get("chapter_ending_id"),
    }


def action_requires_roll(action_id: str) -> tuple[str, int, bool]:
    if str(action_id).startswith("int_"):
        from engine.investigation_board import interaction_requires_roll

        return interaction_requires_roll(action_id)
    if action_id == WAIT_ACTION_ID:
        return "CON", 0, False
    act = _action_def(action_id)
    if not act:
        return "WIS", 12, True
    if act.get("requires_roll") is False:
        return str(act.get("ability", "WIS")), 0, False
    return str(act.get("ability", "WIS")), int(act.get("dc", 12)), True

"""作品集 Demo — 完全脚本化（不调用 LLM / action_generator / 世界模拟）。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine.demo_runner import blocks_to_html
from engine.narrative_formatter import format_narrative_html
from engine.rule_engine import DiceRollInfo, RollOutcome, dice_roll_to_dict
from engine.world_state import GameState

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "demo_scripts"
    / "ravenford_demo_script.json"
)
_CACHE: dict[str, Any] | None = None

_CATEGORY_LABELS = {
    "social": "社交",
    "investigate": "调查",
    "survival": "生存",
    "free": "自由",
}


class ScriptedDemoError(ValueError):
    """脚本 Demo 无效选项或节点。"""


def load_scripted_demo_script() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        with open(_SCRIPT_PATH, encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def is_scripted_demo_mode(state: GameState) -> bool:
    return bool(state.flags.get("scripted_demo_mode"))


def is_demo_story_mode(state: GameState) -> bool:
    """兼容旧名：脚本化 Demo。"""
    return is_scripted_demo_mode(state)


def _runtime(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("scripted_demo")
    if not isinstance(raw, dict):
        raw = {}
        state.flags["scripted_demo"] = raw
    return raw


def init_scripted_demo(state: GameState) -> None:
    script = load_scripted_demo_script()
    state.flags["scripted_demo_mode"] = True
    state.flags["demo_story_mode"] = True
    state.flags.pop("investigation_mode", None)
    state.flags["scripted_demo"] = {
        "script_id": script.get("id", "ravenford_demo"),
        "current_node": "start",
        "notebook": [],
        "timeline": [],
        "npc_trust": {"艾琳娜": 0, "托马斯": 0, "米拉": 0},
        "checks_passed": 0,
        "checks_failed": 0,
        "clue_count": 0,
        "turn": 1,
    }
    state.flags["seed_chapter"] = script.get("chapter") or {"number": 1, "title": "失踪的商人"}
    state.flags.pop("chapter_complete", None)
    state.flags.pop("chapter_ending_id", None)
    crisis = state.flags.setdefault("crisis", {})
    if isinstance(crisis, dict):
        crisis.setdefault("pressure", 22.0)
        crisis["merchant_status"] = "missing"


def _dice_from_node(preset: dict[str, Any] | None) -> DiceRollInfo | None:
    if not isinstance(preset, dict):
        return None
    raw = str(preset.get("result") or "success").lower()
    if raw in ("success", "critical_success"):
        outcome = RollOutcome.SUCCESS if raw != "critical_success" else RollOutcome.CRITICAL_SUCCESS
    elif raw in ("failure", "critical_failure"):
        outcome = RollOutcome.FAILURE if raw != "critical_failure" else RollOutcome.CRITICAL_FAILURE
    else:
        outcome = RollOutcome.SUCCESS
    ability = str(preset.get("ability") or "WIS").upper()
    natural = int(preset.get("roll") or 10)
    mod = int(preset.get("modifier") or 0)
    total = int(preset.get("total") or natural + mod)
    label = str(preset.get("label") or f"{ability} 检定")
    return DiceRollInfo(
        ability=ability,
        dc=int(preset.get("dc") or 10),
        die_roll=natural,
        modifier=mod,
        total=total,
        outcome=outcome,
        description=label,
    )


_TRUST_KEYS = {
    "elena_trust": "艾琳娜",
    "thomas_trust": "托马斯",
    "mira_trust": "米拉",
}

_NPC_RELATION_COPY: dict[str, list[tuple[int, str, str]]] = {
    "艾琳娜": [
        (0, "焦虑不安", "仍在广场等待父亲的消息"),
        (1, "愿意配合", "信任你的调查，愿意回忆细节"),
        (2, "深为感激", "你的坚持给了她希望"),
    ],
    "托马斯": [
        (0, "戒备观望", "以守卫职责为由保持沉默"),
        (1, "有所松动", "开始透露仓库方向的异常"),
        (2, "并肩协作", "愿意与你一同追查真相"),
    ],
    "米拉": [
        (0, "谨慎试探", "在酒馆里远远观察你"),
        (1, "低声相助", "愿意在角落分享所见所闻"),
        (2, "推心置腹", "把你当作可以托付情报的人"),
    ],
}


def _humanize_choice_label(label: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", str(label).strip())


def _dice_timeline_line(preset: dict[str, Any] | None) -> str | None:
    if not isinstance(preset, dict):
        return None
    label = str(preset.get("label") or "检定")
    total = preset.get("total")
    raw = str(preset.get("result") or "success").lower()
    outcome = "成功" if raw in ("success", "critical_success") else "失败"
    if total is not None:
        return f"{label} · {total}（{outcome}）"
    return f"{label}（{outcome}）"


def _crisis_label(pressure: float) -> str:
    if pressure < 30:
        return "较低"
    if pressure < 45:
        return "上升中"
    if pressure < 60:
        return "紧张"
    return "危急"


def _npc_relation_summary(name: str, trust: int) -> dict[str, str]:
    tiers = _NPC_RELATION_COPY.get(name) or [(0, "未知", "")]
    status, detail = tiers[0][1], tiers[0][2]
    for threshold, st, det in tiers:
        if trust >= threshold:
            status, detail = st, det
    return {"name": name, "status": status, "detail": detail}


def _apply_status(state: GameState, rt: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if not status:
        return changes
    clues_delta = int(status.get("clues") or 0)
    if clues_delta:
        rt["clue_count"] = int(rt.get("clue_count", 0)) + clues_delta
        changes["clue_count"] = rt["clue_count"]
    crisis = state.flags.setdefault("crisis", {})
    if isinstance(crisis, dict) and "crisis_pressure" in status:
        crisis["pressure"] = float(status["crisis_pressure"])
        changes["crisis_pressure"] = crisis["pressure"]
    trusts = rt.setdefault("npc_trust", {})
    if isinstance(trusts, dict):
        for key, npc_name in _TRUST_KEYS.items():
            if key in status:
                trusts[npc_name] = int(trusts.get(npc_name, 0)) + int(status[key])
    loc = status.get("location")
    if loc:
        state.location = str(loc)
        changes["moved_to"] = str(loc)
    return changes


def _merge_notebook(rt: dict[str, Any], lines: list[str]) -> None:
    nb = rt.setdefault("notebook", [])
    if not isinstance(nb, list):
        nb = []
        rt["notebook"] = nb
    for line in lines:
        t = str(line).strip()
        if t and t not in nb:
            nb.append(t)


def _sync_notebook_to_state(state: GameState, rt: dict[str, Any]) -> None:
    """供右侧状态栏展示的简化 knowledge（不驱动选项生成）。"""
    from engine.player_knowledge import ensure_player_knowledge

    pk = ensure_player_knowledge(state)
    pk["facts"] = [
        {"id": f"demo_note_{i}", "text": line, "source": "调查笔记"}
        for i, line in enumerate(rt.get("notebook") or [])
    ]
    pk["available_followups"] = []


def _choices_for_node(node: dict[str, Any]) -> list[dict[str, Any]]:
    raw = node.get("choices") or []
    return [c for c in raw if isinstance(c, dict) and c.get("id") and c.get("label")]


def choices_to_inline(choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inline: list[dict[str, Any]] = []
    for c in choices:
        cid = str(c.get("id", "")).strip()
        label = str(c.get("label", "")).strip()
        if not cid or not label:
            continue
        cat = "social"
        if label.startswith("[感知]") or "检查" in label or "观察" in label:
            cat = "investigate"
        elif label.startswith("[生存]") or "前往" in label:
            cat = "survival"
        inline.append(
            {
                "id": cid,
                "text": label,
                "input": label,
                "intent_payload": {"action_id": cid, "mode": "scripted_demo"},
                "category": cat,
                "risk": "low",
            }
        )
    return inline


def choices_to_action_data(choices: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "social": [],
        "investigate": [],
        "stealth": [],
        "survival": [],
        "free": [],
    }
    flat: list[str] = []
    for ch in choices_to_inline(choices):
        cat = str(ch.get("category") or "social")
        if cat not in grouped:
            cat = "social"
        grouped[cat].append(
            {
                "id": ch["id"],
                "label": ch["text"],
                "input": ch["input"],
                "category": cat,
                "intent": ch.get("intent_payload"),
                "unlocked": True,
            }
        )
        if cat != "free":
            flat.append(ch["input"])
    grouped["free"] = [
        {
            "id": "free_input",
            "label": "用你自己的话描述下一步……",
            "input": "",
            "category": "free",
            "unlocked": True,
        }
    ]
    return {
        "grouped": grouped,
        "category_labels": _CATEGORY_LABELS,
        "flat_inputs": flat[:8],
    }


def _build_session_summary(state: GameState, ending_id: str) -> dict[str, Any]:
    script = load_scripted_demo_script()
    copy = (script.get("endings") or {}).get(ending_id) or {}
    rt = _runtime(state)
    crisis = state.flags.get("crisis")
    pressure = float(crisis.get("pressure", 0)) if isinstance(crisis, dict) else 0.0
    notebook = list(rt.get("notebook") or [])
    summary_parts = [str(copy.get("subtitle") or "").strip()]
    for block in copy.get("blocks") or []:
        if isinstance(block, dict):
            text = str(block.get("text") or "").strip()
            if text:
                summary_parts.append(text)
    ending_summary = " ".join(p for p in summary_parts if p)
    trusts = rt.get("npc_trust") if isinstance(rt.get("npc_trust"), dict) else {}
    turns_played = max(0, int(rt.get("turn", 1)) - 1)
    return {
        "chapter": state.flags.get("seed_chapter") or script.get("chapter"),
        "ending": {
            "title": copy.get("title", ""),
            "subtitle": copy.get("subtitle", ""),
            "epigraph": copy.get("epigraph", ""),
            "summary": ending_summary,
        },
        "ending_summary": ending_summary,
        "timeline": list(rt.get("timeline") or []),
        "clue_cards": [{"text": line} for line in notebook],
        "npc_relationships": [
            _npc_relation_summary(name, int(trusts.get(name, 0)))
            for name in ("艾琳娜", "托马斯", "米拉")
        ],
        "player_stats": {
            "turns": turns_played,
            "clues_found": len(notebook),
            "checks_passed": int(rt.get("checks_passed", 0)),
            "checks_failed": int(rt.get("checks_failed", 0)),
            "crisis_label": _crisis_label(pressure),
        },
        "turns_played": turns_played,
    }


def get_opening_package(state: GameState) -> dict[str, Any]:
    script = load_scripted_demo_script()
    opening = script.get("opening") or {}
    blocks = opening.get("blocks") or []
    narrative = blocks_to_html(narrative_blocks=blocks, state=state)
    narrative = format_narrative_html(narrative, state)
    start = (script.get("nodes") or {}).get("start") or {}
    choices = _choices_for_node(start)
    inline = choices_to_inline(choices)
    action_data = choices_to_action_data(choices)
    return {
        "narrative": narrative,
        "inline_choices": inline,
        "choice_transition": str(script.get("choice_transition") or ""),
        "available_actions": action_data,
        "prologue": "",
    }


def resolve_scripted_choice_id(
    *,
    state: GameState,
    action_id: str | None = None,
    player_text: str = "",
) -> str | None:
    if not state or not is_scripted_demo_mode(state):
        return None
    aid = str(action_id or "").strip()
    if aid:
        return aid
    text = (player_text or "").strip()
    if not text:
        return None
    rt = _runtime(state)
    script = load_scripted_demo_script()
    node = (script.get("nodes") or {}).get(str(rt.get("current_node", "start"))) or {}
    for c in _choices_for_node(node):
        label = str(c.get("label", ""))
        if text == label or text in label or label in text:
            return str(c.get("id"))
    return None


def _resolve_next_node(rt: dict[str, Any], choice: dict[str, Any]) -> str:
    branch = choice.get("branch")
    if isinstance(branch, dict):
        need = int(branch.get("min_clues", 4))
        good = str(branch.get("good", ""))
        bad = str(branch.get("bad", ""))
        if int(rt.get("clue_count", 0)) >= need and good:
            return good
        if bad:
            return bad
    nxt = str(choice.get("next") or "").strip()
    if not nxt:
        raise ScriptedDemoError(f"选项缺少 next: {choice.get('id')}")
    return nxt


def process_scripted_demo_choice(
    state: GameState,
    choice_id: str,
    *,
    player_label: str = "",
    turn: int = 0,
) -> dict[str, Any]:
    if str(choice_id).strip() == "free_input":
        raise ScriptedDemoError("演示模式请从叙事选项中选择具体行动")

    script = load_scripted_demo_script()
    rt = _runtime(state)
    node_id = str(rt.get("current_node", "start"))
    nodes = script.get("nodes") or {}
    node = nodes.get(node_id)
    if not isinstance(node, dict):
        raise ScriptedDemoError(f"未知节点: {node_id}")

    choices = _choices_for_node(node)
    choice = next((c for c in choices if str(c.get("id")) == str(choice_id).strip()), None)
    if not choice:
        raise ScriptedDemoError(f"当前阶段无效选项: {choice_id}")

    next_id = _resolve_next_node(rt, choice)
    result_node = nodes.get(next_id)
    if not isinstance(result_node, dict):
        raise ScriptedDemoError(f"未知跳转节点: {next_id}")

    rt["current_node"] = next_id
    current_turn = int(rt.get("turn", 1))
    rt["turn"] = current_turn + 1

    dice_preset = result_node.get("dice") if isinstance(result_node.get("dice"), dict) else None
    notebook_lines = list(result_node.get("notebook") or [])
    timeline = rt.setdefault("timeline", [])
    if isinstance(timeline, list):
        entry: dict[str, Any] = {
            "turn": current_turn,
            "title": _humanize_choice_label(str(choice.get("label") or "")),
        }
        check_line = _dice_timeline_line(dice_preset)
        if check_line:
            entry["check"] = check_line
            raw = str((dice_preset or {}).get("result") or "success").lower()
            entry["check_success"] = raw in ("success", "critical_success")
            if entry["check_success"]:
                rt["checks_passed"] = int(rt.get("checks_passed", 0)) + 1
            else:
                rt["checks_failed"] = int(rt.get("checks_failed", 0)) + 1
        if notebook_lines:
            entry["clue"] = str(notebook_lines[-1])
        timeline.append(entry)

    status = result_node.get("status") if isinstance(result_node.get("status"), dict) else {}
    changes = _apply_status(state, rt, status)
    _merge_notebook(rt, list(result_node.get("notebook") or []))
    _sync_notebook_to_state(state, rt)

    ending_id = result_node.get("ending_id")
    ending_blocks: list[dict[str, Any]] = []
    session_summary = None
    if ending_id:
        state.flags["chapter_complete"] = True
        state.flags["chapter_ending_id"] = str(ending_id)
        state.flags["game_phase"] = "chapter_complete"
        ending_copy = (script.get("endings") or {}).get(str(ending_id)) or {}
        ending_blocks = list(ending_copy.get("blocks") or [])
        crisis = state.flags.get("crisis")
        if isinstance(crisis, dict):
            crisis["merchant_status"] = "resolved" if ending_id == "ending_good" else "dead"
        session_summary = _build_session_summary(state, str(ending_id))

    narrative = blocks_to_html(
        player_action_echo=str(result_node.get("player_action") or player_label or ""),
        narrative_blocks=result_node.get("blocks"),
        ending_blocks=ending_blocks,
        dice_preset=dice_preset,
        append_journal=True,
        state=state,
    )
    narrative = format_narrative_html(narrative, state)

    dice = _dice_from_node(dice_preset)
    next_choices = [] if ending_id else _choices_for_node(result_node)
    inline = choices_to_inline(next_choices)
    action_data = choices_to_action_data(next_choices)

    return {
        "narrative": narrative,
        "inline_choices": inline,
        "choice_transition": str(script.get("choice_transition") or "") if next_choices else "",
        "available_actions": action_data,
        "changes": changes,
        "dice": dice,
        "ending_id": ending_id,
        "session_summary": session_summary,
        "chapter_complete": bool(state.flags.get("chapter_complete")),
        "turn": rt.get("turn", turn),
    }


def get_scripted_state_package(state: GameState) -> dict[str, Any]:
    """get_state 用：当前节点选项，无新叙事。"""
    script = load_scripted_demo_script()
    rt = _runtime(state)
    if state.flags.get("chapter_complete"):
        return {
            "inline_choices": [],
            "choice_transition": "",
            "available_actions": {"grouped": {}, "category_labels": _CATEGORY_LABELS, "flat_inputs": []},
        }
    node_id = str(rt.get("current_node", "start"))
    node = (script.get("nodes") or {}).get(node_id) or {}
    choices = _choices_for_node(node)
    return {
        "inline_choices": choices_to_inline(choices),
        "choice_transition": str(script.get("choice_transition") or ""),
        "available_actions": choices_to_action_data(choices),
    }


# 兼容旧导入名
init_demo_story = init_scripted_demo
process_demo_action = process_scripted_demo_choice
resolve_demo_action_id = resolve_scripted_choice_id

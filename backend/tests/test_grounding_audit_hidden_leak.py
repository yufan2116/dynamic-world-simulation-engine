from __future__ import annotations

from engine.action_generator import generate_actions
from engine.crisis_escalation import get_crisis_ui
from engine.world_state import GameState, ensure_player_known_facts, NPCState
from engine.world_simulator import apply_world_simulation
from engine.intent_parser import ParsedIntent
from engine.narrative_beats import build_event_beats


FORBIDDEN = ("带划痕", "遗留物", "某处建筑", "失踪者留下", "追查线索")


def _all_action_texts(payload: dict) -> str:
    grouped = payload.get("grouped") or {}
    parts: list[str] = []
    for arr in grouped.values():
        if isinstance(arr, list):
            for a in arr:
                if isinstance(a, dict):
                    parts.append(str(a.get("label", "")))
                    parts.append(str(a.get("input", "")))
    return "\n".join(parts)


def test_opening_no_forbidden_leak_from_crisis_internal() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    # 模拟：crisis internal 写入可疑线索（隐藏）——不应进入 options
    state.flags["crisis"] = {"suspicious_clues": ["失踪者在某处建筑留下一枚带划痕的遗留物"]}
    payload = generate_actions(state)
    txt = _all_action_texts(payload)
    for w in FORBIDDEN:
        assert w not in txt


def test_no_follow_clue_before_discovered_fact() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    payload = generate_actions(state)
    txt = _all_action_texts(payload)
    assert "沿着你刚确认的现象继续追查" not in txt


def test_thomas_talk_returns_answer_or_reason() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    state.npcs["托马斯"] = NPCState(name="托马斯", location="村口", attitude="中立", present=True)
    intent = ParsedIntent(action_type="talk", target="托马斯", raw_input="向托马斯打听昨夜异常情况", ability="CHA", dc=12, requires_roll=False)
    changes = apply_world_simulation(state, intent, dice=None)
    beats = build_event_beats(state, intent.model_dump(), None, changes)
    # 必须有答复/反应/或解释原因
    assert beats.get("npc_reaction") or beats.get("consequence")


def test_elena_talk_returns_answer_or_reason() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    state.npcs["艾琳娜"] = NPCState(name="艾琳娜", location="村口", attitude="中立", present=True)
    intent = ParsedIntent(action_type="talk", target="艾琳娜", raw_input="友好地安慰艾琳娜，询问她父亲失踪的细节", ability="WIS", dc=10, requires_roll=False)
    changes = apply_world_simulation(state, intent, dice=None)
    beats = build_event_beats(state, intent.model_dump(), None, changes)
    assert beats.get("npc_reaction") or beats.get("consequence")


def test_crisis_ui_does_not_expose_internal_suspicious_clues() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    state.flags["crisis"] = {"suspicious_clues": ["马库斯在仓库留下一枚带划痕的银币"]}
    ui = get_crisis_ui(state)
    assert ui.get("suspicious_clues") == []


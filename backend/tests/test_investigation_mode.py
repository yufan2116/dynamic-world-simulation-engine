"""调查游戏模式 — 已停用（统一 demo_story_mode）。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="investigation_mode 已停用，请使用 test_demo_runner / test_demo_outcome_coverage")

from engine.investigation_mode import (
    resolve_investigation_action_id,
    build_investigation_actions,
    evaluate_ending,
    init_investigation_game,
    resolve_investigation_action,
)
from engine.seed_loader import load_seed_world


def _state():
    s = load_seed_world("ravenford_demo")
    init_investigation_game(s)
    return s


def test_init_has_six_turns():
    s = _state()
    inv = s.flags["investigation"]
    assert inv["remaining_turns"] == 6
    assert inv["stamina"] == 3


def test_ask_elena_grants_clue_on_success():
    s = _state()
    r = resolve_investigation_action(s, "inv_ask_elena", succeeded=True, turn=1)
    assert "clue_elena_last_seen" in s.flags["investigation"]["discovered_clues"]
    assert s.flags["investigation"]["remaining_turns"] == 5
    assert r["ending_id"] is None


def test_forest_trap_without_clues():
    s = _state()
    r = resolve_investigation_action(s, "inv_go_forest", succeeded=True, turn=1)
    assert r["ending_id"] == "ending_trap"
    assert s.flags["chapter_complete"]


def test_ending_rescue_conditions():
    s = _state()
    inv = s.flags["investigation"]
    inv["discovered_clues"] = [
        "clue_elena_last_seen",
        "clue_patrol_anomaly",
        "clue_muddy_tracks",
        "clue_mira_saw_guard",
    ]
    inv["crisis_pressure"] = 50
    assert evaluate_ending(s, forest_attempt=True) == "ending_rescue"


def test_actions_include_gameplay():
    s = _state()
    actions = build_investigation_actions(s)
    social = actions["grouped"].get("social") or []
    assert any(a.get("gameplay") for a in social)


def test_resolve_action_id_from_intent_target():
    assert (
        resolve_investigation_action_id(
            intent_payload={"target": "int_elena_father"},
            player_text="",
        )
        == "int_elena_father"
    )


def test_resolve_action_id_from_label():
    assert (
        resolve_investigation_action_id(
            player_text="[交涉] 询问父亲最后去向",
        )
        == "int_elena_father"
    )


def test_board_interactions_repeatable():
    from engine.investigation_board import build_investigation_board

    s = _state()
    b = build_investigation_board(s)
    thomas = next(e for e in b["entities"] if e["id"] == "npc_thomas")
    patrol = next(i for i in thomas["interactions"] if i["id"] == "int_thomas_patrol")
    assert patrol["unlocked"]

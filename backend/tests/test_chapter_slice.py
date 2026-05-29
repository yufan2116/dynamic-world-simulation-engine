"""Vertical Slice 结局触发与会话总结。"""
from __future__ import annotations

from engine.chapter_slice import (
    apply_chapter_ending,
    build_session_summary,
    evaluate_chapter_ending,
    track_slice_turn,
)
from engine.crisis_escalation import _ensure_crisis
from engine.seed_loader import load_seed_world


def _demo_state():
    state = load_seed_world("ravenford_demo")
    state.flags["vertical_slice_demo"] = True
    return state


def test_track_routes_on_talk():
    state = _demo_state()
    track_slice_turn(
        state,
        {"action_type": "talk", "target": "托马斯"},
        {"check_succeeded": True},
        player_action_display="询问托马斯昨夜异常",
        turn=1,
    )
    assert state.flags["slice_routes"]["thomas"] >= 1


def test_rescue_ending_conditions():
    state = _demo_state()
    crisis = _ensure_crisis(state)
    crisis["investigation_score"] = 25
    crisis["merchant_status"] = "injured"
    crisis["pressure"] = 50
    state.flags["slice_routes"] = {"thomas": 2, "mira": 2, "elena": 1}
    state.flags["clue_found"] = True
    state.flags["slice_turn_count"] = 10
    ending = evaluate_chapter_ending(state, 10)
    assert ending == "rescue_success"


def test_apply_ending_and_summary():
    state = _demo_state()
    html = apply_chapter_ending(state, "rescue_success")
    assert "马库斯" in html
    assert state.flags["chapter_complete"] is True
    summary = build_session_summary(state)
    assert summary["ending"]["title"]
    assert summary.get("timeline") is not None
    assert summary.get("clue_cards") is not None
    assert summary.get("player_stats")

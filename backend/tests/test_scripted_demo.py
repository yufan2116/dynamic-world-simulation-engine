"""Fully scripted demo — ravenford_demo_script.json。"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from engine.scripted_demo_runner import (
    get_opening_package,
    init_scripted_demo,
    load_scripted_demo_script,
    process_scripted_demo_choice,
)
from engine.game_loop import game_loop
from engine.seed_loader import load_seed_world


def _state():
    s = load_seed_world("ravenford_demo")
    init_scripted_demo(s)
    return s


def _choice_ids(state, node_id: str) -> list[str]:
    script = load_scripted_demo_script()
    node = script["nodes"][node_id]
    return [str(c["id"]) for c in node.get("choices") or []]


def _choice_labels(state, node_id: str) -> list[str]:
    script = load_scripted_demo_script()
    node = script["nodes"][node_id]
    return [str(c["label"]) for c in node.get("choices") or []]


def test_demo_start_returns_at_least_four_choices():
    s = _state()
    pkg = get_opening_package(s)
    assert len(pkg.get("inline_choices") or []) >= 4


def test_ask_elena_last_seen_unlocks_ask_elena_cargo():
    s = _state()
    process_scripted_demo_choice(s, "ask_elena_last_seen", turn=1)
    rt = s.flags["scripted_demo"]
    assert rt["current_node"] == "after_ask_elena_last_seen"
    assert "ask_elena_cargo" in _choice_ids(s, rt["current_node"])


def test_after_ask_elena_cargo_no_ask_elena_last_seen():
    s = _state()
    process_scripted_demo_choice(s, "ask_elena_last_seen", turn=1)
    process_scripted_demo_choice(s, "ask_elena_cargo", turn=2)
    rt = s.flags["scripted_demo"]
    assert rt["current_node"] == "after_ask_elena_cargo"
    assert "ask_elena_last_seen" not in _choice_ids(s, rt["current_node"])


def test_thomas_last_seen_and_patrol_have_different_blocks():
    script = load_scripted_demo_script()
    a = script["nodes"]["after_ask_thomas_last_seen"]["blocks"]
    b = script["nodes"]["after_ask_thomas_patrol"]["blocks"]
    assert json.dumps(a, ensure_ascii=False) != json.dumps(b, ensure_ascii=False)


def test_no_duplicate_labels_within_nodes():
    script = load_scripted_demo_script()
    for node_id, node in (script.get("nodes") or {}).items():
        labels = _choice_labels(None, node_id)
        assert len(labels) == len(set(labels)), f"duplicate label in node {node_id}"


def test_demo_does_not_call_action_generator():
    async def _run():
        with patch("engine.game_loop.generate_actions") as gen:
            gen.side_effect = AssertionError("Demo must not call generate_actions")
            await game_loop.start_new_demo_game("ravenford_demo")
            game_loop._action_id = "ask_elena_last_seen"
            await game_loop.process_action("")

    asyncio.run(_run())


def test_demo_does_not_call_llm_narrative():
    async def _run():
        with patch("engine.game_loop.generate_narrative") as llm:
            llm.side_effect = AssertionError("Demo must not call LLM narrative")
            await game_loop.start_new_demo_game("ravenford_demo")
            game_loop._action_id = "ask_elena_last_seen"
            await game_loop.process_action("")

    asyncio.run(_run())


def test_success_route_reaches_ending_good():
    s = _state()
    route = [
        "ask_elena_last_seen",
        "ask_elena_cargo",
        "ask_thomas_last_seen",
        "inspect_mud",
        "go_warehouse",
        "go_forest",
    ]
    for i, cid in enumerate(route, start=1):
        r = process_scripted_demo_choice(s, cid, turn=i)
    assert s.flags.get("chapter_ending_id") == "ending_good"
    assert r.get("chapter_complete") is True


def test_early_go_forest_reaches_ending_bad():
    s = _state()
    process_scripted_demo_choice(s, "inspect_mud", turn=1)
    r = process_scripted_demo_choice(s, "go_forest", turn=2)
    assert s.flags.get("chapter_ending_id") == "ending_bad"
    assert r.get("chapter_complete") is True


def test_session_summary_is_player_facing():
    s = _state()
    route = [
        "ask_elena_last_seen",
        "ask_elena_cargo",
        "ask_thomas_last_seen",
        "inspect_mud",
        "go_warehouse",
        "go_forest",
    ]
    summary = None
    for i, cid in enumerate(route, start=1):
        r = process_scripted_demo_choice(s, cid, turn=i)
        summary = r.get("session_summary")
    assert summary is not None
    blob = json.dumps(summary, ensure_ascii=False)
    for forbidden in ("ask_elena", "go_forest", "go_warehouse", "action_id", "after_"):
        assert forbidden not in blob, f"debug token leaked: {forbidden}"
    assert summary.get("timeline")
    assert all("title" in t for t in summary["timeline"])
    assert summary.get("clue_cards")
    assert summary.get("player_stats")

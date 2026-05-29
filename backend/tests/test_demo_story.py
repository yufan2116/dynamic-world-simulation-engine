"""Demo 集成 — fully scripted demo。"""
from __future__ import annotations

import asyncio

from engine.scripted_demo_runner import (
    get_scripted_state_package,
    init_scripted_demo,
    is_scripted_demo_mode,
    process_scripted_demo_choice,
)
from engine.game_loop import game_loop
from engine.seed_loader import load_seed_world


def test_demo_init_scripted_no_generate_actions():
    s = load_seed_world("ravenford_demo")
    init_scripted_demo(s)
    assert is_scripted_demo_mode(s)
    pkg = get_scripted_state_package(s)
    assert len(pkg.get("inline_choices") or []) >= 4


def test_demo_game_loop():
    async def _run():
        resp = await game_loop.start_new_demo_game("ravenford_demo")
        assert resp.get("game_mode") == "demo"
        assert len(resp.get("inline_choices") or []) >= 4
        game_loop._action_id = "ask_elena_last_seen"
        act = await game_loop.process_action("")
        assert act.get("dice_roll_info")
        assert len(act.get("inline_choices") or []) >= 2

    asyncio.run(_run())


def test_process_demo_returns_scripted_choices():
    s = load_seed_world("ravenford_demo")
    init_scripted_demo(s)
    r = process_scripted_demo_choice(s, "ask_elena_last_seen", turn=1)
    assert "available_actions" in r
    assert len(r.get("available_actions", {}).get("flat_inputs") or []) >= 2

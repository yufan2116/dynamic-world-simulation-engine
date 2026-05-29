"""Action Execution Pipeline — action_id 直达 resolver，禁止误走仓库 fallback。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from engine.action_pipeline import build_intent_async, run_action_simulation
from engine.action_resolvers import execute_registered_action, registry_table
from engine.intent_parser import ParsedIntent
from engine.rule_engine import DiceRollInfo, RollOutcome
from engine.world_state import GameState, NPCState, ensure_player_known_facts


def _dice(success: bool) -> DiceRollInfo:
    return DiceRollInfo(
        outcome=RollOutcome.SUCCESS if success else RollOutcome.FAILURE,
        die_roll=10,
        modifier=0,
        total=10 if success else 5,
        ability="WIS",
        dc=12,
        description="test",
    )


def test_observe_mira_no_warehouse_leak() -> None:
    state = GameState(location="村口")
    intent = {
        "action_type": "observe",
        "target": "mira",
        "fact_id": "pf_mira_observing",
    }
    reg = execute_registered_action(state, "observe_mira_at_tavern", intent, _dice(True))
    blob = str(reg.get("beats", {}))
    for bad in ("仓库", "麻袋", "谷物", "脚步声"):
        assert bad not in blob
    assert "米拉" in blob or "门帘" in blob


def test_ask_elena_no_warehouse_leak() -> None:
    state = GameState(location="村口")
    state.npcs["艾琳娜"] = NPCState(
        name="艾琳娜", location="村口", attitude="中立", present=True
    )
    intent = {"action_type": "talk", "target": "艾琳娜", "topic": "父亲失踪"}
    reg = execute_registered_action(state, "ask_elena_father_details", intent, _dice(True))
    blob = str(reg.get("beats", {})) + str(reg.get("changes", {}))
    for bad in ("麻袋", "谷物", "仓库脚步声"):
        assert bad not in blob
    assert "艾琳娜" in blob or "父亲" in blob


def test_ask_thomas_contains_thomas() -> None:
    state = GameState(location="村口")
    state.npcs["托马斯"] = NPCState(
        name="托马斯", location="村口", attitude="中立", present=True
    )
    intent = {"action_type": "talk", "target": "托马斯", "topic": "昨夜异常"}
    reg = execute_registered_action(state, "ask_thomas_last_night", intent, _dice(False))
    blob = str(reg.get("beats", {}))
    assert "托马斯" in blob
    assert "麻袋" not in blob


def test_selected_action_skips_intent_parser() -> None:
    async def _run() -> None:
        with patch("engine.action_pipeline.parse_intent", new_callable=AsyncMock) as mock_parse:
            intent, meta = await build_intent_async(
                player_input="",
                choice_text="观察米拉",
                action_id="observe_mira_at_tavern",
                intent_payload={"action_type": "observe", "target": "mira"},
                context={},
            )
            mock_parse.assert_not_called()
            assert meta["parse_path"] == "intent_payload"
            assert intent.parse_source == "selected_action"

    asyncio.run(_run())


def test_unimplemented_action_no_world_story() -> None:
    state = GameState()
    intent = ParsedIntent(action_type="investigate", target="unknown_thing", requires_roll=False)
    changes = run_action_simulation(
        state, intent, None, action_id="totally_unknown_action_xyz"
    )
    assert changes.get("unimplemented_action")
    assert "还没有实现" in str(changes.get("resolver_beats", {}).get("direct_result", ""))
    assert "麻袋" not in str(changes)


def test_registry_table_has_core_ids() -> None:
    table = registry_table()
    assert "observe_mira_at_tavern" in table
    assert "ask_thomas_last_night" in table


def test_follow_mira_fact_routes_to_mira_resolver() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    intent = {"action_type": "investigate", "target": "player_facing_fact", "fact_id": "pf_mira_observing"}
    reg = execute_registered_action(state, "follow_pf_mira_observing", intent, _dice(True))
    assert "米拉" in str(reg.get("beats", {})) or "门帘" in str(reg.get("beats", {}))

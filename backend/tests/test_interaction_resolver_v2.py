"""Simulation Architecture V2 — universal interaction resolver tests."""

from __future__ import annotations

from unittest.mock import patch

from engine.action_id_adapter import ADAPTER_TABLE, adapt_action_id
from engine.action_resolvers import execute_registered_action, resolve_observe_mira_at_tavern
from engine.action_generator import generate_actions
from engine.interaction_resolver import resolve_interaction, resolve_observe_target
from engine.npc_state import ensure_npc_states, get_npc_state, get_player_relationship
from engine.player_knowledge import apply_action_result, ensure_player_knowledge, get_player_knowledge
from engine.rule_engine import DiceRollInfo, RollOutcome
from engine.topic_resolver import register_player_topic
from engine.world_state import GameState, NPCState


def _scene() -> dict:
    return {"location": "村口", "player_visible": {"location": "村口", "active_events": []}}


def _setup_gate_npc(state: GameState) -> None:
    state.location = "村口"
    state.npcs["托马斯"] = NPCState(name="托马斯", location="村口", attitude="中立", present=True)
    state.npcs["艾琳娜"] = NPCState(name="艾琳娜", location="村口", attitude="中立", present=True)
    ensure_npc_states(state)


def test_same_topic_different_npcs_different_answers() -> None:
    state = GameState()
    _setup_gate_npc(state)
    pk = ensure_player_knowledge(state)

    thomas = resolve_interaction(
        "player",
        "thomas",
        {"topic_id": "last_night_disturbance"},
        _scene(),
        pk,
        state,
        interaction_type="ask_about_topic",
        topic_id="last_night_disturbance",
        dice=None,
    )
    elena = resolve_interaction(
        "player",
        "elena",
        {"topic_id": "missing_father"},
        _scene(),
        pk,
        state,
        interaction_type="ask_about_topic",
        topic_id="missing_father",
        dice=None,
    )
    t_text = " ".join(b.get("text", "") for b in thomas.get("narrative_blocks", []))
    e_text = " ".join(b.get("text", "") for b in elena.get("narrative_blocks", []))
    assert "昨夜" in t_text or "动静" in t_text
    assert "父亲" in e_text or "仓库" in e_text
    assert t_text != e_text


def test_thomas_low_trust_extra_patrol_surface_only() -> None:
    state = GameState()
    _setup_gate_npc(state)
    pk = ensure_player_knowledge(state)
    npc = get_npc_state(state, "thomas")
    assert npc
    npc["relationships"]["player"] = {"trust": 5, "suspicion": 35, "attitude": "neutral"}

    out = resolve_interaction(
        "player",
        "thomas",
        {},
        _scene(),
        pk,
        state,
        interaction_type="ask_about_topic",
        topic_id="extra_patrol",
        dice=DiceRollInfo(
            ability="CHA",
            modifier=0,
            die_roll=5,
            total=5,
            dc=12,
            outcome=RollOutcome.FAILURE,
            description="ask",
        ),
    )
    blob = " ".join(b.get("text", "") for b in out.get("narrative_blocks", []))
    assert "例行" in blob or "别多想" in blob or "巡逻" in blob
    assert "走私" not in blob


def test_thomas_high_trust_reveals_deeper_extra_patrol() -> None:
    state = GameState()
    _setup_gate_npc(state)
    pk = ensure_player_knowledge(state)
    npc = get_npc_state(state, "thomas")
    assert npc
    npc["relationships"]["player"] = {"trust": 50, "suspicion": 10, "attitude": "friendly"}

    out = resolve_interaction(
        "player",
        "thomas",
        {},
        _scene(),
        pk,
        state,
        interaction_type="ask_about_topic",
        topic_id="extra_patrol",
        dice=DiceRollInfo(
            ability="CHA",
            modifier=2,
            die_roll=15,
            total=17,
            dc=12,
            outcome=RollOutcome.SUCCESS,
            description="ask",
        ),
    )
    blob = " ".join(b.get("text", "") for b in out.get("narrative_blocks", []))
    assert "走私" in blob or "劫" in blob or "巡逻" in blob


def test_observe_mira_uses_generic_resolver_not_legacy_body() -> None:
    state = GameState()
    state.npcs["米拉"] = NPCState(name="米拉", location="酒馆", attitude="中立", present=True)
    ensure_npc_states(state)
    pk = ensure_player_knowledge(state)

    with patch("engine.interaction_resolver.run_universal_resolution") as mock_run:
        from engine.interaction_resolver import interaction_result_to_pipeline, resolve_observe_target

        interaction = resolve_observe_target(
            "mira", "npc", _scene(), pk, state, None
        )
        mock_run.return_value = interaction_result_to_pipeline(
            interaction, resolver_name="interaction_resolver.observe", check_succeeded=True
        )
        resolve_observe_mira_at_tavern(state, {}, None, "observe_mira_at_tavern")
        assert mock_run.called

    failed = DiceRollInfo(
        ability="WIS",
        modifier=0,
        die_roll=2,
        total=2,
        dc=12,
        outcome=RollOutcome.FAILURE,
        description="observe",
    )
    reg = execute_registered_action(state, "observe_mira_at_tavern", {"target": "mira"}, failed)
    assert "interaction_resolver" in str(reg.get("resolver_name", ""))
    ar = reg.get("action_result") or {}
    assert any(
        f.get("id", "").startswith("change_angle_observe")
        for f in ar.get("available_followups", [])
    )


def test_legacy_action_id_adapter_mapping() -> None:
    p = adapt_action_id("ask_thomas_last_night", {})
    assert p
    assert p["target_npc_id"] == "thomas"
    assert p["topic_id"] == "last_night_disturbance"
    assert p["interaction_type"] == "ask_about_topic"
    assert ADAPTER_TABLE["observe_mira_at_tavern"]["interaction_type"] == "observe"


def test_npc_trust_suspicion_change_after_interaction() -> None:
    state = GameState()
    _setup_gate_npc(state)
    pk = ensure_player_knowledge(state)
    npc = get_npc_state(state, "thomas")
    assert npc
    npc["relationships"]["player"] = {"trust": 0, "suspicion": 40, "attitude": "neutral"}
    before = get_player_relationship(npc)["trust"]

    out = resolve_interaction(
        "player",
        "thomas",
        {},
        _scene(),
        pk,
        state,
        interaction_type="ask_about_topic",
        topic_id="last_night_disturbance",
        dice=DiceRollInfo(
            ability="CHA",
            modifier=0,
            die_roll=3,
            total=3,
            dc=12,
            outcome=RollOutcome.FAILURE,
            description="ask",
        ),
    )
    from engine.npc_state import apply_npc_state_changes

    apply_npc_state_changes(state, out.get("npc_state_changes") or [])
    after = get_player_relationship(get_npc_state(state, "thomas") or {})["trust"]
    assert after != before or out.get("npc_state_changes")


def test_known_topic_generates_verify_option() -> None:
    state = GameState()
    _setup_gate_npc(state)
    pk = ensure_player_knowledge(state)
    register_player_topic(pk, "last_night_disturbance")
    pk["observations"].append(
        {
            "id": "obs_player_heard_noise",
            "text": "你听见昨夜村口外侧有动静",
            "source": "player_observation",
        }
    )
    state.flags["last_scene_graph"] = {
        "location": "村口",
        "active_events": [],
        "visible_npcs": [{"name": "托马斯"}, {"name": "艾琳娜"}],
    }
    payload = generate_actions(state)
    labels = []
    for arr in (payload.get("grouped") or {}).values():
        if isinstance(arr, list):
            for a in arr:
                if isinstance(a, dict) and a.get("label"):
                    labels.append(str(a["label"]))
    assert any("verify_last_night" in str(a.get("id", "")) for arr in (payload.get("grouped") or {}).values() if isinstance(arr, list) for a in arr if isinstance(a, dict))

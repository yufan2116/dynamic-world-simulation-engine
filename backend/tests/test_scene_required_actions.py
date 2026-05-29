from __future__ import annotations

from engine.action_generator import generate_actions
from engine.world_state import GameState, ensure_player_known_facts


def _ids(payload: dict) -> set[str]:
    out: set[str] = set()
    grouped = payload.get("grouped") or {}
    for arr in grouped.values():
        if isinstance(arr, list):
            for a in arr:
                if isinstance(a, dict) and a.get("id"):
                    out.add(str(a["id"]))
    return out


def test_no_private_conversation_no_eavesdrop() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    state.flags["opening_scene"] = True
    state.flags["guards_private_conversation"] = False
    # 没有 last_scene_graph.active_events → 不应生成 eavesdrop_guards
    state.flags["last_scene_graph"] = {"active_events": []}
    payload = generate_actions(state)
    assert "eavesdrop_guards" not in _ids(payload)


def test_thomas_order_event_allows_hear_order() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    # 让生成器认为“托马斯正在下令”（最小条件）
    state.flags["guard_patrol_active"] = True
    # 托马斯必须“可见”
    from engine.world_state import NPCState
    state.npcs["托马斯"] = NPCState(name="托马斯", location="村口", attitude="中立", present=True)
    state.flags["last_scene_graph"] = {"active_events": [{"id": "thomas_calling_extra_patrol"}]}
    payload = generate_actions(state)
    assert "hear_thomas_order" in _ids(payload)


def test_consumed_action_not_repeat() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    state.flags["last_scene_graph"] = {"active_events": [{"id": "thomas_calling_extra_patrol"}]}
    state.flags["consumed_actions"] = ["hear_thomas_order"]
    payload = generate_actions(state)
    assert "hear_thomas_order" not in _ids(payload)


def test_known_clue_creates_followup_action() -> None:
    state = GameState()
    facts = ensure_player_known_facts(state)
    facts["player_facing_facts"].append(
        {"id": "pf_clue_marked_relic", "type": "clue", "text": "带划痕的遗留物", "visibility": "discovered", "introduced_in_narrative": True}
    )
    state.flags["last_scene_graph"] = {"active_events": []}
    state.flags["consumed_actions"] = []
    payload = generate_actions(state)
    ids = _ids(payload)
    assert any(i.startswith("follow_") for i in ids)


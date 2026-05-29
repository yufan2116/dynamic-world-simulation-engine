"""Narrative / Action Grounding — placeholder、rumor 来源、托马斯、截断句。"""

from __future__ import annotations

from engine.action_generator import generate_actions
from engine.grounding import filter_actions_payload
from engine.location_registry import resolve_direction_phrase
from engine.npc_interaction import resolve_npc_interaction
from engine.text_sanitizer import (
    FORBIDDEN_SUBSTRINGS,
    build_rumor_action_label,
    contains_forbidden,
    is_truncated,
    rumor_source_type_allowed,
    sanitize_player_text,
)
from engine.world_state import GameState, NPCState, ensure_player_known_facts


def _flat_labels(payload: dict) -> list[str]:
    out: list[str] = []
    for arr in (payload.get("grouped") or {}).values():
        if isinstance(arr, list):
            for a in arr:
                if isinstance(a, dict) and a.get("label"):
                    out.append(str(a["label"]))
    return out


def test_no_placeholder_in_sanitizer() -> None:
    state = GameState()
    for bad in ("某个方向东侧", "商人失踪者", "方向方向", "世界：米"):
        assert sanitize_player_text(bad, state) == ""
    assert sanitize_player_text("村口外侧加派双哨", state) == "村口外侧加派双哨"


def test_rumor_option_rejects_location_source() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    facts = state.flags["player_known_facts"]
    facts["known_rumors"] = [
        {
            "id": "r1",
            "text": "昨夜有打斗声",
            "source_type": "location",
            "source_label": "村口",
        }
    ]
    payload = generate_actions(state)
    labels = _flat_labels(filter_actions_payload(payload, state))
    assert not any("村口" in lb and "打听" in lb for lb in labels)
    assert not any("有人说" in lb for lb in labels)


def test_rumor_action_label_is_action_oriented() -> None:
    rumor = {
        "source_type": "npc",
        "source_label": "米拉",
        "text": "黑森林商队失踪",
    }
    label = build_rumor_action_label(rumor)
    assert "打听：" not in label
    assert label.startswith("询问米拉")


def test_thomas_withheld_uses_village_outer_not_placeholder() -> None:
    state = GameState()
    state.npcs["托马斯"] = NPCState(name="托马斯", location="村口", attitude="中立", present=True)
    out = resolve_npc_interaction(
        state, "托马斯", "昨夜异常", succeeded=False, raw_input="昨夜异常"
    )
    assert "某个方向" not in (out.get("npc_answer") or "")
    assert out.get("reason") in ("relationship_too_low", "topic_sensitive", "no_knowledge", None)
    phrase = resolve_direction_phrase(state, "warehouse")
    assert phrase == "村口外侧"
    assert "某个方向" not in phrase


def test_after_hear_thomas_order_followup_not_generic_rumor() -> None:
    from engine.player_knowledge import ensure_player_knowledge

    state = GameState()
    state.location = "村口"
    state.flags["guard_patrol_active"] = True
    state.flags["last_scene_graph"] = {"active_events": [{"id": "thomas_calling_extra_patrol"}]}
    state.flags["consumed_actions"] = ["hear_thomas_order"]
    state.flags["heard_thomas_order"] = True
    state.npcs["托马斯"] = NPCState(name="托马斯", location="村口", attitude="中立", present=True)
    pk = ensure_player_knowledge(state)
    pk["observations"].append(
        {
            "id": "fact_thomas_extra_patrol",
            "text": "托马斯正在加派村口外侧哨岗",
            "source": "npc_order",
        }
    )
    payload = filter_actions_payload(generate_actions(state), state)
    labels = _flat_labels(payload)
    assert any(
        "托马斯" in lb and ("仓库" in lb or "巡逻" in lb or "追问" in lb)
        for lb in labels
    )
    assert not any("向村口打听" in lb for lb in labels)


def test_world_event_not_single_char_or_truncated() -> None:
    assert is_truncated("米")
    assert is_truncated("泥泞")
    assert not is_truncated("村口外侧传来短促撞击声。")


def test_forbidden_substrings_list_covers_audit_terms() -> None:
    for term in ("某个方向", "unknown", "商人失踪者"):
        assert term in FORBIDDEN_SUBSTRINGS
    assert rumor_source_type_allowed("npc")
    assert not rumor_source_type_allowed("location")

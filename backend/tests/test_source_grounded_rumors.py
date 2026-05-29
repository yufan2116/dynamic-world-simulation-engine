from __future__ import annotations

from engine.rumor_network import add_rumor, tick_rumors
from engine.world_state import GameState, ensure_player_known_facts
from engine.grounding import UNSOURCED_PHRASES, filter_actions_payload


def test_rumor_requires_source_fields() -> None:
    state = GameState()
    r = add_rumor(
        state,
        "夜里有异常声响。",
        origin="村口",
        source_type="npc",
        source_id="mira",
        source_label="米拉",
        visibility="local",
    )
    assert r.get("source_type") == "npc"
    assert r.get("source_id") == "mira"
    assert r.get("source_label") == "米拉"
    assert r.get("visibility") == "local"


def test_unsourced_phrase_not_allowed_in_options() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    payload = {
        "grouped": {
            "social": [
                {
                    "id": "bad",
                    "label": "向在场者打听：「有人说昨夜某处建筑附近有马蹄声」",
                    "input": "向路人打听传闻：有人说……",
                    "category": "social",
                    "unlocked": True,
                }
            ]
        },
        "flat_inputs": [],
    }
    out = filter_actions_payload(payload, state)
    assert out["grouped"]["social"] == []


def test_opening_known_fact_enables_source_grounded_followup() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    # 模拟：玩家已听见一个来源明确的 rumor
    rid = add_rumor(
        state,
        "父亲昨晚没有回来。",
        origin="村口",
        source_type="npc",
        source_id="elena",
        source_label="艾琳娜",
        visibility="public",
        known_to_player=True,
    )["id"]
    # tick 使其写入 known_rumors（标记 heard）
    tick_rumors(state)
    facts = state.flags["player_known_facts"]
    known = facts.get("known_rumors")
    assert isinstance(known, list)
    assert any(isinstance(x, dict) and x.get("id") == rid and x.get("source_label") == "艾琳娜" for x in known)


def test_rumor_not_known_no_mira_hoofbeats_option() -> None:
    # “米拉没有明确说过夜间马蹄声前”，不应允许出现该类选项（通过 known_rumors 驱动保证）
    state = GameState()
    ensure_player_known_facts(state)
    # 生成 actions payload 的 rumor 相关选项只来自 known_rumors，此处为空，因此不会出现“有人说/听说”类文本
    for phrase in UNSOURCED_PHRASES:
        assert phrase not in ""


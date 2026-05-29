"""Player Knowledge Driven Gameplay Loop — 验收测试。"""

from __future__ import annotations

import random
import re
import uuid

from engine.action_generator import generate_actions, generate_from_knowledge
from engine.action_resolvers import resolve_observe_mira_at_tavern
from engine.choice_validator import validate_choices_payload
from engine.crisis_escalation import get_crisis_ui
from engine.narrative_engine import generate_narrative
from engine.player_knowledge import (
    apply_action_result,
    ensure_player_knowledge,
    get_player_knowledge,
)
from engine.world_state import GameState, NPCState, ensure_player_known_facts
from engine.world_tick import run_world_ticks


def _flat_labels(payload: dict) -> list[str]:
    out: list[str] = []
    for arr in (payload.get("grouped") or {}).values():
        if isinstance(arr, list):
            for a in arr:
                if isinstance(a, dict) and a.get("label"):
                    out.append(str(a["label"]))
    return out


def _all_choices(payload: dict) -> list[dict]:
    items: list[dict] = []
    for arr in (payload.get("grouped") or {}).values():
        if isinstance(arr, list):
            items.extend([a for a in arr if isinstance(a, dict)])
    return items


def _world_panel_blob(state: GameState) -> str:
    ui = get_crisis_ui(state)
    parts = [
        str(ui.get("level_label", "")),
        str(ui.get("merchant_status_label", "")),
        " ".join(str(x) for x in (ui.get("suspicious_clues") or [])),
        " ".join(str(x) for x in (ui.get("risk_notes") or [])),
    ]
    flags = state.flags or {}
    for k in ("village_panic", "danger_level", "war_risk"):
        parts.append(str(flags.get(k, "")))
    return " ".join(parts)


def test_no_rumor_verify_options_without_rumors() -> None:
    state = GameState()
    ensure_player_knowledge(state)
    pk = get_player_knowledge(state)
    pk["rumors"] = []
    payload = generate_actions(state)
    labels = _flat_labels(payload)
    assert not any("求证" in lb and "传闻" in lb for lb in labels)
    assert not any("你听到的传闻" in lb for lb in labels)


def test_observe_mira_failure_yields_change_angle_followup() -> None:
    from engine.rule_engine import DiceRollInfo, RollOutcome

    state = GameState()
    state.location = "村口"
    state.npcs["米拉"] = NPCState(name="米拉", location="村口", attitude="中立", present=True)
    ensure_player_knowledge(state)
    failed_dice = DiceRollInfo(
        ability="WIS",
        modifier=0,
        die_roll=3,
        total=3,
        dc=12,
        outcome=RollOutcome.FAILURE,
        description="观察米拉",
    )
    reg = resolve_observe_mira_at_tavern(state, {}, failed_dice, "observe_mira_at_tavern")
    ar = reg.get("action_result") or {}
    assert ar, "V2 resolver must return action_result"
    apply_action_result(state, ar)

    pk = get_player_knowledge(state)
    assert any(f.get("id") == "mira_behind_tavern_curtain_unclear" for f in pk.get("observations", []))
    followups = pk.get("available_followups") or []
    assert any(f.get("id") == "change_angle_observe_mira" for f in followups)

    payload = generate_actions(state)
    labels = _flat_labels(payload)
    assert any("换个角度观察酒馆门帘后的米拉" in lb for lb in labels)


def test_all_choices_have_source_fact() -> None:
    state = GameState()
    ensure_player_known_facts(state)
    ensure_player_knowledge(state)
    facts = state.flags["player_known_facts"]
    facts["player_facing_facts"] = [
        {
            "id": "pf_mira_observing",
            "type": "observation",
            "text": "米拉站在酒馆门帘后观察，神色惊忧。",
            "introduced_in_narrative": True,
            "visibility": "public",
        }
    ]
    pk = ensure_player_knowledge(state)
    for pf_item in facts["player_facing_facts"]:
        if not any(x.get("id") == pf_item["id"] for x in pk.get("observations", [])):
            pk["observations"].append(
                {"id": pf_item["id"], "text": pf_item["text"], "source": "player_observation"}
            )

    payload = generate_actions(state)
    for choice in _all_choices(payload):
        if choice.get("id") == "free_input":
            continue
        assert choice.get("source_fact"), f"missing source_fact: {choice.get('id')}"


def test_invalid_source_fact_choice_removed() -> None:
    pk = {
        "facts": [],
        "rumors": [],
        "observations": [{"id": "obs1", "text": "测试观察", "source": "test"}],
        "questions": [],
        "available_followups": [],
    }
    payload = {
        "grouped": {
            "investigate": [
                {
                    "id": "bad_choice",
                    "label": "针对「测试观察」继续调查",
                    "input": "继续",
                    "source_fact": "nonexistent_id",
                    "unlocked": True,
                },
                {
                    "id": "good_choice",
                    "label": "针对「测试观察」继续调查",
                    "input": "继续",
                    "source_fact": "obs1",
                    "unlocked": True,
                },
            ],
            "free": [{"id": "free_input", "label": "自由", "input": ""}],
        },
        "flat_inputs": [],
    }
    filtered = validate_choices_payload(payload, pk)
    ids = [c.get("id") for c in filtered["grouped"]["investigate"]]
    assert "bad_choice" not in ids
    assert "good_choice" in ids


def test_world_tick_event_not_in_player_knowledge() -> None:
    state = GameState()
    ensure_player_knowledge(state)
    state.flags["crisis"] = {
        "recent_anomalies": ["村口外侧似乎出现新的痕迹"],
        "suspicious_clues": ["hidden clue"],
    }
    run_world_ticks(state, ticks=1)
    pk_after = get_player_knowledge(state)
    all_text = " ".join(
        str(item.get("text", ""))
        for key in ("facts", "observations", "rumors", "questions")
        for item in (pk_after.get(key) or [])
        if isinstance(item, dict)
    )
    assert "村口外侧似乎出现新的痕迹" not in all_text


def test_forbidden_generic_choice_labels() -> None:
    pk = ensure_player_knowledge(GameState())
    pk["rumors"] = [
        {
            "id": "r1",
            "text": "测试",
            "source": "米拉",
            "source_type": "npc",
            "source_label": "米拉",
        }
    ]
    payload = {
        "grouped": {
            "social": [
                {
                    "id": "x1",
                    "label": "向米拉求证你听到的传闻",
                    "input": "x",
                    "source_fact": "r1",
                    "unlocked": True,
                },
                {
                    "id": "x2",
                    "label": "沿着你刚确认的现象继续追查",
                    "input": "x",
                    "source_fact": "r1",
                    "unlocked": True,
                },
                {
                    "id": "x3",
                    "label": "调查最近的异常动静",
                    "input": "x",
                    "source_fact": "r1",
                    "unlocked": True,
                },
                {
                    "id": "x4",
                    "label": "向现场线索打听",
                    "input": "x",
                    "source_fact": "r1",
                    "unlocked": True,
                },
            ],
            "free": [],
        },
        "flat_inputs": [],
    }
    filtered = validate_choices_payload(payload, pk)
    assert filtered["grouped"].get("social") == []


def test_generate_from_knowledge_without_state() -> None:
    pk = {
        "facts": [],
        "rumors": [],
        "observations": [],
        "questions": [],
        "available_followups": [
            {
                "id": "change_angle_observe_mira",
                "label": "换个角度观察酒馆门帘后的米拉",
                "source_fact": "mira_behind_tavern_curtain_unclear",
                "category": "investigate",
                "intent": {"action_type": "observe", "target": "mira"},
            }
        ],
    }
    pk["observations"].append(
        {
            "id": "mira_behind_tavern_curtain_unclear",
            "text": "米拉似乎仍在门帘后停留，但你没看清她在看什么",
            "source": "player_observation",
        }
    )
    scene = {"player_visible": {"location": "村口", "active_events": []}}
    payload = generate_from_knowledge(pk, scene, {"location": "村口", "consumed_actions": []})
    labels = _flat_labels(payload)
    assert any("换个角度观察酒馆门帘后的米拉" in lb for lb in labels)


def test_hidden_warehouse_blood_not_leaked_anywhere() -> None:
    """手动注入 crisis 内部线索「仓库出现血迹」，不得进入 pk/actions/narrative/world panel。"""
    hidden_text = "仓库出现血迹"
    state = GameState()
    ensure_player_knowledge(state)
    state.flags["crisis"] = {
        "suspicious_clues": [hidden_text],
        "recent_anomalies": [hidden_text],
        "pressure": 55,
    }
    tick_out = run_world_ticks(state, ticks=1)
    api_visible = (tick_out.get("public_events") or []) + (tick_out.get("local_events") or [])
    api_blob = " ".join(str(e.get("text", "")) for e in api_visible)
    assert hidden_text not in api_blob

    pk = get_player_knowledge(state)
    pk_blob = " ".join(
        str(i.get("text", ""))
        for k in ("facts", "observations", "rumors", "questions")
        for i in (pk.get(k) or [])
        if isinstance(i, dict)
    )
    assert hidden_text not in pk_blob

    payload = generate_actions(state)
    actions_blob = " ".join(_flat_labels(payload))
    for c in _all_choices(payload):
        actions_blob += " " + str(c.get("source_fact", "")) + " " + str(c.get("reason", ""))
    assert hidden_text not in actions_blob

    import asyncio

    narrative = asyncio.run(
        generate_narrative(state, {"action_type": "rest"}, None, {}, [])
    )
    assert hidden_text not in re.sub(r"<[^>]+>", "", narrative)

    panel = _world_panel_blob(state)
    assert hidden_text not in panel


def test_random_hidden_clues_never_surface_in_choices_narrative_panel() -> None:
    rng = random.Random(42)
    templates = [
        "地下密室发现{}",
        "失踪者留下{}",
        "{}方向的脚印",
        "昨夜{}",
        "守卫私下提到{}",
    ]
    fillers = ("带划痕银币", "麻袋血迹", "密信残页", "邪术符文", "未署名威胁信")
    clues = [
        templates[rng.randint(0, len(templates) - 1)].format(fillers[rng.randint(0, len(fillers) - 1)])
        for _ in range(20)
    ]

    state = GameState()
    ensure_player_knowledge(state)
    state.flags["crisis"] = {"suspicious_clues": list(clues), "recent_anomalies": list(clues)}

    run_world_ticks(state, ticks=2)
    pk_blob = " ".join(
        str(i.get("text", ""))
        for k in ("facts", "observations", "rumors", "questions")
        for i in (get_player_knowledge(state).get(k) or [])
        if isinstance(i, dict)
    )
    payload = generate_actions(state)
    actions_blob = " ".join(_flat_labels(payload))
    panel = _world_panel_blob(state)

    import asyncio

    narrative = asyncio.run(
        generate_narrative(state, {"action_type": "investigate", "target": "environment"}, None, {}, [])
    )
    narr_plain = re.sub(r"<[^>]+>", "", narrative)

    for clue in clues:
        assert clue not in pk_blob, clue
        assert clue not in actions_blob, clue
        assert clue not in narr_plain, clue
        assert clue not in panel, clue


def test_choice_validator_rejects_arbitrary_generic_phrase() -> None:
    """非米拉/传闻：任意泛化「向某人求证传闻」也应被规则挡下。"""
    pk = {
        "facts": [],
        "rumors": [{"id": "rx", "text": "铁匠铺昨夜失火", "source": "瓦里克", "source_label": "瓦里克"}],
        "observations": [],
        "questions": [],
        "available_followups": [],
    }
    payload = {
        "grouped": {
            "social": [
                {
                    "id": f"bad_{uuid.uuid4().hex[:6]}",
                    "label": "向瓦里克求证你听到的传闻",
                    "input": "x",
                    "source_fact": "rx",
                    "unlocked": True,
                }
            ],
            "free": [],
        },
        "flat_inputs": [],
    }
    out = validate_choices_payload(payload, pk)
    assert out["grouped"].get("social") == []

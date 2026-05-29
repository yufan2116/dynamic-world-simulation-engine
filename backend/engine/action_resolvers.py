"""Action Resolver Registry — action_id 直达结果，禁止误走仓库 investigate fallback。"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from engine.npc_interaction import resolve_npc_interaction
from engine.rule_engine import DiceRollInfo, RollOutcome, outcome_succeeds
from engine.world_state import GameState, ensure_player_known_facts

logger = logging.getLogger(__name__)

ResolverFn = Callable[
    [GameState, dict[str, Any], DiceRollInfo | None, str],
    dict[str, Any],
]

WAREHOUSE_LEAK_TERMS = ("仓库", "麻袋", "谷物", "脚步声")


def _succeeded(dice: DiceRollInfo | None) -> bool:
    if dice is None:
        return True
    return outcome_succeeds(dice.outcome)


def _append_player_facing_fact(state: GameState, item: dict[str, Any]) -> None:
    facts = ensure_player_known_facts(state)
    pf = facts.get("player_facing_facts")
    if not isinstance(pf, list):
        pf = []
        facts["player_facing_facts"] = pf
    item = dict(item)
    item.setdefault("introduced_in_narrative", True)
    item.setdefault("visibility", "public")
    if not any(isinstance(x, dict) and x.get("id") == item.get("id") for x in pf):
        pf.append(item)


def _invalid_for_target(beats: dict[str, Any], target: str) -> bool:
    if target in ("warehouse", "environment", "hidden_details"):
        return False
    blob = " ".join(
        str(beats.get(k, ""))
        for k in ("scene_note", "direct_result", "npc_reaction", "new_information", "consequence")
    )
    return any(t in blob for t in WAREHOUSE_LEAK_TERMS)


def _safe_fallback_beats(action: str = "observe") -> dict[str, Any]:
    return {
        "scene_note": "",
        "direct_result": "你没有得到明确的新信息。",
        "consequence": "你确认当前场景暂时没有更多可见异常。",
    }


def resolve_observe_mira_at_tavern(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    action_id: str,
) -> dict[str, Any]:
    """Legacy adapter — 委托通用 observe resolver。"""
    from engine.interaction_resolver import run_universal_resolution
    from engine.player_knowledge import get_player_knowledge

    pk = get_player_knowledge(state)
    scene = state.flags.get("last_scene_graph") if isinstance(state.flags.get("last_scene_graph"), dict) else {}
    result = run_universal_resolution(state, action_id, intent, dice, scene, pk)
    if result:
        result["resolver_name"] = "interaction_resolver.observe"
        return result
    return resolve_unimplemented(action_id)


def resolve_npc_question(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    action_id: str,
) -> dict[str, Any]:
    """Legacy talk/ask — 委托 universal interaction resolver。"""
    from engine.interaction_resolver import run_universal_resolution
    from engine.player_knowledge import get_player_knowledge

    pk = get_player_knowledge(state)
    scene = state.flags.get("last_scene_graph") if isinstance(state.flags.get("last_scene_graph"), dict) else {}
    result = run_universal_resolution(state, action_id, intent, dice, scene, pk)
    if result:
        return result

    target = str(intent.get("target") or "")
    ok = _succeeded(dice)
    topic = str(intent.get("raw_input") or intent.get("topic") or "")
    resolved = resolve_npc_interaction(state, target, topic, succeeded=ok, raw_input=topic)
    beats = {
        "direct_result": resolved.get("npc_answer") or "对方没有正面回答。",
        "npc_reaction": resolved.get("npc_reaction") or "",
        "new_information": (
            str((resolved.get("revealed_fact") or {}).get("label", ""))
            if resolved.get("revealed_fact")
            else None
        ),
        "consequence": resolved.get("withheld_information") or resolved.get("reason") or "",
    }
    changes: dict[str, Any] = {"check_succeeded": ok}
    return {"handled": True, "resolver_name": action_id, "changes": changes, "beats": beats}


def resolve_listen_thomas_order(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    action_id: str,
) -> dict[str, Any]:
    from engine.interaction_resolver import run_universal_resolution
    from engine.player_knowledge import get_player_knowledge

    pk = get_player_knowledge(state)
    scene = state.flags.get("last_scene_graph") if isinstance(state.flags.get("last_scene_graph"), dict) else {}
    result = run_universal_resolution(state, action_id, intent, dice, scene, pk)
    if result:
        return result
    return resolve_unimplemented(action_id)


def resolve_investigation_environment(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    action_id: str,
) -> dict[str, Any]:
    loc = state.location
    ok = _succeeded(dice)
    beats = {
        "scene_note": f"{state.weather}，你留意{loc}四周。",
        "direct_result": (
            f"你确认{loc}暂时没有更多可见异常。"
            if ok
            else "你没有得到明确的新信息。"
        ),
        "consequence": "局势没有明显变化。" if not ok else "",
    }
    return {
        "handled": True,
        "resolver_name": action_id,
        "changes": {"check_succeeded": ok},
        "beats": beats,
    }


def resolve_follow_player_facing_fact(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    action_id: str,
) -> dict[str, Any]:
    fid = str(intent.get("fact_id") or "")
    if fid == "pf_mira_observing" or "mira" in fid.lower():
        return resolve_observe_mira_at_tavern(state, intent, dice, "observe_mira_at_tavern")
    facts = ensure_player_known_facts(state)
    text = ""
    for f in facts.get("player_facing_facts") or []:
        if isinstance(f, dict) and str(f.get("id")) == fid:
            text = str(f.get("text") or "")
            break
    ok = _succeeded(dice)
    beats = {
        "direct_result": (
            f"你沿着先前确认的现象继续查看：{text}" if text and ok else "你没有得到明确的新信息。"
        ),
        "consequence": "当前场景暂时没有更多可见异常。" if not ok else "你记住了细节，但尚无突破。",
    }
    return {
        "handled": True,
        "resolver_name": action_id,
        "changes": {"check_succeeded": ok},
        "beats": beats,
    }


def resolve_unimplemented(action_id: str) -> dict[str, Any]:
    return {
        "handled": True,
        "unimplemented": True,
        "resolver_name": "unimplemented",
        "changes": {
            "check_succeeded": False,
            "resolver_error": action_id,
        },
        "beats": {
            "direct_result": "这个行动还没有实现对应 resolver。",
            "consequence": f"（开发）未注册 action_id: {action_id}",
        },
    }


# action_id → resolver
ACTION_RESOLVER_REGISTRY: dict[str, ResolverFn] = {
    "observe_mira_at_tavern": resolve_observe_mira_at_tavern,
    "comfort_elena": resolve_npc_question,
    "talk_elena_opening": resolve_npc_question,
    "ask_elena_father_details": resolve_npc_question,
    "talk_艾琳娜": resolve_npc_question,
    "ask_thomas_last_night": resolve_npc_question,
    "talk_托马斯": resolve_npc_question,
    "hear_thomas_order": resolve_listen_thomas_order,
    "listen_thomas_order": resolve_listen_thomas_order,
    "inspect_village_gate_environment": resolve_investigation_environment,
    "observe_village_gate_environment": resolve_investigation_environment,
}


def resolve_warehouse_search(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    action_id: str,
) -> dict[str, Any]:
    """仅 search_warehouse 可触发仓库调查内容。"""
    from engine.crisis_escalation import record_investigation_progress
    from engine.npc_memory import update_npc_from_action

    ok = _succeeded(dice)
    if state.location != "仓库":
        state.location = "仓库"
    changes: dict[str, Any] = {"check_succeeded": ok, "moved_to": "仓库"}
    if ok:
        state.flags["warehouse_searched"] = True
        state.flags["clue_found"] = True
        record_investigation_progress(state, 15)
        changes["clue"] = "带血脚印通向森林方向"
        beats = {
            "direct_result": "你在货箱旁发现未干的痕迹",
            "new_information": "带血脚印通向森林方向",
            "consequence": "脚印指向森林方向",
        }
    else:
        state.flags["warehouse_noise"] = True
        beats = {
            "direct_result": "你没有得到明确的新信息。",
            "consequence": "你确认当前场景暂时没有更多可见异常。",
        }
    return {"handled": True, "resolver_name": action_id, "changes": changes, "beats": beats}


ACTION_RESOLVER_REGISTRY["search_warehouse"] = resolve_warehouse_search


def _resolver_for_action_id(action_id: str) -> ResolverFn | None:
    if action_id in ACTION_RESOLVER_REGISTRY:
        return ACTION_RESOLVER_REGISTRY[action_id]
    if action_id.startswith("follow_"):
        return resolve_follow_player_facing_fact
    if action_id.startswith("observe_"):
        return resolve_observe_mira_at_tavern
    if action_id.startswith("inspect_"):
        return resolve_investigation_environment
    if action_id.startswith("talk_") or action_id.startswith("ask_"):
        return resolve_npc_question
    return None


def execute_registered_action(
    state: GameState,
    action_id: str,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
) -> dict[str, Any]:
    from engine.interaction_resolver import run_universal_resolution
    from engine.player_knowledge import get_player_knowledge

    pk = get_player_knowledge(state)
    scene = state.flags.get("last_scene_graph") if isinstance(state.flags.get("last_scene_graph"), dict) else {}
    v2 = run_universal_resolution(state, action_id, intent, dice, scene, pk)
    if v2:
        return v2

    fn = _resolver_for_action_id(action_id)
    if fn is None:
        logger.warning("ACTION_PIPELINE unregistered action_id=%s", action_id)
        return resolve_unimplemented(action_id)
    result = fn(state, intent, dice, action_id)
    result.setdefault("handled", True)
    return result


def registry_table() -> dict[str, str]:
    """action_id → resolver 函数名（文档/调试）。"""
    out = {k: v.__name__ for k, v in ACTION_RESOLVER_REGISTRY.items()}
    out["follow_*"] = resolve_follow_player_facing_fact.__name__
    out["talk_*"] = resolve_npc_question.__name__
    return out

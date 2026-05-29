"""Action Execution Pipeline — intent 构建、resolver 路由、debug 日志。"""

from __future__ import annotations

import json
import logging
from typing import Any

from engine.action_resolvers import execute_registered_action, registry_table
from engine.intent_parser import ParsedIntent, parse_intent
from engine.rule_engine import DiceRollInfo
from engine.world_simulator import apply_world_simulation
from engine.world_state import GameState

logger = logging.getLogger(__name__)


async def build_intent_async(
    *,
    player_input: str,
    choice_text: str | None,
    action_id: str | None,
    intent_payload: dict[str, Any] | None,
    context: dict[str, Any],
) -> tuple[ParsedIntent, dict[str, Any]]:
    display = (choice_text or player_input or "").strip()
    meta: dict[str, Any] = {
        "selected_choice_text": choice_text,
        "action_id": action_id,
        "intent_payload": intent_payload,
    }

    if action_id and isinstance(intent_payload, dict) and intent_payload.get("action_type"):
        merged = dict(intent_payload)
        merged.setdefault("raw_input", display or player_input)
        merged.setdefault("confidence", 0.95)
        merged["parse_source"] = "selected_action"
        intent = ParsedIntent(**merged)  # type: ignore[call-arg]
        meta["parse_path"] = "intent_payload"
        meta["parsed_intent"] = intent.model_dump()
        return intent, meta

    if action_id:
        intent = ParsedIntent(
            action_type="unknown",
            raw_input=display or player_input,
            parse_source="selected_action_missing_payload",
            confidence=0.5,
            requires_roll=False,
        )
        meta["parse_path"] = "action_id_only"
        meta["parsed_intent"] = intent.model_dump()
        meta["warning"] = "action_id without valid intent_payload"
        return intent, meta

    intent = await parse_intent(player_input, context)
    intent.parse_source = "free_text"
    meta = {
        "selected_choice_text": choice_text,
        "action_id": action_id,
        "intent_payload": intent_payload,
        "parse_path": "intent_parser",
        "parsed_intent": intent.model_dump(),
    }
    return intent, meta


def run_action_simulation(
    state: GameState,
    intent: ParsedIntent,
    dice: DiceRollInfo | None,
    *,
    action_id: str | None,
    action_source: dict[str, Any] | None = None,
    uses_known_fact: list[str] | None = None,
) -> dict[str, Any]:
    intent_dict = intent.model_dump()
    if action_id:
        intent_dict["action_id"] = action_id

    if action_id:
        reg = execute_registered_action(state, action_id, intent_dict, dice)
        changes = dict(reg.get("changes") or {})
        changes["resolver_handled"] = bool(reg.get("handled"))
        changes["resolver_name"] = reg.get("resolver_name", action_id)
        if reg.get("beats"):
            changes["resolver_beats"] = reg["beats"]
        if reg.get("action_result"):
            changes["action_result"] = reg["action_result"]
        if reg.get("unimplemented"):
            changes["unimplemented_action"] = True
        if action_source:
            changes["action_source"] = action_source
        if uses_known_fact:
            changes["uses_known_fact"] = uses_known_fact
        return changes

    changes = apply_world_simulation(state, intent, dice)
    changes["resolver_name"] = "world_simulator"
    if action_source:
        changes["action_source"] = action_source
    return changes


def log_action_pipeline(
    *,
    meta: dict[str, Any],
    intent: ParsedIntent,
    action_id: str | None,
    action_source: dict[str, Any] | None,
    uses_known_fact: list[str] | None,
    changes: dict[str, Any],
    new_actions_count: int = 0,
) -> None:
    payload = {
        "selected_choice_text": meta.get("selected_choice_text"),
        "action_id": action_id,
        "intent_payload": meta.get("intent_payload"),
        "source": action_source,
        "uses_known_fact": uses_known_fact,
        "parsed_intent": meta.get("parsed_intent") or intent.model_dump(),
        "parse_path": meta.get("parse_path"),
        "final_intent_used_by_resolver": intent.model_dump(),
        "resolver_name": changes.get("resolver_name"),
        "resolver_handled": changes.get("resolver_handled"),
        "result_clue": changes.get("clue"),
        "introduced_player_facing_facts": _extract_introduced_facts(changes),
        "new_actions_count": new_actions_count,
    }
    logger.info("ACTION_PIPELINE %s", json.dumps(payload, ensure_ascii=False, default=str))


def _extract_introduced_facts(changes: dict[str, Any]) -> list[str]:
    beats = changes.get("resolver_beats")
    if isinstance(beats, dict) and beats.get("new_information"):
        return [str(beats["new_information"])]
    if changes.get("clue"):
        return [str(changes["clue"])]
    return []


def lookup_action_meta(
    state: GameState, action_id: str | None
) -> tuple[dict[str, Any] | None, list[str]]:
    if not action_id:
        return None, []
    last = state.flags.get("last_available_actions") or {}
    grouped = last.get("grouped") if isinstance(last, dict) else None
    if not isinstance(grouped, dict):
        return None, []
    for arr in grouped.values():
        if not isinstance(arr, list):
            continue
        for a in arr:
            if isinstance(a, dict) and a.get("id") == action_id:
                src = a.get("source") if isinstance(a.get("source"), dict) else None
                uses = a.get("uses_known_fact")
                return src, list(uses) if isinstance(uses, list) else []
    return None, []

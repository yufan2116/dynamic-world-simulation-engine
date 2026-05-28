"""持久化叙事历史，供刷新后恢复叙事流。"""
from __future__ import annotations

from typing import Any

from engine.world_state import GameState


def append_narrative(
    state: GameState,
    html: str,
    *,
    kind: str = "narrative",
    turn: int | None = None,
) -> None:
    log = state.flags.get("narrative_log")
    if not isinstance(log, list):
        log = []
    entry: dict[str, Any] = {"html": html, "kind": kind}
    if turn is not None:
        entry["turn"] = turn
    log.append(entry)
    state.flags["narrative_log"] = log[-100:]


def seed_opening_narratives(
    state: GameState,
    prologue: str,
    narrative: str,
    turn: int,
) -> None:
    state.flags["narrative_log"] = [
        {"html": prologue, "kind": "prologue", "turn": turn},
        {"html": narrative, "kind": "narrative", "turn": turn},
    ]


def ensure_narrative_log(state: GameState) -> list[dict[str, Any]]:
    log = state.flags.get("narrative_log")
    if isinstance(log, list) and log:
        return log
    tid = state.flags.get("template_id") or "missing_merchant_medieval"
    from engine.opening_narrative import get_opening_narrative, get_opening_prologue

    turn = int(state.flags.get("last_turn") or 1)
    prologue = get_opening_prologue(state, tid)
    narrative = get_opening_narrative(state, tid)
    seed_opening_narratives(state, prologue, narrative, turn)
    return state.flags["narrative_log"]

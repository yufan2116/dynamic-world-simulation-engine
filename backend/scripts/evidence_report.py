#!/usr/bin/env python3
"""生成 Evidence Report 用的真实 GameLoop 响应 JSON（与 HTTP API 同路径）。"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.game_loop import GameLoop  # noqa: E402
from engine.player_knowledge import get_player_knowledge  # noqa: E402
from engine.rule_engine import DiceRollInfo, RollOutcome  # noqa: E402
from engine.world_state import NPCState  # noqa: E402
from storage import db  # noqa: E402


def _extract_actions(action_data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cat, arr in (action_data.get("grouped") or {}).items():
        if not isinstance(arr, list):
            continue
        for a in arr:
            if not isinstance(a, dict):
                continue
            out.append(
                {
                    "id": a.get("id"),
                    "label": a.get("label"),
                    "category": cat,
                    "source_fact": a.get("source_fact"),
                    "reason": a.get("reason"),
                    "intent": a.get("intent"),
                }
            )
    return out


def _evidence_pack(loop: GameLoop, label: str, api_result: dict[str, Any]) -> dict[str, Any]:
    assert loop.state
    return {
        "scenario": label,
        "turn": api_result.get("turn"),
        "player_knowledge": copy.deepcopy(get_player_knowledge(loop.state)),
        "parsed_intent": copy.deepcopy(api_result.get("parsed_intent")),
        "actions": copy.deepcopy(_extract_actions(api_result.get("available_actions") or {})),
        "inline_choices_count": len(api_result.get("inline_choices") or []),
        "narrative_plain_preview": (api_result.get("narrative") or "")[:400],
    }


async def _run() -> list[dict[str, Any]]:
    await db.init_db()
    loop = GameLoop()
    reports: list[dict[str, Any]] = []

    # 1) 开场（demo seed）
    opening = await loop.start_new_demo_game("ravenford_demo")
    reports.append(_evidence_pack(loop, "opening_after_start", opening))

    # 2) 观察米拉失败
    assert loop.state
    loop.state.flags["opening_scene"] = True
    loop.state.npcs.setdefault(
        "米拉",
        NPCState(name="米拉", location="酒馆", attitude="中立", present=True),
    )
    failed = DiceRollInfo(
        ability="WIS",
        modifier=0,
        die_roll=2,
        total=2,
        dc=12,
        outcome=RollOutcome.FAILURE,
        description="观察米拉",
    )
    loop._action_id = "observe_mira_at_tavern"
    loop._intent_payload = {
        "action_type": "observe",
        "target": "mira",
        "location": "tavern",
    }
    loop._selected_choice_text = "观察酒馆门帘后的米拉"

    from engine.action_pipeline import run_action_simulation
    from engine.intent_parser import ParsedIntent

    intent = ParsedIntent(
        action_type="observe",
        target="mira",
        location="tavern",
        raw_input="观察酒馆门帘后的米拉",
        requires_roll=True,
        ability="WIS",
        dc=12,
    )
    changes = run_action_simulation(
        loop.state,
        intent,
        failed,
        action_id="observe_mira_at_tavern",
    )
    from engine.player_knowledge import apply_action_result

    ar = changes.get("action_result")
    if isinstance(ar, dict):
        apply_action_result(loop.state, ar)

    from engine.action_generator import generate_actions

    action_data = generate_actions(loop.state)
    reports.append(
        {
            "scenario": "after_observe_mira_failure_simulated",
            "resolver_consequence": (changes.get("resolver_beats") or {}).get("consequence"),
            "player_knowledge": copy.deepcopy(get_player_knowledge(loop.state)),
            "actions": copy.deepcopy(_extract_actions(action_data)),
        }
    )

    # 3) 与托马斯交谈（完整 API process_action）
    loop._action_id = "ask_thomas_last_night"
    loop._intent_payload = {
        "action_type": "talk",
        "target": "托马斯",
        "location": "current",
    }
    loop._selected_choice_text = "询问托马斯昨夜是否听见异常动静"
    thomas_resp = await loop.process_action("询问托马斯昨夜异常情况")
    reports.append(_evidence_pack(loop, "after_talk_thomas", thomas_resp))

    return reports


def main() -> None:
    data = asyncio.run(_run())
    out_path = ROOT / "scripts" / "evidence_api_responses.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

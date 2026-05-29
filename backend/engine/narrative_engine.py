"""叙事引擎 — CRPG Scene Renderer；LLM 渲染已发生事实，非小说润色。"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import httpx

from engine.llm_config import get_llm_api_key, get_llm_base_url, get_llm_model
from engine.narrative_beats import beats_to_html, build_event_beats
from engine.rumor_network import rumors_at_location
from engine.rule_engine import DiceRollInfo, RollOutcome
from engine.encounter_state import build_encounter_state
from engine.npc_dialogue_tree import resolve_scene_dialogue_behaviors
from engine.scene_graph import build_scene_graph
from engine.world_template_manager import get_narrative_style, resolve_template_id
from engine.world_state import GameState
from engine.grounding import filter_unknown_text
from engine.narrative_formatter import format_narrative_html
from engine.text_sanitizer import sanitize_narrative_html, sanitize_player_text

SYSTEM_PROMPT = """你是 CRPG Scene Renderer，不是小说作者。
你只负责把 encounter（遭遇状态）与 event_beats（行动结果）渲染成「当前正在发生」的游戏文本。

渲染优先级：encounter > event_beats > scene_graph。不得违背 encounter 中的 tension、risk、npc_goal、hidden_info。

规则：
1. 不要写小说腔，不要使用命运、迷雾、史诗、宿命、仿佛、灵魂、铁、诗意比喻等泛文学表达。
2. 不要新增未提供的 NPC、地点、物品、线索。
2.1 你只能使用 player_known_facts、scene_graph、event_beats 中已经提供的信息。
    禁止主动引入未发现的地点、物品、线索、NPC；禁止无来源表达（例如“有人说/听说/据说”）。
3. 只描写当前场景正在发生的事情。
4. 输出应短、清楚、有动作感。
5. 结构顺序：scene → dialogue → result（玩家行动后果）→ consequence → world。
   不要输出「行动」标题或元标签；不要用「你深吸一口气」等空洞铺垫句。
   选项由系统另行生成，勿在正文末尾列举 1.2.3. 选项。
6. 每次输出必须覆盖（若无内容可省略该段）：
   - scene：当前场景变化
   - result：玩家行动造成的直接结果（class="result"）
   - dialogue：NPC 对白（class="dialogue"）
   - consequence：世界状态变化（class="consequence" 内 <em>）
7. 失败必须有具体后果，但不要直接写「失败」二字。
8. 成功必须给出明确获得的信息、位置变化或关系变化。
9. 对话要短，必须符合 scene_graph.visible_npcs[].conversational_behavior：
   若 is_dialogue_target 为 true，对白须体现 active_branch 与 behavior_hints（动作+语气），不得违背。
10. npc_dialogue 字段给出本回合对话焦点 NPC 的完整行为树，优先于其他 NPC。
11. 不要输出 DC、d20、检定总值、属性修正。
12. 字数控制在 80-160 中文字。
13. 输出 HTML，且仅使用以下标签：
   <p class="scene">...</p>
   <p class="result">...</p>
   <p class="dialogue">...</p>
   <p class="consequence"><em>...</em></p>
   <p class="world">...</p>（仅用于 world_events）
14. event_beats 是行动结果事实；hidden_info / hidden_truth 是场景内真相，NPC 可按 npc_goal 选择是否透露。
15. 语气须匹配 encounter.encounter_tone 与 encounter.risk（low/medium/high）。"""

NOVEL_STYLE_MARKERS = [
    "命运",
    "宿命",
    "灵魂",
    "仿佛",
    "史诗",
    "古老",
    "迷雾深处",
    "世界的齿轮",
    "未冷却的铁",
    "神秘力量",
    "诗",
    "鹰隼",
    "散开一角",
]

DICE_LEAK_MARKERS = ("DC", "d20", "掷出", "检定总值", "+ ", "属性修正")


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_player_action_echo_html(player_action_display: str) -> str:
    """前端叙事流行动回显（必须独立块）。"""
    display = (player_action_display or "").strip()
    if not display:
        display = "你照自己的判断采取行动。"
    display = _escape_html(display)
    return f'<p class="player-action">你选择：<strong>“{display}”</strong></p>'


def build_system_prompt(state: GameState) -> str:
    tid = resolve_template_id(state.flags.get("template_id"))
    style = get_narrative_style(tid)
    tone = "、".join(style.get("tone", []))
    extra_rules = style.get("llm_extra_rules") or []
    avoid = style.get("novel_avoid") or []
    extra_block = "\n".join(f"- {r}" for r in extra_rules)
    avoid_block = "、".join(avoid) if avoid else ""
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"【本世界文风】{tone}\n"
        f"{style.get('style_hints', '')}\n"
        f"{extra_block}\n"
        f"【额外禁用词】{avoid_block}"
    )


def _outcome_for_payload(dice: dict[str, Any] | None, succeeded: bool) -> str:
    if not dice:
        return "success" if succeeded else "failure"
    raw = dice.get("outcome", "")
    mapping = {
        RollOutcome.CRITICAL_SUCCESS.value: "critical_success",
        RollOutcome.SUCCESS.value: "success",
        RollOutcome.FAILURE.value: "failure",
        RollOutcome.CRITICAL_FAILURE.value: "critical_failure",
    }
    return mapping.get(raw, "success" if succeeded else "failure")


def _sanitize_world_changes(changes: dict[str, Any]) -> dict[str, Any]:
    skip = {"narrative_scene", "success_scene", "failure_scene"}
    return {k: v for k, v in changes.items() if k not in skip}


def _extract_recent_events(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    """最近 3 条关键事件：玩家行动 / 世界事件 / NPC 关系变化。"""
    last_action: dict[str, str] | None = None
    last_world: dict[str, str] | None = None
    last_npc: dict[str, str] | None = None

    for ev in reversed(events):
        et = ev.get("event_type", "")
        payload = ev.get("payload") or {}
        turn = ev.get("turn", 0)

        if last_action is None and et == "action":
            inp = payload.get("player_input", "")
            intent = payload.get("intent") or {}
            act = intent.get("action_type", "")
            last_action = {
                "type": "player_action",
                "turn": str(turn),
                "summary": f"玩家：{inp[:80]}" if inp else f"行动类型：{act}",
            }

        if last_world is None and et == "world_change":
            ticks = payload.get("world_tick_events") or {}
            if isinstance(ticks, dict):
                visible = (ticks.get("public_events") or []) + (ticks.get("local_events") or [])
                if visible:
                    last_world = {
                        "type": "world_event",
                        "turn": str(turn),
                        "summary": str(visible[-1].get("text", "世界状态更新"))[:120],
                    }
            elif isinstance(ticks, list) and ticks:
                last_world = {
                    "type": "world_event",
                    "turn": str(turn),
                    "summary": ticks[-1].get("text", "世界状态更新")[:120],
                }
            elif payload.get("clue"):
                last_world = {
                    "type": "world_event",
                    "turn": str(turn),
                    "summary": f"线索：{payload['clue']}"[:120],
                }
            elif payload.get("moved_to"):
                last_world = {
                    "type": "world_event",
                    "turn": str(turn),
                    "summary": f"移动至：{payload['moved_to']}",
                }

        if last_npc is None and et == "world_change":
            for upd in payload.get("npc_updates") or []:
                if upd.get("attitude_to"):
                    last_npc = {
                        "type": "npc_relation",
                        "turn": str(turn),
                        "summary": (
                            f"{upd.get('npc', 'NPC')}态度："
                            f"{upd.get('attitude_from', '?')}→{upd['attitude_to']}"
                        ),
                    }
                    break

        if last_action and last_world and last_npc:
            break

    out: list[dict[str, str]] = []
    if last_action:
        out.append(last_action)
    if last_world:
        out.append(last_world)
    if last_npc:
        out.append(last_npc)
    return out[:3]


def _visible_rumors(state: GameState) -> list[dict[str, str]]:
    rumors = rumors_at_location(state, state.location)
    vis = []
    for r in rumors:
        if not isinstance(r, dict):
            continue
        if not r.get("known_to_player"):
            continue
        if r.get("visibility") in ("hidden",):
            continue
        vis.append(
            {
                "id": str(r.get("id", "")),
                "text": str(r.get("text", "")),
                "source_label": str(r.get("source_label", "")),
                "credibility": str(r.get("credibility", "")),
            }
        )
    return vis[-3:]


def _build_payload(
    state: GameState,
    intent: dict[str, Any],
    dice: dict[str, Any] | None,
    changes: dict[str, Any],
    recent_events: list[dict[str, Any]],
    event_beats: dict[str, Any],
    *,
    player_action_display: str,
) -> dict[str, Any]:
    succeeded = bool(changes.get("check_succeeded", True))
    npc_changes = changes.get("npc_updates") or []
    scene_graph = build_scene_graph(state, intent, changes)
    npc_dialogue = resolve_scene_dialogue_behaviors(state, intent, changes)
    encounter = build_encounter_state(state, intent, changes, dice)

    return {
        "encounter": encounter,
        "scene_graph": scene_graph,
        "npc_dialogue": npc_dialogue,
        "player_action_display": player_action_display,
        "player_action": intent.get("raw_input") or "",
        "intent": {
            "action_type": intent.get("action_type"),
            "target": intent.get("target"),
            "destination": intent.get("destination"),
            "raw_input": intent.get("raw_input"),
            "confidence": intent.get("confidence"),
        },
        "rule_result": {
            "succeeded": succeeded,
            "outcome": _outcome_for_payload(dice, succeeded),
        },
        "event_beats": {
            k: event_beats.get(k)
            for k in (
                "direct_result",
                "npc_reaction",
                "new_information",
                "consequence",
                "scene_note",
                "world_events",
            )
            if event_beats.get(k)
        },
        "world_changes": _sanitize_world_changes(changes),
        "npc_changes": npc_changes,
        "recent_events": _extract_recent_events(recent_events),
        "visible_rumors": _visible_rumors(state),
    }


def _novel_style_score(text: str) -> int:
    return sum(text.count(m) for m in NOVEL_STYLE_MARKERS)


def _is_bad_output(text: str, *, action_type: str = "") -> bool:
    if any(m in text for m in DICE_LEAK_MARKERS):
        return True
    if _novel_style_score(text) >= 3:
        return True
    if not re.search(r'class="(player-action|scene|result|dialogue|consequence|world)"', text):
        return True
    # 强制：talk 类必须有 result/dialogue/consequence 之一，否则视为“只写场景背景”不合格
    if action_type in ("talk", "persuade", "intimidate"):
        if not re.search(r'class="(dialogue|result|consequence)"', text):
            return True
    return False


async def _call_llm(
    *,
    system: str,
    user: str,
    temperature: float,
) -> str:
    model = get_llm_model()
    base_url = get_llm_base_url()
    api_key = get_llm_api_key()
    assert api_key
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": 450,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def generate_narrative(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    changes: dict[str, Any],
    recent_events: list[dict[str, Any]],
    *,
    player_action_display: str = "",
) -> str:
    dice_dict = dice.model_dump() if dice else None
    if dice_dict and hasattr(dice_dict.get("outcome"), "value"):
        dice_dict["outcome"] = dice_dict["outcome"].value

    event_beats = build_event_beats(state, intent, dice_dict, changes)
    fallback_html = format_narrative_html(
        sanitize_narrative_html(beats_to_html(event_beats, state), state),
        state,
        intent=intent,
        changes=changes,
    )

    api_key = get_llm_api_key()
    if not api_key:
        echo = sanitize_player_text(build_player_action_echo_html(player_action_display), state)
        return echo + "\n" + fallback_html

    payload = _build_payload(
        state,
        intent,
        dice_dict,
        changes,
        recent_events,
        event_beats,
        player_action_display=player_action_display,
    )
    user_content = (
        "根据以下 JSON 渲染本回合遭遇（HTML）。"
        "以 encounter 为场面基调，用 event_beats 写清行动结果；"
        "hidden_info 仅供你把握场面，勿让 NPC 违背 npc_goal 一次性说透。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    system = build_system_prompt(state)
    try:
        text = await _call_llm(
            system=system,
            user=user_content,
            temperature=0.55,
        )
        if _is_bad_output(text, action_type=str(intent.get("action_type", ""))):
            text = await _call_llm(
                system=system
                + "\n\n【重申】禁止文学修辞；必须输出带 class 的 <p> 标签；总字数 80-160。",
                user=user_content,
                temperature=0.35,
            )
        if _is_bad_output(text, action_type=str(intent.get("action_type", ""))):
            echo = sanitize_player_text(build_player_action_echo_html(player_action_display), state)
            return echo + "\n" + fallback_html
        text = filter_unknown_text(text, state)
        text = format_narrative_html(
            sanitize_narrative_html(text, state),
            state,
            intent=intent,
            changes=changes,
        )
        echo = sanitize_player_text(build_player_action_echo_html(player_action_display), state)
        return echo + "\n" + text
    except Exception:
        echo = sanitize_player_text(build_player_action_echo_html(player_action_display), state)
        return echo + "\n" + fallback_html


def build_narrative_proof(
    state: GameState,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    changes: dict[str, Any],
    recent_events: list[dict[str, Any]],
    *,
    player_action_display: str,
) -> dict[str, Any]:
    """构造“叙事不是瞎编”的可复盘证据：输入 payload 与其哈希。"""
    dice_dict = dice.model_dump() if dice else None
    if dice_dict and hasattr(dice_dict.get("outcome"), "value"):
        dice_dict["outcome"] = dice_dict["outcome"].value

    event_beats = build_event_beats(state, intent, dice_dict, changes)
    payload = _build_payload(
        state,
        intent,
        dice_dict,
        changes,
        recent_events,
        event_beats,
        player_action_display=player_action_display,
    )
    system = build_system_prompt(state)

    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    system_hash = hashlib.sha256(system.encode("utf-8")).hexdigest()
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    user_prompt = (
        "根据以下 JSON 渲染本回合遭遇（HTML）。"
        "以 encounter 为场面基调，用 event_beats 写清行动结果；"
        "hidden_info 仅供你把握场面，勿让 NPC 违背 npc_goal 一次性说透。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    user_hash = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()

    return {
        "llm": {
            "configured": bool(get_llm_api_key()),
            "model": get_llm_model(),
            "base_url": get_llm_base_url(),
        },
        "system_prompt_sha256": system_hash,
        "user_prompt_sha256": user_hash,
        "payload_sha256": payload_hash,
        # 注意：这里保留 payload 的“结构化证据”（可截断），用于前端解释叙事输入来自哪儿。
        "payload_preview": payload,
        # Inspector 面板用途：保存可直接展示的 prompt（体量可接受；若未来变大再做截断/开关）。
        "system_prompt": system,
        "user_prompt": user_prompt,
    }

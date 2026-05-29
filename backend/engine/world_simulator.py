"""确定性世界模拟 — 根据意图与检定结果更新状态，并产出叙事节拍素材。"""
from __future__ import annotations

from typing import Any

from engine.crisis_escalation import record_investigation_progress, record_player_rest
from engine.intent_parser import ParsedIntent
from engine.location_registry import resolve_direction_phrase
from engine.npc_interaction import resolve_npc_interaction
from engine.npc_memory import update_npc_from_action
from engine.text_sanitizer import sanitize_player_text
from engine.rule_engine import DiceRollInfo, RollOutcome, outcome_succeeds
from engine.world_state import GameState
from engine.world_state import ensure_player_known_facts
from engine.world_templates import all_locations_for_state, location_connections_for_state
from engine.world_tick import advance_world_time


def _set_active_npcs(state: GameState) -> None:
    state.active_npcs = [n.name for n in state.npc_at_location()]


def apply_world_simulation(
    state: GameState,
    intent: ParsedIntent,
    dice: DiceRollInfo | None,
) -> dict[str, Any]:
    """纯代码规则：更新地点、NPC、任务、声望等。"""
    changes: dict[str, Any] = {"npc_updates": [], "faction_changes": {}}
    succeeded = True
    if dice:
        succeeded = outcome_succeeds(dice.outcome)
    changes["check_succeeded"] = succeeded

    action = intent.action_type
    demo = bool(state.flags.get("vertical_slice_demo"))
    minutes = 22 if demo else 30
    if action == "rest":
        minutes = 360 if demo else 480
    elif action == "move":
        minutes = 35 if demo else 45
    time_diff = advance_world_time(state, minutes)
    changes["time"] = time_diff

    if action == "move" and intent.destination:
        dest = intent.destination
        conns = location_connections_for_state(state)
        if dest in conns.get(state.location, []) or dest in all_locations_for_state(state):
            state.location = dest
            changes["moved_to"] = dest
            facts = ensure_player_known_facts(state)
            if dest not in facts["known_locations"]:
                facts["known_locations"].append(dest)
            _set_active_npcs(state)

    elif action == "talk" and intent.target:
        target = intent.target
        if target in state.npcs:
            npc = state.npcs[target]
            if npc.location != state.location and target != "瓦里克":
                changes["failure_scene"] = (
                    f"<p>你寻找<strong>{target}</strong>，但对方并不在此处。"
                    f"也许该去别处打听。</p>"
                )
                changes["check_succeeded"] = False
            elif target == "瓦里克" and not state.flags.get("varick_revealed"):
                changes["failure_scene"] = (
                    "<p>森林深处只有风声。瓦里克的踪迹尚未显现——"
                    "你需要更多线索才能找到他。</p>"
                )
                changes["check_succeeded"] = False
            else:
                mem = f"玩家与{target}交谈：「{intent.raw_input[:50]}」"
                delta = 5 if succeeded else -10
                if dice and dice.outcome == RollOutcome.CRITICAL_SUCCESS:
                    delta = 15
                elif dice and dice.outcome == RollOutcome.CRITICAL_FAILURE:
                    delta = -20
                upd = update_npc_from_action(
                    state, target, memory=mem, attitude_delta=delta
                )
                if upd:
                    changes["npc_updates"].append(upd)
                if target == "托马斯":
                    resolved = resolve_npc_interaction(
                        state,
                        "托马斯",
                        intent.raw_input or "昨夜异常",
                        succeeded=succeeded,
                        raw_input=intent.raw_input or "",
                    )
                    changes["npc_answer"] = resolved.get("npc_answer")
                    changes["npc_reaction"] = resolved.get("npc_reaction")
                    changes["withheld_information"] = resolved.get("withheld_information")
                    changes["no_new_information_reason"] = resolved.get("reason")
                    revealed = resolved.get("revealed_fact")
                    if isinstance(revealed, dict):
                        record_investigation_progress(state, 8 if succeeded else 2)
                        facts = ensure_player_known_facts(state)
                        kf = facts.get("known_facts")
                        if isinstance(kf, list):
                            item = dict(revealed)
                            item.setdefault("discovered_turn", int(state.flags.get("last_turn", 1) or 1))
                            item.setdefault("discovered_at", str(state.location))
                            if not any(
                                isinstance(x, dict) and x.get("id") == item.get("id") for x in kf
                            ):
                                kf.append(item)
                        changes["clue"] = str(revealed.get("label", ""))
                    elif not succeeded:
                        state.flags["thomas_alerted"] = True
                if target == "米拉" and succeeded:
                    record_investigation_progress(state, 6)
                    changes["clue"] = "马库斯最后出现在仓库附近"
                    facts = ensure_player_known_facts(state)
                    facts["known_facts"].append(
                        {
                            "id": "clue_marcus_last_seen_near_warehouse",
                            "type": "clue",
                            "label": "马库斯最后出现在仓库附近",
                            "visibility": "discovered",
                            "source": "npc",
                            "source_label": "米拉",
                            "discovered_turn": int(state.flags.get("last_turn", 1) or 1),
                            "discovered_at": str(state.location),
                            "description": "米拉提到马库斯最后一趟的去向与仓库附近有关。",
                        }
                    )
                if target == "艾琳娜":
                    if succeeded:
                        state.faction_reputation["村民"] = (
                            state.faction_reputation.get("村民", 0) + 5
                        )
                        changes["faction_changes"]["村民"] = "+5"
                        record_investigation_progress(state, 4)
                        changes["npc_answer"] = "艾琳娜哽咽着说：父亲昨夜说要去清点货物，之后就再也没回来。"
                        changes["npc_reaction"] = "她攥紧衣角，反复强调父亲从不夜不归宿。"
                        facts = ensure_player_known_facts(state)
                        pf = facts.get("player_facing_facts")
                        if isinstance(pf, list):
                            pf.append(
                                {
                                    "id": "pf_elena_last_seen_cargo_check",
                                    "type": "npc_statement",
                                    "text": "艾琳娜说父亲昨夜去清点货物后没有回来。",
                                    "visibility": "discovered",
                                    "source": "npc_statement",
                                    "source_label": "艾琳娜",
                                    "introduced_in_narrative": True,
                                    "discovered_turn": int(state.flags.get("last_turn", 1) or 1),
                                    "discovered_at": str(state.location),
                                }
                            )
                    else:
                        state.flags["village_panic"] = min(
                            100, int(state.flags.get("village_panic", 35)) + 5
                        )
                        changes["npc_answer"] = "艾琳娜情绪崩溃，只能反复说“昨晚没回来”，说不清更多细节。"
                        changes["no_new_information_reason"] = "艾琳娜情绪失控，暂时无法提供更多细节。"
                if target == "瓦里克":
                    if succeeded:
                        state.faction_reputation["强盗"] = (
                            state.faction_reputation.get("强盗", 0) + 10
                        )
                    else:
                        state.faction_reputation["强盗"] = (
                            state.faction_reputation.get("强盗", 0) - 10
                        )
                        changes["failure_scene"] = (
                            "<p>瓦里克冷笑一声，手下向前逼近一步。"
                            "你感到剑刃的寒意——谈判破裂了。</p>"
                        )

    elif action == "investigate":
        if intent.target == "thomas_order":
            state.flags["heard_thomas_order"] = True
            patrol = resolve_direction_phrase(state, "warehouse") or "村口外侧"
            changes["npc_answer"] = sanitize_player_text(
                f"托马斯：『今夜加强{patrol}巡逻，双哨换岗，任何人不得擅离岗位。』",
                state,
            )
            changes["npc_reaction"] = "两名守卫应声离去，脚步消失在木栅外。"
            changes["clue"] = f"托马斯下令加强{patrol}巡逻"
            facts = ensure_player_known_facts(state)
            kf = facts.get("known_facts")
            if isinstance(kf, list):
                item = {
                    "id": "fact_thomas_extra_patrol",
                    "type": "observation",
                    "label": f"托马斯下令加强{patrol}巡逻",
                    "visibility": "discovered",
                    "source": "npc_order",
                    "source_label": "托马斯",
                    "discovered_turn": int(state.flags.get("last_turn", 1) or 1),
                    "discovered_at": str(state.location),
                    "description": f"你当场听清托马斯要求加强{patrol}的哨岗与巡逻。",
                }
                if not any(isinstance(x, dict) and x.get("id") == item["id"] for x in kf):
                    kf.append(item)
        elif (
            intent.target == "warehouse"
            or intent.destination == "仓库"
            or str(intent.raw_input or "").find("仓库") >= 0
        ):
            state.location = "仓库"
            changes["moved_to"] = "仓库"
            _set_active_npcs(state)
        if state.location == "仓库" and (
            intent.target == "warehouse"
            or intent.destination == "仓库"
            or "仓库" in str(intent.raw_input or "")
        ):
            if succeeded:
                state.flags["warehouse_searched"] = True
                state.flags["clue_found"] = True
                record_investigation_progress(state, 15)
                changes["clue"] = "带血脚印通向森林方向"
                facts = ensure_player_known_facts(state)
                if "仓库" not in facts["known_locations"]:
                    facts["known_locations"].append("仓库")
                # 结构化 fact 已写入 known_facts；不再依赖 known_clues
                facts["known_facts"].append(
                    {
                        "id": "clue_bloody_footprints_to_forest",
                        "type": "clue",
                        "label": "带血脚印通向森林方向",
                        "visibility": "discovered",
                        "source": "player_observation",
                        "source_label": "现场勘验",
                        "discovered_turn": int(state.flags.get("last_turn", 1) or 1),
                        "discovered_at": str(state.location),
                        "description": "你在地面上确认了一串带血的脚印，延伸向森林方向。",
                    }
                )
                upd = update_npc_from_action(
                    state,
                    "米拉",
                    memory="传闻有人在仓库发现血迹与脚印。",
                    attitude_delta=5,
                )
                if upd:
                    changes["npc_updates"].append(upd)
            else:
                state.flags["warehouse_noise"] = True
                upd = update_npc_from_action(
                    state,
                    "托马斯",
                    memory="仓库方向传来异常声响，托马斯前往查看。",
                    attitude_delta=-5,
                )
                if upd:
                    changes["npc_updates"].append(upd)
                state.flags["village_panic"] = min(
                    100, int(state.flags.get("village_panic", 35)) + 8
                )
        elif state.location == "森林小路":
            if succeeded:
                state.flags["varick_revealed"] = True
                state.npcs["瓦里克"].present = True
                state.npcs["瓦里克"].location = "森林小路"
                changes["clue"] = "瓦里克与强盗现身森林小路"
                _set_active_npcs(state)
            else:
                changes["failure_scene"] = (
                    "<p>林间雾气太浓，你迷失了方向，只听见远处传来一声冷笑。</p>"
                )

    elif action == "persuade" or action == "intimidate":
        target = intent.target
        if target and target in state.npcs:
            delta = (10 if succeeded else -8) if action == "persuade" else (8 if succeeded else -12)
            upd = update_npc_from_action(
                state,
                target,
                memory=f"玩家尝试{'说服' if action == 'persuade' else '恐吓'}{target}",
                attitude_delta=delta,
            )
            if upd:
                changes["npc_updates"].append(upd)
            if not succeeded:
                state.flags["village_panic"] = min(
                    100, int(state.flags.get("village_panic", 35)) + 3
                )

    elif action == "combat":
        if state.location == "森林小路" and state.flags.get("varick_revealed"):
            if succeeded:
                state.flags["combat_won"] = True
                state.faction_reputation["强盗"] = -50
                state.faction_reputation["村庄守卫"] = (
                    state.faction_reputation.get("村庄守卫", 0) + 20
                )
                changes["quest_update"] = "瓦里克被击退，森林小路恢复平静"
                changes["success_scene"] = (
                    "<p>剑锋交击，火花四溅。瓦里克终于踉跄后退，"
                    "咒骂着带人退入密林深处。</p>"
                )
                for q in state.quests:
                    if q.id == "missing_merchant":
                        q.status = "completed"
                crisis = state.flags.setdefault("crisis", {})
                if isinstance(crisis, dict):
                    crisis["merchant_status"] = "resolved"
                    crisis["pressure"] = max(0, float(crisis.get("pressure", 0)) - 40)
                update_npc_from_action(
                    state,
                    "瓦里克",
                    memory="瓦里克在战斗中被击败。",
                    attitude_delta=-30,
                )
            else:
                changes["failure_scene"] = (
                    "<p>你负伤撤离，身后的笑声像鞭子一样抽在背上。"
                    "村庄的方向，钟声响得更急了。</p>"
                )
                state.faction_reputation["村庄守卫"] = (
                    state.faction_reputation.get("村庄守卫", 0) - 5
                )
                state.flags["village_panic"] = min(
                    100, int(state.flags.get("village_panic", 35)) + 10
                )

    elif action == "rest":
        record_player_rest(state)
        changes["success_scene"] = (
            "<p>你在避风处短暂歇息，体力稍有恢复。"
            "但当你睁眼时，时钟已悄然拨动——世界从未停下。</p>"
        )

    elif action == "unknown":
        if not succeeded:
            changes["failure_scene"] = (
                "<p>你的意图模糊不清，只是徒然消耗了时间。"
                "雾气更浓了。</p>"
            )
        elif dice:
            changes["success_scene"] = (
                "<p>你静下心来观察四周，隐约觉得应继续追查失踪商人的下落。</p>"
            )

    _set_active_npcs(state)
    return changes

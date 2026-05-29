"""Universal Interaction Resolver — Simulation Architecture V2."""

from __future__ import annotations

from typing import Any

from engine.location_registry import is_location_public, resolve_direction_phrase
from engine.npc_state import (
    apply_npc_state_changes,
    ensure_npc_states,
    get_npc_state,
    get_player_relationship,
    npc_id_from_name,
    npc_name_from_id,
    npc_present_at_location,
)
from engine.rule_engine import DiceRollInfo, RollOutcome, outcome_succeeds
from engine.topic_resolver import (
    get_topic,
    player_knows_topic,
    register_player_topic,
    resolve_topic,
)
from engine.world_state import GameState

INTERACTION_TYPES = frozenset({
    "ask_about_topic",
    "comfort",
    "observe",
    "persuade",
    "intimidate",
    "deceive",
    "follow",
    "eavesdrop",
    "trade",
    "accuse",
})


def _dice_ok(dice: DiceRollInfo | None) -> bool:
    if dice is None:
        return True
    return outcome_succeeds(dice.outcome)


def _empty_result() -> dict[str, Any]:
    return {
        "narrative_blocks": [],
        "npc_state_changes": [],
        "new_facts": [],
        "new_observations": [],
        "new_questions": [],
        "new_rumors": [],
        "available_followups": [],
    }


def _check_reveal_conditions(
    conditions: dict[str, Any],
    *,
    rel: dict[str, Any],
    topic_id: str | None,
    dice_ok: bool,
    crisis_pressure: float = 0,
) -> bool:
    if not conditions:
        return True
    trust = int(rel.get("trust", 0))
    suspicion = int(rel.get("suspicion", 0))
    if conditions.get("trust_min") is not None and trust < int(conditions["trust_min"]):
        return False
    if conditions.get("suspicion_max") is not None and suspicion > int(conditions["suspicion_max"]):
        return False
    if conditions.get("dice_success") and not dice_ok:
        return False
    if conditions.get("topic_match") and topic_id != conditions.get("topic_match"):
        return False
    if conditions.get("pressure_min") is not None and crisis_pressure < float(conditions["pressure_min"]):
        return False
    return True


def _crisis_pressure(state: GameState) -> float:
    c = state.flags.get("crisis")
    if isinstance(c, dict):
        return float(c.get("pressure", 0))
    return 0.0


def resolve_interaction(
    actor: str,
    target_npc_id: str,
    intent: dict[str, Any],
    scene_graph: dict[str, Any],
    player_knowledge: dict[str, Any],
    world_state: GameState,
    *,
    interaction_type: str = "ask_about_topic",
    topic_id: str | None = None,
    dice: DiceRollInfo | None = None,
    secondary_type: str | None = None,
    special: str | None = None,
) -> dict[str, Any]:
    """通用 NPC 互动解析。"""
    result = _empty_result()
    itype = str(interaction_type or intent.get("interaction_type") or "ask_about_topic")
    npc = get_npc_state(world_state, target_npc_id)
    if not npc:
        result["narrative_blocks"].append(
            {"type": "result", "text": "你找不到要交谈的对象。"}
        )
        return result

    name = str(npc.get("name") or npc_name_from_id(target_npc_id))
    if not npc_present_at_location(world_state, target_npc_id):
        result["narrative_blocks"].append(
            {"type": "result", "text": f"{name}此刻不在你面前。"}
        )
        return result

    rel = get_player_relationship(npc)
    dice_ok = _dice_ok(dice)
    pressure = _crisis_pressure(world_state)

    if special == "overhear_order":
        return _resolve_eavesdrop_order(world_state, npc, player_knowledge, result)

    if itype == "comfort" or secondary_type == "ask_about_topic":
        blocks, changes = _resolve_comfort_and_ask(
            world_state, npc, rel, intent, topic_id, dice_ok, pressure, player_knowledge
        )
        result["narrative_blocks"].extend(blocks)
        result["npc_state_changes"].extend(changes)
        if itype == "ask_about_topic" and not secondary_type:
            ask_blocks, ask_changes, extras = _resolve_ask_about_topic(
                world_state, npc, rel, topic_id, intent, dice_ok, pressure, player_knowledge
            )
            result["narrative_blocks"].extend(ask_blocks)
            result["npc_state_changes"].extend(ask_changes)
            _merge_extras(result, extras)
        else:
            ask_blocks, ask_changes, extras = _resolve_ask_about_topic(
                world_state, npc, rel, topic_id, intent, dice_ok, pressure, player_knowledge
            )
            result["narrative_blocks"].extend(ask_blocks)
            result["npc_state_changes"].extend(ask_changes)
            _merge_extras(result, extras)
        return result

    if itype == "ask_about_topic":
        blocks, changes, extras = _resolve_ask_about_topic(
            world_state, npc, rel, topic_id, intent, dice_ok, pressure, player_knowledge
        )
        result["narrative_blocks"].extend(blocks)
        result["npc_state_changes"].extend(changes)
        _merge_extras(result, extras)
        return result

    if itype in ("persuade", "intimidate", "deceive", "accuse"):
        blocks, changes, extras = _resolve_social_pressure(
            world_state, npc, rel, itype, topic_id, intent, dice_ok, player_knowledge
        )
        result["narrative_blocks"].extend(blocks)
        result["npc_state_changes"].extend(changes)
        _merge_extras(result, extras)
        return result

    if itype == "eavesdrop":
        return _resolve_eavesdrop(world_state, npc, dice_ok, result)

    result["narrative_blocks"].append(
        {"type": "result", "text": f"{name}对你的举动有些困惑。"}
    )
    return result


def _merge_extras(result: dict[str, Any], extras: dict[str, Any]) -> None:
    for k in ("new_facts", "new_observations", "new_questions", "new_rumors", "available_followups"):
        result[k].extend(extras.get(k) or [])


def _resolve_comfort_and_ask(
    state: GameState,
    npc: dict[str, Any],
    rel: dict[str, Any],
    intent: dict[str, Any],
    topic_id: str | None,
    dice_ok: bool,
    pressure: float,
    player_knowledge: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    name = str(npc.get("name"))
    topic = resolve_topic(intent=intent, topic_id=topic_id) or get_topic("missing_father")
    blocks = [
        {
            "type": "dialogue",
            "speaker": name,
            "text": "谢谢你愿意听我说……" if dice_ok else "我……我现在说不出更多。",
        }
    ]
    changes = [
        {
            "npc_id": npc.get("id"),
            "trust_delta": 5 if dice_ok else -2,
            "emotion": "distressed" if not dice_ok else "hopeful",
        }
    ]
    return blocks, changes


def _resolve_ask_about_topic(
    state: GameState,
    npc: dict[str, Any],
    rel: dict[str, Any],
    topic_id: str | None,
    intent: dict[str, Any],
    dice_ok: bool,
    pressure: float,
    player_knowledge: dict[str, Any],
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    extras = _empty_result()
    name = str(npc.get("name"))
    nid = str(npc.get("id"))
    topic = resolve_topic(intent=intent, topic_id=topic_id)
    blocks: list[dict] = []
    changes: list[dict] = []

    if not topic:
        blocks.append(
            {
                "type": "dialogue",
                "speaker": name,
                "text": "……你想问什么？说清楚一点。",
            }
        )
        return blocks, changes, extras

    tid = str(topic["id"])
    trust = int(rel.get("trust", 0))
    suspicion = int(rel.get("suspicion", 0))
    sensitivity = int(topic.get("sensitivity", 30))
    knows_topic = tid in [str(k.get("topic_id")) for k in (npc.get("knowledge") or []) if isinstance(k, dict)]
    knows_topic = knows_topic or nid in (topic.get("known_by") or [])

    if not knows_topic:
        blocks.extend(
            [
                {"type": "dialogue", "speaker": name, "text": "这事我不太清楚，你问别人吧。"},
                {"type": "consequence", "text": f"{name}似乎对「{topic['label']}」没有更多信息。"},
            ]
        )
        changes.append({"npc_id": nid, "suspicion_delta": 2})
        return blocks, changes, extras

    # 收集可揭示内容
    revealed_text: str | None = None
    reveal_level = "none"
    new_obs: dict[str, Any] | None = None

    for item in list(npc.get("knowledge") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("topic_id")) != tid:
            continue
        vis = str(item.get("visibility_to_player", "hidden"))
        if vis == "public" or trust >= sensitivity // 2:
            revealed_text = str(item.get("text"))
            reveal_level = "surface"
            new_obs = {
                "id": f"obs_{nid}_{item.get('id')}",
                "text": revealed_text,
                "source": "npc_dialogue",
            }
            break

    for sec in list(npc.get("secrets") or []):
        if not isinstance(sec, dict):
            continue
        if str(sec.get("topic_id")) != tid:
            continue
        cond = sec.get("reveal_conditions") or {}
        if _check_reveal_conditions(cond, rel=rel, topic_id=tid, dice_ok=dice_ok, crisis_pressure=pressure):
            revealed_text = str(sec.get("text"))
            reveal_level = "deep"
            new_obs = {
                "id": f"obs_{nid}_{sec.get('id')}",
                "text": revealed_text,
                "source": "npc_dialogue",
            }
            break

    # 低信任 / 高敏感：表层或回避
    if reveal_level == "none":
        if trust < 15 or suspicion > 40 or not dice_ok:
            outer = resolve_direction_phrase(state, "warehouse")
            if tid == "last_night_disturbance":
                blocks.extend(
                    [
                        {
                            "type": "dialogue",
                            "speaker": name,
                            "text": f"昨夜{outer}确实有些动静，细节现在不能说。",
                        },
                        {
                            "type": "consequence",
                            "text": f"{name}明显在回避具体细节。",
                        },
                    ]
                )
                extras["new_observations"].append(
                    {
                        "id": f"obs_{nid}_night_activity_surface",
                        "text": f"{name}承认昨夜{outer}有动静，但拒绝说明细节",
                        "source": "npc_dialogue",
                    }
                )
                register_player_topic(player_knowledge, tid)
            elif tid == "extra_patrol":
                blocks.extend(
                    [
                        {
                            "type": "dialogue",
                            "speaker": name,
                            "text": "巡逻是例行安排，别多想。",
                        },
                        {"type": "consequence", "text": f"{name}不愿解释加派巡逻的原因。"},
                    ]
                )
            else:
                blocks.append(
                    {
                        "type": "dialogue",
                        "speaker": name,
                        "text": "……我现在不能说太多。",
                    }
                )
            changes.append({"npc_id": nid, "trust_delta": -3, "suspicion_delta": 5, "emotion": "guarded"})
            return blocks, changes, extras

    if reveal_level == "surface" and revealed_text:
        blocks.extend(
            [
                {"type": "dialogue", "speaker": name, "text": revealed_text},
                {"type": "result", "text": f"{name}只肯透露表面信息。"},
            ]
        )
        if new_obs:
            extras["new_observations"].append(new_obs)
        register_player_topic(player_knowledge, tid)
        changes.append({"npc_id": nid, "trust_delta": 2})
        return blocks, changes, extras

    if reveal_level == "deep" and revealed_text:
        blocks.extend(
            [
                {"type": "dialogue", "speaker": name, "text": revealed_text},
                {"type": "result", "text": f"{name}在你取得信任后说出了更具体的情况。"},
            ]
        )
        if new_obs:
            extras["new_observations"].append(new_obs)
        register_player_topic(player_knowledge, tid)
        changes.append({"npc_id": nid, "trust_delta": 5, "emotion": "weary"})
        return blocks, changes, extras

    blocks.append({"type": "dialogue", "speaker": name, "text": "……"})
    return blocks, changes, extras


def _resolve_social_pressure(
    state: GameState,
    npc: dict[str, Any],
    rel: dict[str, Any],
    itype: str,
    topic_id: str | None,
    intent: dict[str, Any],
    dice_ok: bool,
    player_knowledge: dict[str, Any],
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    extras = _empty_result()
    name = str(npc.get("name"))
    nid = str(npc.get("id"))
    if itype == "persuade" and dice_ok:
        blocks = [{"type": "dialogue", "speaker": name, "text": "……好吧，我告诉你一点。"}]
        changes = [{"npc_id": nid, "trust_delta": 8, "suspicion_delta": -5}]
        _, _, ask_extras = _resolve_ask_about_topic(
            state, npc, rel, topic_id, intent, True, _crisis_pressure(state), player_knowledge
        )
        _merge_extras(extras, ask_extras)
        return blocks, changes, extras
    blocks = [{"type": "dialogue", "speaker": name, "text": f"{name}没有被你说服。"}]
    changes = [{"npc_id": nid, "trust_delta": -5, "suspicion_delta": 10, "emotion": "hostile"}]
    return blocks, changes, extras


def _resolve_eavesdrop(
    state: GameState,
    npc: dict[str, Any],
    dice_ok: bool,
    result: dict[str, Any],
) -> dict[str, Any]:
    name = str(npc.get("name"))
    if dice_ok:
        patrol = resolve_direction_phrase(state, "warehouse") or "村口外侧"
        result["narrative_blocks"].extend(
            [
                {"type": "scene", "text": "你屏息靠近，听清压低的声音。"},
                {
                    "type": "dialogue",
                    "speaker": name,
                    "text": f"『今夜加强{patrol}巡逻，双哨换岗。』",
                },
                {"type": "result", "text": f"你听清{name}下达的巡逻命令。"},
            ]
        )
        result["new_observations"].append(
            {
                "id": "fact_thomas_extra_patrol",
                "text": f"托马斯正在加派{patrol}哨岗",
                "source": "npc_order",
            }
        )
        state.flags["heard_thomas_order"] = True
    else:
        result["narrative_blocks"].append(
            {"type": "result", "text": "人声嘈杂，你没能听清他们在说什么。"}
        )
    return result


def _resolve_eavesdrop_order(
    state: GameState,
    npc: dict[str, Any],
    player_knowledge: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    return _resolve_eavesdrop(state, npc, True, result)


def resolve_observe_target(
    target: str,
    target_type: str,
    scene_graph: dict[str, Any],
    player_knowledge: dict[str, Any],
    world_state: GameState,
    dice: DiceRollInfo | None = None,
    *,
    fact_id: str | None = None,
) -> dict[str, Any]:
    """通用观察：NPC 或地点。"""
    result = _empty_result()
    dice_ok = _dice_ok(dice)
    loc = str(scene_graph.get("location") or world_state.location)

    if target_type == "npc" or target in NAME_NPC_IDS:
        nid = npc_id_from_name(target) if target not in ("mira", "thomas", "elena") else target
        npc = get_npc_state(world_state, nid)
        if not npc:
            result["narrative_blocks"].append({"type": "result", "text": "你没有看到明确的目标。"})
            return result
        name = str(npc.get("name"))
        emotion = str(npc.get("current_emotion", "平静"))
        activity = str(npc.get("current_activity", "停留"))
        rel = get_player_relationship(npc)

        if dice_ok:
            if nid == "mira":
                text = "米拉在艾琳娜求助时一直观察广场，没有主动出面。"
                obs_id = "fact_mira_watching_square"
            else:
                from engine.narrative_formatter import format_npc_activity_line

                text = format_npc_activity_line(name, activity, emotion)
                obs_id = f"obs_{nid}_{activity}"
            result["narrative_blocks"].extend(
                [
                    {"type": "scene", "text": f"你注视{name}的一举一动。"},
                    {"type": "result", "text": text},
                    {"type": "consequence", "text": f"你确认{name}并非单纯旁观。"},
                ]
            )
            result["new_observations"].append(
                {"id": obs_id, "text": text, "source": "player_observation"}
            )
        else:
            unclear_id = fact_id or f"{nid}_observe_unclear"
            result["narrative_blocks"].extend(
                [
                    {"type": "scene", "text": f"{name}似乎在门帘或人群后停留。"},
                    {
                        "type": "consequence",
                        "text": "需要换个角度再观察。",
                    },
                ]
            )
            obs_id = (
                "mira_behind_tavern_curtain_unclear"
                if nid == "mira"
                else f"obs_{unclear_id}"
            )
            obs_text = (
                f"{name}似乎仍在附近停留，但你没看清其在看什么"
                if nid == "mira"
                else f"你没看清{name}正在做什么"
            )
            result["new_observations"].append(
                {"id": obs_id, "text": obs_text, "source": "player_observation"}
            )
            label = f"换个角度观察{name}" if nid != "mira" else "换个角度观察酒馆门帘后的米拉"
            result["available_followups"] = [
                {
                    "id": f"change_angle_observe_{nid}",
                    "label": label,
                    "source_fact": obs_id,
                    "reason": "上一轮观察未能看清细节",
                    "category": "investigate",
                    "intent": {
                        "action_type": "observe",
                        "target": nid,
                        "target_type": "npc",
                        "interaction_type": "observe",
                    },
                },
                {
                    "id": f"approach_ask_{nid}",
                    "label": f"走近{name}，直接询问刚才看到了什么",
                    "source_fact": obs_id,
                    "reason": "观察未果，可改为当面询问",
                    "category": "social",
                    "intent": {
                        "action_type": "talk",
                        "target": name,
                        "interaction_type": "ask_about_topic",
                    },
                },
            ]
        if rel.get("suspicion", 0) > 30 and dice_ok:
            result["npc_state_changes"].append(
                {"npc_id": nid, "suspicion_delta": 3, "emotion": "guarded"}
            )
        return result

    # 地点观察
    objects = list(scene_graph.get("interactive_objects") or [])
    if dice_ok and objects:
        focus = objects[0]
        result["narrative_blocks"].append(
            {"type": "result", "text": f"你注意到{loc}的{focus}，没有新的异常。"}
        )
    else:
        result["narrative_blocks"].append(
            {"type": "result", "text": f"你没有在{loc}发现更多可见细节。"}
        )
    return result


NAME_NPC_IDS = {"mira", "thomas", "elena", "varick"}


def interaction_result_to_pipeline(
    interaction: dict[str, Any],
    *,
    resolver_name: str,
    check_succeeded: bool = True,
) -> dict[str, Any]:
    """转换为 action_resolvers / game_loop 兼容格式。"""
    blocks = interaction.get("narrative_blocks") or []
    beats = {
        "scene_note": "",
        "direct_result": "",
        "npc_reaction": "",
        "new_information": None,
        "consequence": "",
    }
    dialogue_parts: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        txt = str(b.get("text", ""))
        if t == "scene":
            beats["scene_note"] = txt
        elif t == "dialogue":
            sp = b.get("speaker", "")
            dialogue_parts.append(f"{sp}：{txt}" if sp else txt)
        elif t == "result":
            beats["direct_result"] = txt
        elif t == "consequence":
            beats["consequence"] = txt
    if dialogue_parts:
        beats["npc_reaction"] = " ".join(dialogue_parts)
    if interaction.get("new_observations"):
        beats["new_information"] = str(interaction["new_observations"][0].get("text", ""))

    action_result = {
        "narrative_blocks": blocks,
        "new_facts": interaction.get("new_facts") or [],
        "new_observations": interaction.get("new_observations") or [],
        "new_questions": interaction.get("new_questions") or [],
        "new_rumors": interaction.get("new_rumors") or [],
        "available_followups": interaction.get("available_followups") or [],
    }
    return {
        "handled": True,
        "resolver_name": resolver_name,
        "changes": {"check_succeeded": check_succeeded},
        "beats": beats,
        "action_result": action_result,
        "npc_state_changes": interaction.get("npc_state_changes") or [],
    }


def run_universal_resolution(
    state: GameState,
    action_id: str,
    intent: dict[str, Any],
    dice: DiceRollInfo | None,
    scene_graph: dict[str, Any] | None,
    player_knowledge: dict[str, Any],
) -> dict[str, Any] | None:
    """尝试 V2 解析；返回 None 表示未适配。"""
    from engine.action_id_adapter import adapt_action_id

    params = adapt_action_id(action_id, intent)
    if not params and intent.get("interaction_type") in INTERACTION_TYPES:
        params = dict(intent)

    scene_graph = scene_graph if isinstance(scene_graph, dict) else {}
    ensure_npc_states(state)

    if params and params.get("interaction_type") == "observe":
        target = str(params.get("target_npc_id") or intent.get("target") or "")
        interaction = resolve_observe_target(
            target,
            str(params.get("observe_target_type") or "npc"),
            scene_graph,
            player_knowledge,
            state,
            dice,
            fact_id=str(intent.get("fact_id") or ""),
        )
        apply_npc_state_changes(state, interaction.get("npc_state_changes") or [])
        return interaction_result_to_pipeline(
            interaction,
            resolver_name="interaction_resolver.observe",
            check_succeeded=_dice_ok(dice),
        )

    if not params or not params.get("target_npc_id"):
        return None

    interaction = resolve_interaction(
        actor="player",
        target_npc_id=str(params["target_npc_id"]),
        intent=intent,
        scene_graph=scene_graph,
        player_knowledge=player_knowledge,
        world_state=state,
        interaction_type=str(params.get("interaction_type") or "ask_about_topic"),
        topic_id=params.get("topic_id"),
        dice=dice,
        secondary_type=params.get("secondary_type"),
        special=params.get("special"),
    )
    apply_npc_state_changes(state, interaction.get("npc_state_changes") or [])
    return interaction_result_to_pipeline(
        interaction,
        resolver_name="interaction_resolver",
        check_succeeded=_dice_ok(dice),
    )

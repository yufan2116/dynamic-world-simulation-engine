"""动态行动生成 — 由世界状态驱动，非 hardcode 列表。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.grounding import filter_actions_payload
from engine.demo_runner import filter_demo_actions_payload, is_demo_story_mode
from engine.location_registry import resolve_direction_phrase
from engine.player_knowledge import (
    build_player_visible,
    ensure_player_knowledge,
    get_player_knowledge,
)
from engine.choice_validator import validate_choices_payload
from engine.text_sanitizer import build_rumor_action_label, rumor_source_type_allowed, sanitize_player_text
from engine.world_state import GameState
from engine.world_state import ensure_player_known_facts
from engine.world_templates import location_connections_for_state

CATEGORIES = ("investigate", "social", "stealth", "survival", "free")
CATEGORY_LABELS = {
    "investigate": "调查",
    "social": "社交",
    "stealth": "潜行",
    "survival": "生存",
    "free": "自由行动",
}


class DynamicAction(BaseModel):
    id: str
    label: str
    input: str
    category: str
    intent: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, str] | None = None
    source_fact: str = ""
    reason: str = ""
    uses_known_fact: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    reveals: list[dict[str, Any]] = Field(default_factory=list)
    risk: str = "medium"
    description: str = ""
    unlocked: bool = True
    lock_reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    scene_requirements: dict[str, Any] = Field(default_factory=dict)
    consumable: bool = False


def _is_night(state: GameState) -> bool:
    return state.time_of_day in ("凌晨", "深夜")


def _is_stormy(state: GameState) -> bool:
    return state.weather in ("暴雨", "暴雨初歇", "阴云", "浓雾")


def _player_mod(state: GameState, ability: str) -> int:
    return state.player.get_modifier(ability)


def _has_clue(state: GameState, key: str) -> bool:
    return bool(state.flags.get(key))


def _npc_here(state: GameState, name: str):
    for n in state.npc_at_location():
        if n.name == name:
            return n
    return None


def _add(
    bucket: dict[str, list[DynamicAction]],
    action: DynamicAction,
) -> None:
    cat = action.category if action.category in CATEGORIES else "investigate"
    if action.id not in {a.id for a in bucket.get(cat, [])}:
        bucket.setdefault(cat, []).append(action)


def _move_label(state: GameState, dest: str) -> str:
    if _is_night(state):
        return f"趁夜色潜行前往{dest}"
    if _is_stormy(state):
        return f"冒雨赶往{dest}"
    if state.time_of_day == "正午":
        return f"在日光下步行至{dest}"
    return f"沿小路前往{dest}"


def _minimal_play_context(state: GameState) -> dict[str, Any]:
    """仅含移动/休息等基础玩法所需的最小上下文（非隐藏模拟状态）。"""
    return {
        "location": state.location,
        "consumed_actions": list(state.flags.get("consumed_actions") or []),
        "heard_thomas_order": bool(state.flags.get("heard_thomas_order")),
        "opening_scene": bool(state.flags.get("opening_scene")),
        "guard_patrol_active": bool(state.flags.get("guard_patrol_active")),
        "guards_private_conversation": bool(state.flags.get("guards_private_conversation")),
        "warehouse_searched": bool(state.flags.get("warehouse_searched")),
        "varick_revealed": bool(state.flags.get("varick_revealed")),
        "plea_letter_found": bool(state.flags.get("plea_letter_found")),
        "bandit_raid": bool(state.flags.get("bandit_raid")),
        "clue_found": bool(state.flags.get("clue_found")),
    }


def generate_from_knowledge(
    player_knowledge: dict[str, Any],
    scene_graph: dict[str, Any],
    play_context: dict[str, Any],
    *,
    state: GameState | None = None,
) -> dict[str, Any]:
    """仅从 player_knowledge + scene_graph.player_visible 生成分组行动。"""
    pv = scene_graph.get("player_visible") or scene_graph
    loc = str(pv.get("location") or play_context.get("location") or "村口")
    if state and is_demo_story_mode(state):
        consumed: set[str] = set()
    else:
        consumed = set(str(x) for x in (play_context.get("consumed_actions") or []))
    known_locations = set(str(x) for x in (pv.get("known_locations") or []))
    if loc:
        known_locations.add(loc)

    active_event_ids: set[str] = set()
    for ev in pv.get("active_events") or []:
        if isinstance(ev, dict) and ev.get("id"):
            active_event_ids.add(str(ev["id"]))
    if play_context.get("guard_patrol_active"):
        active_event_ids.add("thomas_calling_extra_patrol")

    player = state.player if state else None
    wis_mod = _player_mod(state, "WIS") if state else 0
    cha_mod = _player_mod(state, "CHA") if state else 0
    dex_mod = _player_mod(state, "DEX") if state else 0
    night = _is_night(state) if state else False
    storm = _is_stormy(state) if state else False

    buckets: dict[str, list[DynamicAction]] = {c: [] for c in CATEGORIES}

    # --- 1. available_followups（正式版 resolver hooks；Demo 不从此处生成按钮）---
    followup_source = (
        []
        if (state and is_demo_story_mode(state))
        else (player_knowledge.get("available_followups") or [])
    )
    for fu in followup_source:
        if not isinstance(fu, dict):
            continue
        fid = str(fu.get("id", "")).strip()
        if not fid or fid in consumed:
            continue
        sf = str(fu.get("source_fact", "")).strip()
        label = str(fu.get("label", "")).strip()
        if not sf or not label:
            continue
        from engine.narrative_formatter import humanize_action_label

        intent_fu = fu.get("intent") if isinstance(fu.get("intent"), dict) else {}
        label = humanize_action_label(
            label,
            state=state,
            source_fact=sf,
            category=str(fu.get("category") or "investigate"),
            target=str(intent_fu.get("target") or ""),
        )
        cat = str(fu.get("category") or "investigate")
        intent = dict(fu.get("intent") if isinstance(fu.get("intent"), dict) else {})
        intent.setdefault("action_id", fid)
        _add(
            buckets,
            DynamicAction(
                id=fid,
                label=label,
                input=label,
                category=cat if cat in CATEGORIES else "investigate",
                intent=intent,
                source_fact=sf,
                reason=str(fu.get("reason") or ""),
                uses_known_fact=[sf],
                risk="low",
                tags=["follow_up"],
            ),
        )

    # --- 2. 基于已知观察的具象追查（禁止泛化 follow_clue）---
    for obs in (player_knowledge.get("observations") or [])[-5:]:
        if not isinstance(obs, dict):
            continue
        oid = str(obs.get("id", "")).strip()
        text = str(obs.get("text", "")).strip()
        if not oid or not text:
            continue
        if oid == "pf_mira_observing" and "observe_mira_at_tavern" not in consumed:
            _add(
                buckets,
                DynamicAction(
                    id="observe_mira_at_tavern",
                    label="走向酒馆门口，观察米拉刚才在门帘后看到了什么",
                    input="观察酒馆门帘后的米拉",
                    category="investigate",
                    intent={
                        "action_type": "observe",
                        "target": "mira",
                        "location": "tavern",
                        "fact_id": oid,
                    },
                    source_fact=oid,
                    reason="开场已注意到米拉在门帘后观察",
                    uses_known_fact=[oid],
                    risk="low",
                    tags=["opening"],
                ),
            )
        elif oid == "mira_behind_tavern_curtain_unclear":
            continue  # 由 available_followups 提供具象选项
        elif f"follow_{oid}" not in consumed and "沿着你刚确认" not in text:
            from engine.narrative_formatter import humanize_action_label

            short = text[:22] + "…" if len(text) > 22 else text
            follow_label = humanize_action_label(
                f"针对「{short}」继续调查",
                state=state,
                source_fact=oid,
                category="investigate",
            )
            _add(
                buckets,
                DynamicAction(
                    id=f"follow_{oid}",
                    label=follow_label,
                    input=f"继续追查：{text}",
                    category="investigate",
                    intent={
                        "action_type": "investigate",
                        "target": "player_observation",
                        "fact_id": oid,
                    },
                    source_fact=oid,
                    reason="基于你已确认的现场观察",
                    uses_known_fact=[oid],
                    risk="low",
                    tags=["follow_up"],
                    consumable=True,
                ),
            )

    if not state:
        return _finalize_buckets(buckets, player_knowledge, consumed, None)

    # 以下需要最小 play_context + state（移动/在场 NPC），不读取 crisis hidden
    return _generate_scene_and_survival(
        state,
        buckets,
        player_knowledge,
        pv,
        play_context,
        loc=loc,
        consumed=consumed,
        known_locations=known_locations,
        active_event_ids=active_event_ids,
        player=player,
        wis_mod=wis_mod,
        cha_mod=cha_mod,
        dex_mod=dex_mod,
        night=night,
        storm=storm,
    )


def _pk_has_fact_id(player_knowledge: dict[str, Any], fact_id: str) -> bool:
    for bucket in ("facts", "observations", "rumors"):
        for item in player_knowledge.get(bucket) or []:
            if isinstance(item, dict) and str(item.get("id")) == fact_id:
                return True
    return False


def _generate_demo_knowledge_actions(
    state: GameState,
    buckets: dict[str, list[DynamicAction]],
    player_knowledge: dict[str, Any],
    pv: dict[str, Any],
    consumed: set[str],
    scene_source: str,
) -> None:
    """Demo：由 player_knowledge 推导的追问/跟进（非脚本 available_followups）。"""
    from engine.npc_state import visible_npc_entries

    visible = {str(n.get("id")) for n in visible_npc_entries(state, {"player_visible": pv})}

    if (
        "elena" in visible
        and _pk_has_fact_id(player_knowledge, "clue_elena_cargo")
        and not _pk_has_fact_id(player_knowledge, "fact_elena_cargo_detail")
        and "ask_elena_cargo_detail" not in consumed
    ):
        _add(
            buckets,
            DynamicAction(
                id="ask_elena_cargo_detail",
                label="追问艾琳娜：她父亲提到的「货」是什么",
                input="追问艾琳娜货物详情",
                category="social",
                intent={
                    "action_type": "talk",
                    "target": "艾琳娜",
                    "topic_id": "cargo",
                    "interaction_type": "ask_about_topic",
                },
                source_fact="clue_elena_cargo",
                reason="艾琳娜刚提到一批货",
                uses_known_fact=["clue_elena_cargo"],
                tags=["demo_knowledge"],
            ),
        )

    if (
        "thomas" in visible
        and _pk_has_fact_id(player_knowledge, "observation_thomas_nervous")
        and not _pk_has_fact_id(player_knowledge, "clue_thomas_patrol")
        and "ask_thomas_last_night" not in consumed
    ):
        _add(
            buckets,
            DynamicAction(
                id="ask_thomas_warehouse_activity",
                label="向托马斯打听昨夜仓库方向是否有人出入",
                input="询问托马斯昨夜仓库方向的动静",
                category="social",
                intent={
                    "action_type": "talk",
                    "target": "托马斯",
                    "topic_id": "warehouse_activity",
                },
                source_fact="observation_thomas_nervous",
                reason="托马斯对仓库方向异常紧张",
                uses_known_fact=["observation_thomas_nervous"],
                tags=["demo_knowledge"],
            ),
        )


def _generate_entity_based_actions(
    state: GameState,
    buckets: dict[str, list[DynamicAction]],
    player_knowledge: dict[str, Any],
    pv: dict[str, Any],
    consumed: set[str],
    scene_source: str,
) -> None:
    """从可见实体 + known topics 生成选项（V2）。"""
    from engine.npc_state import npc_id_from_name, visible_npc_entries
    from engine.topic_resolver import TOPIC_REGISTRY, get_topic, player_knows_topic

    visible = visible_npc_entries(state, {"player_visible": pv})
    visible_ids = {str(n.get("id")) for n in visible}

    for npc_data in visible:
        nid = str(npc_data.get("id", ""))
        name = str(npc_data.get("name", ""))
        if not nid or not name:
            continue
        obs_id = f"observe_{nid}_reaction"
        if obs_id not in consumed:
            _add(
                buckets,
                DynamicAction(
                    id=obs_id,
                    label=f"观察{name}的反应与举止",
                    input=f"观察{name}的反应",
                    category="investigate",
                    intent={
                        "action_type": "observe",
                        "target": nid,
                        "target_type": "npc",
                        "interaction_type": "observe",
                    },
                    source_fact=scene_source,
                    reason=f"{name}在场，可观察其举止",
                    tags=["entity_observe"],
                ),
            )
        for tid, spec in TOPIC_REGISTRY.items():
            known_by = spec.get("known_by") or []
            if nid not in known_by:
                continue
            act_id = f"ask_{nid}_{tid}"
            if act_id in consumed:
                continue
            label = f"询问{name}关于「{spec.get('label', tid)}」"
            _add(
                buckets,
                DynamicAction(
                    id=act_id,
                    label=label,
                    input=label,
                    category="social",
                    intent={
                        "action_type": "talk",
                        "target": name,
                        "interaction_type": "ask_about_topic",
                        "topic_id": tid,
                    },
                    source_fact=scene_source,
                    reason=f"{name}可能了解「{spec.get('label')}」",
                    tags=["entity_ask"],
                ),
            )
        if nid == "elena":
            comfort_id = "comfort_elena"
            if comfort_id not in consumed:
                _add(
                    buckets,
                    DynamicAction(
                        id=comfort_id,
                        label=f"安抚{name}，询问她父亲失踪的细节",
                        input=f"安抚{name}",
                        category="social",
                        intent={
                            "action_type": "talk",
                            "target": name,
                            "interaction_type": "comfort",
                            "topic_id": "missing_father",
                        },
                        source_fact="pf_elena_help",
                        reason="艾琳娜正在求助",
                        tags=["entity_comfort"],
                    ),
                )

    for tid in list(player_knowledge.get("known_topics") or []):
        topic = get_topic(str(tid))
        if not topic:
            continue
        for other_nid in topic.get("known_by") or []:
            if other_nid not in visible_ids:
                continue
            other = next((n for n in visible if str(n.get("id")) == other_nid), None)
            if not other:
                continue
            oname = str(other.get("name"))
            act_id = f"verify_{tid}_with_{other_nid}"
            if act_id in consumed:
                continue
            if player_knows_topic(player_knowledge, str(tid)):
                _add(
                    buckets,
                    DynamicAction(
                        id=act_id,
                        label=f"向{oname}求证：{topic.get('label', tid)}",
                        input=f"向{oname}求证{topic.get('label')}",
                        category="social",
                        intent={
                            "action_type": "talk",
                            "target": oname,
                            "interaction_type": "ask_about_topic",
                            "topic_id": tid,
                        },
                        source_fact=str(tid),
                        reason="你已掌握该话题的部分信息，可向他人求证",
                        tags=["topic_verify"],
                    ),
                )

    for obj in list(pv.get("interactive_objects") or [])[:3]:
        if not isinstance(obj, str) or len(obj) < 2:
            continue
        oid = f"inspect_obj_{abs(hash(obj)) % 100000}"
        if oid in consumed:
            continue
        _add(
            buckets,
            DynamicAction(
                id=oid,
                label=f"仔细检查：{obj}",
                input=f"检查{obj}",
                category="investigate",
                intent={
                    "action_type": "investigate",
                    "target": "object",
                    "object_id": obj,
                    "interaction_type": "observe",
                    "target_type": "object",
                },
                source_fact=scene_source,
                reason="场景中存在可调查对象",
                tags=["entity_object"],
            ),
        )


def _generate_scene_and_survival(
    state: GameState,
    buckets: dict[str, list[DynamicAction]],
    player_knowledge: dict[str, Any],
    pv: dict[str, Any],
    play_context: dict[str, Any],
    *,
    loc: str,
    consumed: set[str],
    known_locations: set[str],
    active_event_ids: set[str],
    player: Any,
    wis_mod: int,
    cha_mod: int,
    dex_mod: int,
    night: bool,
    storm: bool,
) -> dict[str, Any]:
    """场景互动、社交、移动等（不读取 crisis 隐藏字段）。"""
    scene_source = f"scene:{loc}"

    # --- 调查 ---
    obs_desc = "留意脚印、血迹与异常声响"
    if storm:
        obs_desc = "雨声掩盖了很多声音，但仍可寻找被冲乱的新痕迹"
    if night:
        obs_desc = "夜色中细节难辨，需格外专注"
    _add(
        buckets,
        DynamicAction(
            id=f"inspect_{loc}_environment" if loc == "村口" else f"observe_{loc}",
            label=f"仔细观察{loc}周围的环境",
            input=f"仔细观察{loc}周围的环境",
            category="investigate",
            intent={
                "action_type": "investigate",
                "target": "environment",
                "location": "current",
            },
            risk="low",
            description=obs_desc,
            source_fact=scene_source,
            reason=f"你当前在{loc}，可观察周围环境",
            tags=["perception"],
        ),
    )

    if wis_mod >= 2 and not _has_clue(state, "clue_found"):
        _add(
            buckets,
            DynamicAction(
                id="keen_sense",
                label="屏息凝神，搜寻被忽略的细节",
                input="屏息凝神搜寻环境中的隐藏细节",
                category="investigate",
                intent={"action_type": "investigate", "target": "hidden_details", "location": "current"},
                risk="medium",
                description=f"高感知（WIS {player.wisdom}）让你更易发现蛛丝马迹",
                tags=["wis", "unlock"],
                source_fact=scene_source,
                reason="高感知角色可搜寻隐藏细节",
            ),
        )

    if loc == "仓库" and "仓库" in known_locations and not play_context.get("warehouse_searched"):
        _add(
            buckets,
            DynamicAction(
                id="search_warehouse",
                label="翻查货箱与角落，寻找失踪者痕迹",
                input="搜查仓库中的货物与箱子",
                category="investigate",
                intent={"action_type": "investigate", "target": "warehouse", "location": "current"},
                risk="high",
                description="仓库与商人失踪直接相关",
            ),
        )

    if loc == "森林小路":
        if not play_context.get("varick_revealed"):
            _add(
                buckets,
                DynamicAction(
                    id="track_forest",
                    label="沿泥泞小径追踪可疑足迹",
                    input="沿小路追踪可疑脚印",
                    category="investigate",
                    description="林间的足迹或许指向真相",
                    unlocked=_has_clue(state, "clue_found") or wis_mod >= 1,
                    lock_reason="尚无方向，需先在别处找到线索" if not (_has_clue(state, "clue_found") or wis_mod >= 1) else None,
                ),
            )
        else:
            _add(
                buckets,
                DynamicAction(
                    id="confront_varick",
                    label="直面瓦里克与其手下",
                    input="与瓦里克对峙",
                    category="investigate",
                    description="强盗现身，必须做出抉择",
                ),
            )

    if play_context.get("plea_letter_found") and loc in ("森林小路", "仓库"):
        _add(
            buckets,
            DynamicAction(
                id="follow_plea_letter",
                label="按求救信残页指示的方向搜索",
                input="调查求救信提到的方向",
                category="investigate",
                description="残页上的字迹或许指向马库斯",
            ),
        )

    # 禁止：直接使用 crisis internal recent_anomalies 生成选项（会泄露 hidden escalation）

    _generate_entity_based_actions(
        state,
        buckets,
        player_knowledge,
        pv,
        consumed,
        scene_source,
    )
    if state and is_demo_story_mode(state):
        _generate_demo_knowledge_actions(
            state,
            buckets,
            player_knowledge,
            pv,
            consumed,
            scene_source,
        )

    # --- 社交 ---
    if play_context.get("opening_scene") and loc == "村口":
        _add(
            buckets,
            DynamicAction(
                id="ask_elena_father_details",
                label="上前安慰冲进广场的艾琳娜，询问细节",
                input="安慰艾琳娜并询问商人失踪的细节",
                category="social",
                intent={
                    "action_type": "talk",
                    "target": "艾琳娜",
                    "location": "current",
                    "topic": "父亲失踪",
                },
            risk="low",
                description="她刚刚哭喊着冲进来，或许知道关键细节",
                tags=["opening"],
                source_fact="pf_elena_help" if any(
                    isinstance(f, dict) and f.get("id") == "pf_elena_help"
                    for f in (player_knowledge.get("facts") or [])
                ) else scene_source,
                reason="艾琳娜正在广场求助",
            ),
        )

    for npc in state.npc_at_location():
        att = npc.attitude_value
        if att >= 20:
            tone = "友好地"
            desc = f"{npc.name}对你态度尚可（{npc.attitude}）"
        elif att <= -20:
            tone = "谨慎地"
            desc = f"{npc.name}对你保持警惕（{npc.attitude}）"
        else:
            tone = ""
            desc = f"{npc.name}态度{npc.attitude}"

        talk_id = f"talk_{npc.name}"
        if npc.name == "艾琳娜":
            label = f"{tone}安慰艾琳娜，询问她父亲失踪的细节".strip()
            inp = "安慰艾琳娜并询问商人失踪的细节"
            talk_id = "ask_elena_father_details"
        elif npc.name == "托马斯":
            label = f"{tone}询问托马斯昨夜是否听见异常动静".strip()
            inp = "询问托马斯昨夜异常情况"
            talk_id = "ask_thomas_last_night"
        elif npc.name == "米拉":
            label = f"{tone}与米拉交谈，探听酒馆里的消息".strip()
            inp = "与米拉交谈"
        elif npc.name == "瓦里克":
            label = "与瓦里克交涉，试探其底线"
            inp = "与瓦里克对话"
        else:
            label = f"{tone}与{npc.name}交谈".strip()
            inp = f"与{npc.name}交谈"

        _add(
            buckets,
            DynamicAction(
                id=talk_id,
                label=label,
                input=inp,
                category="social",
                intent={
                    "action_type": "talk",
                    "target": npc.name,
                    "location": "current",
                    "topic": inp,
                },
                risk="low",
                description=desc,
                source_fact=scene_source,
                reason=f"{npc.name}在场，可交谈",
            ),
        )

        if cha_mod >= 2 and att < 20:
            _add(
                buckets,
                DynamicAction(
                    id=f"persuade_{npc.name}",
                    label=f"尝试说服{npc.name}透露更多内情",
                    input=f"说服{npc.name}告诉我所知的一切",
                    category="social",
                    intent={"action_type": "persuade", "target": npc.name, "location": "current"},
                    risk="medium",
                    description=f"魅力（CHA {player.charisma}）或可打开局面",
                    unlocked=att > -40,
                    lock_reason=f"{npc.name}对你过于敌意，难以说服" if att <= -40 else None,
                    tags=["cha", "unlock"],
                ),
            )

    # --- 来源可追溯 rumor：仅 player_knowledge.rumors ---
    rumors = player_knowledge.get("rumors") or []
    if rumors:
        for r in rumors[-3:]:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id", ""))
            txt = str(r.get("text", "")).strip()
            src_lbl = str(r.get("source_label") or r.get("source", "")).strip()
            st = str(r.get("source_type", "npc")).strip().lower()
            if not rid or not txt or not src_lbl or src_lbl == "未知来源":
                continue
            if st == "location" or src_lbl in ("村口", "酒馆", "仓库"):
                continue
            if not rumor_source_type_allowed(st):
                continue
            label = build_rumor_action_label(r)
            if not label or not sanitize_player_text(label, state):
                continue
            target = src_lbl if st == "npc" else ""
            _add(
                buckets,
                DynamicAction(
                    id=f"rumor_{rid}",
                    label=label,
                    input=label,
                    category="social",
                    intent={
                        "action_type": "talk" if target else "investigate",
                        "target": target or "overheard_group",
                        "location": "current",
                        "rumor_id": rid,
                    },
                    source={"type": st, "id": rid, "label": src_lbl},
                    source_fact=rid,
                    reason=f"你已听说：{txt[:20]}",
                    uses_known_fact=[rid],
                    risk="low",
                    description="",
                    tags=["rumor", "source_grounded"],
                ),
            )

    # --- 潜行 ---
    if _npc_here(state, "托马斯") and loc in ("村口", "仓库"):
        # 需要 scene_graph.active_events 显式出现“guards_private_conversation”
        if "guards_private_conversation" in active_event_ids and "eavesdrop_guards" not in consumed:
            _add(
                buckets,
                DynamicAction(
                    id="eavesdrop_guards",
                    label="趁守卫在角落低声交谈时，靠近听清他们在说什么",
                    input="偷听守卫谈话",
                    category="stealth",
                    intent={"action_type": "investigate", "target": "guards_private_conversation", "location": "current"},
                    description="来源：在场守卫 · 角落低语 · 当回合可见",
                    unlocked=night or dex_mod >= 2,
                    lock_reason="白天难以不被发现，需更高敏捷或等待夜晚" if not (night or dex_mod >= 2) else None,
                    tags=["dex", "night", "unlock"],
                    scene_requirements={
                        "required_visible_npcs": ["托马斯"],
                        "required_active_events": ["guards_private_conversation"],
                        "required_location": str(loc),
                        "required_known_facts": [],
                        "required_visible_objects": [],
                    },
                    consumable=True,
                ),
            )

    # 若有托马斯正在下令加派哨岗，可生成“听清命令”类（而不是偷听私谈）
    thomas_patrol_fact = "fact_thomas_extra_patrol"
    has_patrol_fact = any(
        isinstance(x, dict) and x.get("id") == thomas_patrol_fact
        for x in (player_knowledge.get("observations") or []) + (player_knowledge.get("facts") or [])
    )
    if (("hear_thomas_order" in consumed) or play_context.get("heard_thomas_order")) and has_patrol_fact:
        dir_phrase = resolve_direction_phrase(state, "warehouse")
        _add(
            buckets,
            DynamicAction(
                id="ask_thomas_patrol_reason",
                label=f"追问托马斯为什么要加强{dir_phrase}巡逻",
                input="追问托马斯加强巡逻的原因",
                category="social",
                intent={"action_type": "talk", "target": "托马斯", "location": "current"},
                risk="low",
                description="你已听清他的命令，可以追问动机",
                tags=["follow_up", "thomas_order"],
                source_fact=thomas_patrol_fact,
                reason="你已听清托马斯加派巡逻的命令",
            ),
        )
        if _npc_here(state, "托马斯"):
            _add(
                buckets,
                DynamicAction(
                    id="watch_guards_departure",
                    label="观察两名守卫离开时走向哪里",
                    input="观察守卫离开的方向",
                    category="investigate",
                    intent={"action_type": "investigate", "target": "guard_departure", "location": "current"},
                    risk="low",
                    tags=["follow_up", "thomas_order"],
                ),
            )
        if loc != "酒馆" and "米拉" in {n.name for n in state.npcs.values() if n.present}:
            _add(
                buckets,
                DynamicAction(
                    id="ask_mira_guard_movement",
                    label="前往酒馆询问米拉是否注意到守卫调动",
                    input="询问米拉是否看到守卫调动",
                    category="social",
                    intent={"action_type": "talk", "target": "米拉", "location": "酒馆"},
                    risk="low",
                    tags=["follow_up", "thomas_order"],
                ),
            )
        if _npc_here(state, "艾琳娜") or play_context.get("opening_scene"):
            _add(
                buckets,
                DynamicAction(
                    id="comfort_elena_father_time",
                    label="安慰艾琳娜，并确认她父亲昨夜离开的时间",
                    input="安慰艾琳娜并询问父亲离开时间",
                    category="social",
                    intent={"action_type": "talk", "target": "艾琳娜", "location": "current"},
                    risk="low",
                    tags=["follow_up"],
                ),
            )

    if "thomas_calling_extra_patrol" in active_event_ids and "hear_thomas_order" not in consumed:
        patrol_phrase = resolve_direction_phrase(state, "warehouse")
        patrol_label = (
            f"托马斯正在加派{patrol_phrase}哨岗"
            if patrol_phrase
            else "托马斯正在加派村口外侧哨岗"
        )
        patrol_desc = (
            f"你当场听见托马斯要求今夜加强{patrol_phrase}的巡逻与哨岗。"
            if patrol_phrase
            else "你当场听见托马斯要求今夜加强村口外侧的巡逻与哨岗。"
        )
        _add(
            buckets,
            DynamicAction(
                id="hear_thomas_order",
                label="靠近听清托马斯正在下达的巡逻命令",
                input="听清托马斯下达的巡逻命令",
                category="investigate",
                intent={"action_type": "investigate", "target": "thomas_order", "location": "current"},
                description="",
                risk="low",
                reveals=[
                    {
                        "id": "fact_thomas_extra_patrol",
                        "type": "observation",
                        "label": patrol_label,
                        "source": "npc_order",
                        "source_label": "托马斯",
                        "description": patrol_desc,
                    }
                ],
                scene_requirements={
                    "required_visible_npcs": ["托马斯"],
                    "required_active_events": ["thomas_calling_extra_patrol"],
                    "required_location": str(loc),
                    "required_known_facts": [],
                    "required_visible_objects": [],
                },
                consumable=True,
                source_fact="scene:thomas_calling_extra_patrol",
                reason="托马斯正在当场下达巡逻命令",
            ),
        )

    if loc == "酒馆" and (night or cha_mod >= 1):
        _add(
            buckets,
            DynamicAction(
                id="pretend_drunk",
                label="假装喝醉，接近谈话的人群",
                input="我假装喝醉接近守卫",
                category="stealth",
                description="酒馆的喧嚣是天然的掩护",
                tags=["cha", "roleplay"],
            ),
        )

    if loc != "森林小路" and night and not play_context.get("bandit_raid"):
        dest = "仓库" if loc != "仓库" else "酒馆"
        if dest in location_connections_for_state(state).get(loc, []):
            _add(
                buckets,
                DynamicAction(
                    id=f"sneak_{dest}",
                    label=f"借夜色掩护，悄悄摸向{dest}",
                    input=f"悄悄前往{dest}",
                    category="stealth",
                    description="避开耳目，不惊动任何人",
                    unlocked=dex_mod >= 1,
                    lock_reason="敏捷不足，难以无声移动" if dex_mod < 1 else None,
                    tags=["dex", "unlock"],
                ),
            )

    # --- 生存 / 移动 ---
    for dest in location_connections_for_state(state).get(loc, []):
        if dest == loc:
            continue
        danger_note = ""
        _add(
            buckets,
            DynamicAction(
                id=f"move_{loc}_{dest}",
                label=_move_label(state, dest),
                input=f"前往{dest}",
                category="survival",
                description=f"从{loc}出发{dest}{danger_note}",
                tags=["move"],
                source_fact=scene_source,
                reason=f"可从{loc}前往{dest}",
            ),
        )

    rest_label = "在原地休整，恢复体力"
    rest_desc = "时间仍会流逝，世界不会停下"
    if night:
        rest_label = "找避风处过夜，等待黎明"
        rest_desc = "漫长的一夜可能发生许多事"
    _add(
        buckets,
        DynamicAction(
            id="rest",
            label=rest_label,
            input="在原地休整片刻" if not night else "在此过夜休息",
            category="survival",
            description=rest_desc,
            tags=["rest"],
        ),
    )

    if player.class_name in ("骑士", "游侠") and loc == "村口":
        _add(
            buckets,
            DynamicAction(
                id="scout_perimeter",
                label="沿村界巡逻一圈，标记异常",
                input="沿村庄四周观察环境与脚印",
                category="survival",
                description=f"{player.class_name}的素养适合系统性侦察",
                tags=["class"],
            ),
        )

    if storm and loc != "酒馆":
        _add(
            buckets,
            DynamicAction(
                id="seek_shelter",
                label="寻找可避雨的遮蔽处等待天气好转",
                input="寻找遮蔽处等待天气好转",
                category="survival",
                description="恶劣天气下贸然行动风险更高",
            ),
        )

    # --- 自由行动 ---
    _add(
        buckets,
        DynamicAction(
            id="free_input",
            label="自由描述你想做的事…",
            input="",
            category="free",
            description="例如：「我假装喝醉接近守卫」「用军徽换取托马斯的信任」",
            tags=["custom"],
        ),
    )

    return _finalize_buckets(buckets, player_knowledge, consumed, state)


def _finalize_buckets(
    buckets: dict[str, list[DynamicAction]],
    player_knowledge: dict[str, Any],
    consumed: set[str],
    state: GameState | None,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    flat: list[str] = []
    demo_mode = bool(state and is_demo_story_mode(state))
    per_cat_cap = 8 if demo_mode else 5
    for cat in CATEGORIES:
        actions = buckets.get(cat, [])
        unlocked_first = sorted(
            actions,
            key=lambda a: (
                not a.unlocked,
                "demo_knowledge" not in (a.tags or []),
                a.label,
            ),
        )
        trimmed = unlocked_first[:per_cat_cap] if cat != "free" else unlocked_first[:1]
        dumped: list[dict[str, Any]] = []
        for a in trimmed:
            d = a.model_dump()
            intent = d.get("intent") if isinstance(d.get("intent"), dict) else {}
            intent = dict(intent)
            intent.setdefault("action_id", a.id)
            d["intent"] = intent
            if cat != "free" and a.category != "free" and not d.get("source_fact"):
                d["source_fact"] = (a.uses_known_fact[0] if a.uses_known_fact else f"scene:{state.location if state else 'unknown'}")
            dumped.append(d)
        grouped[cat] = dumped
        for a in trimmed:
            if a.unlocked and a.input and a.category != "free":
                flat.append(a.input)

    payload = {
        "grouped": grouped,
        "category_labels": CATEGORY_LABELS,
        "flat_inputs": flat[:8],
    }
    demo_mode = bool(state and is_demo_story_mode(state))
    payload = validate_choices_payload(
        payload,
        player_knowledge,
        consumed_actions=[] if demo_mode else list(consumed),
    )
    if state:
        payload = filter_actions_payload(payload, state)
    return payload


def generate_actions(state: GameState) -> dict[str, Any]:
    """根据 player_knowledge + scene_graph 生成分组行动（统一入口）。"""
    pk = get_player_knowledge(state)
    legacy = ensure_player_known_facts(state)
    scene = state.flags.get("last_scene_graph")
    if not isinstance(scene, dict):
        scene = {}
    scene = dict(scene)
    scene["player_visible"] = build_player_visible(
        scene,
        pk,
        location=state.location,
        known_locations=list(legacy.get("known_locations") or []),
        known_npcs=list(legacy.get("known_npcs") or []),
    )
    payload = generate_from_knowledge(
        pk,
        scene,
        _minimal_play_context(state),
        state=state,
    )
    if is_demo_story_mode(state):
        payload = filter_demo_actions_payload(payload, state)
    return payload


def generate_options(state: GameState) -> list[str]:
    """兼容旧接口：返回可执行 input 字符串列表。"""
    data = generate_actions(state)
    return data["flat_inputs"] or ["仔细观察周围环境"]

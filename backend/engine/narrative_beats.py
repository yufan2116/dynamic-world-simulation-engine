"""叙事节拍 — 结构化事件事实（非文学段落），供 CRPG Scene Renderer 使用。"""
from __future__ import annotations

from typing import Any

from engine.rule_engine import RollOutcome
from engine.world_state import GameState


def _outcome_key(dice: dict[str, Any] | None, succeeded: bool) -> str:
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


def _merge_beat(**parts: str | None) -> dict[str, Any]:
    beat: dict[str, Any] = {
        "direct_result": parts.get("direct_result") or "",
        "npc_reaction": parts.get("npc_reaction") or "",
        "new_information": parts.get("new_information"),
        "consequence": parts.get("consequence"),
        "scene_note": parts.get("scene_note"),
    }
    return beat


def _beat_talk_thomas(outcome: str, succeeded: bool) -> dict[str, Any]:
    if outcome == "critical_success":
        return _merge_beat(
            direct_result="你听清守卫私下交谈的关键句",
            npc_reaction="托马斯脸色发白，压低声音：「队长也知道那批货……」随即闭嘴",
            new_information="守卫内部有人牵涉仓库货物",
            consequence="托马斯态度转为谨慎合作",
        )
    if not succeeded:
        return _merge_beat(
            direct_result="你靠近偷听时踩响地板",
            npc_reaction="托马斯手按剑柄：「谁在那里？！」",
            consequence="托马斯对你的警惕上升",
        )
    if succeeded:
        return _merge_beat(
            direct_result="你在雨声掩护下听完对话",
            npc_reaction="托马斯低声：「昨晚那批货又进旧仓库了，别多问。」",
            new_information="旧仓库与昨夜货物有关",
            consequence="获得可追查的仓库线索",
        )
    return _beat_generic_failure("talk")


def _beat_talk_mira(succeeded: bool) -> dict[str, Any]:
    if succeeded:
        return _merge_beat(
            direct_result="米拉放下手中的杯子，凑近你",
            npc_reaction="米拉：「马库斯最后一趟往仓库去了，雨太大，没人见他回来。」",
            new_information="马库斯最后出现在仓库方向",
        )
    return _merge_beat(
        direct_result="米拉摇头，不愿多说",
        npc_reaction="米拉：「我现在没心情聊这个。」",
        consequence="对话未取得新信息",
    )


def _beat_talk_elena(succeeded: bool) -> dict[str, Any]:
    if succeeded:
        return _merge_beat(
            direct_result="艾琳娜抓住你的袖口",
            npc_reaction="艾琳娜：「求求你，我父亲答应今晚回来……」",
            new_information="艾琳娜坚信父亲未抛弃她",
            consequence="村民声望上升",
        )
    return _merge_beat(
        direct_result="艾琳娜别过脸去",
        npc_reaction="艾琳娜哽咽着说不出完整句子",
        consequence="广场气氛更紧张",
    )


def _beat_talk_varick(succeeded: bool) -> dict[str, Any]:
    if succeeded:
        return _merge_beat(
            direct_result="瓦里克打量你片刻",
            npc_reaction="瓦里克：「想活命就少管商队的事。」",
            new_information="强盗方知晓你在调查",
        )
    return _merge_beat(
        direct_result="瓦里克冷笑",
        npc_reaction="瓦里克：「滚。趁我还没改主意。」",
        consequence="强盗声望下降",
    )


def _beat_investigate(outcome: str, succeeded: bool, state: GameState, changes: dict[str, Any]) -> dict[str, Any]:
    if state.location == "森林小路":
        if succeeded:
            return _merge_beat(
                direct_result="你在雾中辨明足迹与折断的树枝",
                new_information="瓦里克一伙在森林小路活动",
                consequence="瓦里克现身可对话",
            )
        return _merge_beat(
            direct_result="浓雾遮住视线，你在林间打转",
            npc_reaction="远处传来一声短促冷笑",
            consequence="未找到有效路径",
        )
    if outcome == "critical_success":
        return _merge_beat(
            direct_result="你找到几乎被抹去的靴印与半枚撕裂徽章",
            new_information="现场有第三人经过的痕迹",
        )
    if not succeeded:
        return _merge_beat(
            direct_result="你只翻出一堆破麻袋和散落的谷物",
            npc_reaction="仓库外传来脚步声——有人正在靠近",
            consequence="仓库方向传出异常声响",
        )
    if changes.get("clue"):
        return _merge_beat(
            direct_result="你在货箱旁发现未干的痕迹",
            new_information=str(changes["clue"]),
            consequence="脚印指向森林方向",
        )
    return _beat_generic_failure("investigate")


def _beat_move(state: GameState, changes: dict[str, Any]) -> dict[str, Any]:
    dest = changes.get("moved_to", state.location)
    return _merge_beat(
        scene_note=f"{state.weather}，你抵达{dest}",
        direct_result=f"位置变更：{dest}",
        new_information=f"当前时间 {state.flags.get('clock', state.time_of_day)}",
    )


def _beat_combat(succeeded: bool, changes: dict[str, Any]) -> dict[str, Any]:
    if succeeded:
        return _merge_beat(
            direct_result="剑锋交击后瓦里克带人退入密林",
            npc_reaction="瓦里克退走时咒骂不断",
            new_information="森林小路暂时恢复通行",
            consequence=changes.get("quest_update") or "瓦里克被击退",
        )
    return _merge_beat(
        direct_result="你负伤后撤",
        npc_reaction="身后传来强盗的笑声",
        consequence="村庄守卫声望下降，恐慌上升",
    )


def _beat_generic_failure(action: str) -> dict[str, Any]:
    labels = {
        "persuade": "对方没有接受你的说法",
        "intimidate": "威胁未能奏效",
        "combat": "对方占了上风",
        "talk": "对话未能取得进展",
        "investigate": "调查没有新发现",
        "unknown": "你的意图不清晰，时间被浪费",
    }
    return _merge_beat(
        direct_result=labels.get(action, "行动未达预期"),
        consequence="局势没有向你有利的方向变化",
    )


def _beat_generic_success(changes: dict[str, Any]) -> dict[str, Any]:
    if changes.get("clue"):
        return _merge_beat(
            direct_result="你确认了新的线索",
            new_information=str(changes["clue"]),
        )
    return _merge_beat(
        direct_result="行动完成",
        new_information="情况有轻微进展",
    )


def _beat_from_world_blocks(
    action: str,
    target: str | None,
    succeeded: bool,
    changes: dict[str, Any],
) -> dict[str, Any] | None:
    """将 world_simulator 的特殊情况转为结构化节拍（忽略 HTML scene 字段）。"""
    if not succeeded and target and changes.get("check_succeeded") is False:
        if "并不在此处" in str(changes.get("failure_scene", "")):
            return _merge_beat(
                direct_result=f"{target}不在当前地点",
                consequence="需要前往其他地点寻找",
            )
        if "瓦里克" in str(changes.get("failure_scene", "")):
            return _merge_beat(
                direct_result="森林深处只有风声",
                new_information="需要更多线索才能找到瓦里克",
            )
        if "瓦里克冷笑" in str(changes.get("failure_scene", "")):
            return _beat_talk_varick(False)
    if action == "rest":
        return _merge_beat(
            direct_result="你短暂歇息，体力稍有恢复",
            consequence="时间推进，世界仍在运转",
        )
    if action == "unknown":
        if not succeeded:
            return _merge_beat(
                direct_result="你无法把意图落实为具体行动",
                consequence="时间流逝，雾气更浓",
            )
        return _merge_beat(
            direct_result="你观察四周，判断应继续调查失踪案",
        )
    return None


def build_event_beats(
    state: GameState,
    intent: dict[str, Any],
    dice: dict[str, Any] | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """结构化事件节拍，不含文学修辞。"""
    from engine.world_ontology import is_xianxia

    if is_xianxia(state):
        from engine.narrative_beats_xianxia import build_event_beats_xianxia

        return build_event_beats_xianxia(state, intent, dice, changes)

    if intent.get("action_type") == "start":
        return _merge_beat()

    action = intent.get("action_type", "unknown")
    target = intent.get("target")
    succeeded = bool(changes.get("check_succeeded", True))
    outcome = _outcome_key(dice, succeeded)

    preset = _beat_from_world_blocks(action, target, succeeded, changes)
    if preset:
        beat = preset
    elif action == "move" and changes.get("moved_to"):
        beat = _beat_move(state, changes)
    elif action == "talk" and target == "托马斯":
        beat = _beat_talk_thomas(outcome, succeeded)
    elif action == "talk" and target == "米拉":
        beat = _beat_talk_mira(succeeded)
    elif action == "talk" and target == "艾琳娜":
        beat = _beat_talk_elena(succeeded)
    elif action == "talk" and target == "瓦里克":
        beat = _beat_talk_varick(succeeded)
    elif action == "investigate":
        beat = _beat_investigate(outcome, succeeded, state, changes)
    elif action == "combat":
        beat = _beat_combat(succeeded, changes)
    elif not succeeded:
        beat = _beat_generic_failure(action)
    else:
        beat = _beat_generic_success(changes)

    extras: list[str] = []
    for upd in changes.get("npc_updates", []):
        name = upd.get("npc", "")
        if upd.get("attitude_to"):
            extras.append(f"{name}对你的态度变为「{upd['attitude_to']}」")
    if changes.get("quest_update"):
        extras.append(str(changes["quest_update"]))
    if extras:
        prev = beat.get("consequence") or ""
        beat["consequence"] = "；".join(filter(None, [prev, *extras]))

    tick = changes.get("world_tick_events") or []
    if tick:
        beat["world_events"] = [e.get("text", "") for e in tick if e.get("text")]

    beat["outcome"] = outcome
    return beat


def beats_to_html(beat: dict[str, Any]) -> str:
    """将结构化节拍渲染为分层 HTML（回退用）。"""
    parts: list[str] = []
    if beat.get("scene_note"):
        parts.append(f'<p class="scene">{beat["scene_note"]}</p>')
    if beat.get("direct_result"):
        parts.append(f'<p class="result">{beat["direct_result"]}</p>')
    if beat.get("npc_reaction"):
        text = beat["npc_reaction"]
        if "：" in text or ":" in text:
            parts.append(f'<p class="dialogue">{text}</p>')
        else:
            parts.append(f'<p class="result">{text}</p>')
    if beat.get("new_information"):
        parts.append(
            f'<p class="consequence"><em>信息：{beat["new_information"]}</em></p>'
        )
    if beat.get("consequence"):
        parts.append(f'<p class="consequence"><em>{beat["consequence"]}</em></p>')
    for line in beat.get("world_events") or []:
        parts.append(f'<p class="world">{line}</p>')
    if not parts:
        parts.append('<p class="scene">四周一片安静，你暂时按兵不动。</p>')
    return "\n".join(parts)


def build_narrative(
    state: GameState,
    intent: dict[str, Any],
    dice: dict[str, Any] | None,
    changes: dict[str, Any],
) -> str:
    """兼容入口：返回分层 HTML（无 LLM 时使用）。"""
    return beats_to_html(build_event_beats(state, intent, dice, changes))

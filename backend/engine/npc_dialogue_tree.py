"""NPC 对话行为树 — 按世界状态选择对话模式，稳定 CRPG 对白风格。"""
from __future__ import annotations

from typing import Any

from engine.world_state import GameState, NPCState

# 行为节点 → 给 Scene Renderer 的执行说明（中文，短句）
BEHAVIOR_HINTS: dict[str, str] = {
    "avoid_eye_contact": "避免直视玩家，视线游移或看向别处",
    "short_answers": "只用一两句短答，不展开背景",
    "change_topic": "岔开话题，引向公务/天气/别处",
    "official_tone": "公事公办，用职务口吻",
    "lower_voice": "压低声音，靠近说话",
    "share_rumor": "只透露已发生的传闻级信息，不编造细节",
    "guard_jargon": "用守卫/巡逻用语，少感情词",
    "direct_answer": "直接回答问题，不绕弯",
    "warm_tone": "语气带关切，仍保持克制",
    "practical_advice": "给可执行建议（去哪、找谁）",
    "pleading": "带恳求，重复关键请求",
    "tearful_pause": "哽咽、停顿，句子不完整",
    "cling_to_hope": "坚持父亲会回来，拒绝最坏猜测",
    "threaten": "带威胁，短句命令式",
    "mock_player": "嘲弄、反问",
    "negotiation_stance": "讨价还价，不一次说透",
    "dismiss_player": "想打发玩家离开",
    "sect_elder_tone": "长老训诫式，简练威严",
    "cite_rules": "引用门规/封印条例",
    "withhold_details": "刻意不说全，要玩家再去查",
    "nervous_stammer": "紧张、说话打结",
    "report_to_elder": "建议去找长老或汇报",
    "ominous_hint": "阴冷暗示，不直说目的",
    "taunt": "讥讽玩家实力或来历",
    "demand_proof": "要求玩家证明身份或立场",
    "neutral_polite": "礼貌但疏远，有问有答",
    "busy_dismissal": "表示正忙，请稍后再问",
}


# 每个 NPC 的对话树：分支名 → 行为节点列表（按优先级从上到下匹配）
NPC_CONVERSATION_TREES: dict[str, dict[str, list[str]]] = {
    "托马斯": {
        "if_alerted": [
            "avoid_eye_contact",
            "short_answers",
            "official_tone",
            "change_topic",
            "demand_proof",
        ],
        "if_suspicious": [
            "avoid_eye_contact",
            "short_answers",
            "change_topic",
            "guard_jargon",
        ],
        "if_cooperative": [
            "lower_voice",
            "share_rumor",
            "guard_jargon",
            "direct_answer",
        ],
        "if_neutral": [
            "official_tone",
            "short_answers",
            "neutral_polite",
        ],
    },
    "米拉": {
        "if_anxious": [
            "warm_tone",
            "share_rumor",
            "practical_advice",
            "change_topic",
        ],
        "if_cooperative": [
            "lower_voice",
            "warm_tone",
            "practical_advice",
            "direct_answer",
        ],
        "if_busy": [
            "busy_dismissal",
            "short_answers",
            "warm_tone",
        ],
        "if_neutral": [
            "warm_tone",
            "neutral_polite",
            "practical_advice",
        ],
    },
    "艾琳娜": {
        "if_desperate": [
            "pleading",
            "tearful_pause",
            "cling_to_hope",
            "short_answers",
        ],
        "if_cooperative": [
            "pleading",
            "direct_answer",
            "cling_to_hope",
        ],
        "if_distrustful": [
            "avoid_eye_contact",
            "short_answers",
            "tearful_pause",
        ],
        "if_neutral": [
            "pleading",
            "neutral_polite",
        ],
    },
    "瓦里克": {
        "if_hostile": [
            "threaten",
            "mock_player",
            "short_answers",
            "dismiss_player",
        ],
        "if_negotiating": [
            "negotiation_stance",
            "withhold_details",
            "taunt",
        ],
        "if_neutral": [
            "mock_player",
            "short_answers",
            "ominous_hint",
        ],
    },
    "云长老": {
        "if_strict": [
            "sect_elder_tone",
            "cite_rules",
            "withhold_details",
            "short_answers",
        ],
        "if_cooperative": [
            "sect_elder_tone",
            "direct_answer",
            "cite_rules",
        ],
        "if_neutral": [
            "sect_elder_tone",
            "neutral_polite",
            "withhold_details",
        ],
    },
    "林师妹": {
        "if_panicked": [
            "nervous_stammer",
            "report_to_elder",
            "short_answers",
            "pleading",
        ],
        "if_cooperative": [
            "nervous_stammer",
            "direct_answer",
            "report_to_elder",
        ],
        "if_neutral": [
            "neutral_polite",
            "nervous_stammer",
        ],
    },
    "血煞道人": {
        "if_hostile": [
            "threaten",
            "ominous_hint",
            "taunt",
            "dismiss_player",
        ],
        "if_negotiating": [
            "ominous_hint",
            "withhold_details",
            "mock_player",
        ],
        "if_neutral": [
            "ominous_hint",
            "short_answers",
            "taunt",
        ],
    },
}

# 分支匹配优先级（先匹配者生效）
_BRANCH_PRIORITY: dict[str, list[str]] = {
    "托马斯": ["if_alerted", "if_suspicious", "if_cooperative", "if_neutral"],
    "米拉": ["if_anxious", "if_cooperative", "if_busy", "if_neutral"],
    "艾琳娜": ["if_desperate", "if_cooperative", "if_distrustful", "if_neutral"],
    "瓦里克": ["if_hostile", "if_negotiating", "if_neutral"],
    "云长老": ["if_strict", "if_cooperative", "if_neutral"],
    "林师妹": ["if_panicked", "if_cooperative", "if_neutral"],
    "血煞道人": ["if_hostile", "if_negotiating", "if_neutral"],
}


def _attitude_bucket(npc: NPCState) -> str:
    val = npc.attitude_value
    label = npc.attitude
    if val <= -40 or label in ("敌对", "冷淡"):
        return "negative"
    if val >= 40 or label in ("友好", "亲密"):
        return "positive"
    return "neutral"


def _branch_conditions(
    state: GameState,
    npc: NPCState,
    intent: dict[str, Any],
    changes: dict[str, Any],
) -> dict[str, bool]:
    """计算某 NPC 各对话分支是否成立。"""
    name = npc.name
    bucket = _attitude_bucket(npc)
    panic = int(state.flags.get("village_panic", 35))
    is_target = intent.get("target") == name
    action = intent.get("action_type", "")
    social = action in ("talk", "persuade", "intimidate")
    succeeded = changes.get("check_succeeded", True)

    cond: dict[str, bool] = {}

    if name == "托马斯":
        cond["if_alerted"] = bool(state.flags.get("thomas_alerted"))
        cond["if_suspicious"] = (
            bucket == "negative"
            or (is_target and social and not succeeded)
            or bool(state.flags.get("warehouse_noise") and bucket != "positive")
        )
        cond["if_cooperative"] = bucket == "positive" or bool(state.flags.get("guard_info"))
        cond["if_neutral"] = not any(
            cond.get(k) for k in ("if_alerted", "if_suspicious", "if_cooperative")
        )

    elif name == "米拉":
        cond["if_anxious"] = panic > 50 or state.flags.get("clue_found")
        cond["if_cooperative"] = bucket == "positive"
        cond["if_busy"] = state.time_of_day in ("正午", "傍晚") and not cond.get("if_cooperative")
        cond["if_neutral"] = not any(
            cond.get(k) for k in ("if_anxious", "if_cooperative", "if_busy")
        )

    elif name == "艾琳娜":
        cond["if_desperate"] = panic > 55 or (is_target and social and not succeeded)
        cond["if_cooperative"] = bucket == "positive"
        cond["if_distrustful"] = bucket == "negative"
        cond["if_neutral"] = not any(
            cond.get(k) for k in ("if_desperate", "if_cooperative", "if_distrustful")
        )

    elif name == "瓦里克":
        cond["if_hostile"] = bucket == "negative" or action == "combat"
        cond["if_negotiating"] = (
            action in ("talk", "persuade") and is_target and bucket != "negative"
        )
        cond["if_neutral"] = not cond.get("if_hostile") and not cond.get("if_negotiating")

    elif name == "云长老":
        crisis = state.flags.get("crisis") or {}
        pressure = float(crisis.get("pressure", 12)) if isinstance(crisis, dict) else 12.0
        cond["if_strict"] = pressure > 30 or bucket == "negative"
        cond["if_cooperative"] = bucket == "positive"
        cond["if_neutral"] = not cond.get("if_strict") and not cond.get("if_cooperative")

    elif name == "林师妹":
        crisis = state.flags.get("crisis") or {}
        pressure = float(crisis.get("pressure", 12)) if isinstance(crisis, dict) else 12.0
        cond["if_panicked"] = pressure > 35
        cond["if_cooperative"] = bucket == "positive"
        cond["if_neutral"] = not cond.get("if_panicked") and not cond.get("if_cooperative")

    elif name == "血煞道人":
        cond["if_hostile"] = bucket == "negative" or action in ("combat", "intimidate")
        cond["if_negotiating"] = action in ("talk", "persuade") and is_target
        cond["if_neutral"] = not cond.get("if_hostile") and not cond.get("if_negotiating")

    return cond


def resolve_npc_dialogue_behavior(
    state: GameState,
    npc: NPCState,
    intent: dict[str, Any],
    changes: dict[str, Any],
) -> dict[str, Any]:
    """
    解析当前 NPC 激活的对话分支与行为节点。

    返回示例：
    {
      "active_branch": "if_suspicious",
      "behaviors": ["avoid_eye_contact", "short_answers", "change_topic"],
      "behavior_hints": ["避免直视……", "只用一两句短答……"],
      "is_dialogue_target": true
    }
    """
    name = npc.name
    tree = NPC_CONVERSATION_TREES.get(name, {})
    priority = _BRANCH_PRIORITY.get(name, list(tree.keys()))
    conditions = _branch_conditions(state, npc, intent, changes)

    active_branch = "if_neutral"
    for branch in priority:
        if conditions.get(branch) and branch in tree:
            active_branch = branch
            break

    behaviors = list(tree.get(active_branch, tree.get("if_neutral", ["neutral_polite", "short_answers"])))
    hints = [BEHAVIOR_HINTS.get(b, b) for b in behaviors]

    return {
        "active_branch": active_branch,
        "behaviors": behaviors,
        "behavior_hints": hints,
        "is_dialogue_target": intent.get("target") == name,
    }


def resolve_scene_dialogue_behaviors(
    state: GameState,
    intent: dict[str, Any],
    changes: dict[str, Any],
) -> dict[str, Any]:
    """当前地点所有可见 NPC 的对话行为 + 本回合对话焦点。"""
    by_npc: dict[str, Any] = {}
    for npc in state.npc_at_location():
        by_npc[npc.name] = resolve_npc_dialogue_behavior(state, npc, intent, changes)

    target = intent.get("target")
    focus = by_npc.get(target) if target else None

    return {
        "by_npc": by_npc,
        "dialogue_target": target,
        "dialogue_target_behavior": focus,
    }

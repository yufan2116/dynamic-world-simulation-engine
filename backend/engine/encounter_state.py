"""遭遇状态 — tension / NPC intent / hidden info / danger / social 合成 encounter，驱动叙事。"""
from __future__ import annotations

from typing import Any

from engine.crisis_escalation import _ensure_crisis, compute_crisis_pressure
from engine.npc_ai import NPC_PROFILES, _ensure_profiles
from engine.npc_dialogue_tree import resolve_scene_dialogue_behaviors
from engine.world_template_manager import resolve_template_id
from engine.world_state import GameState, NPCState

# encounter_type → 叙事基调（给 Scene Renderer）
ENCOUNTER_TONE: dict[str, str] = {
    "suspicious_guard": "守卫戒备、盘问、遮遮掩掩",
    "guard_confession": "守卫压低声音透露内幕",
    "desperate_plea": "女儿恳求、情绪濒临失控",
    "inn_gossip": "酒馆私下交谈、交换消息",
    "bandit_negotiation": "强盗对峙、讨价还价",
    "warehouse_probe": "仓库搜查、动静与线索",
    "forest_trail": "林间追踪、视野受限",
    "bandit_confrontation": "正面冲突、刀剑相向",
    "village_unrest": "村民恐慌、舆论压力",
    "sect_crisis": "宗门封印危机、等级森严",
    "ambient_scene": "日常场景、低冲突",
    "travel_transition": "路途移动、环境变化",
    "rest_break": "短暂休整、时间流逝",
}

# 对话分支 → NPC 本回合意图（对玩家）
_BRANCH_NPC_INTENT: dict[str, str] = {
    "if_alerted": "确认玩家身份并阻止其靠近敏感话题",
    "if_suspicious": "不泄露信息、尽快结束对话",
    "if_cooperative": "在可控范围内分享所知",
    "if_neutral": "保持礼节、不多谈私事",
    "if_anxious": "掩饰忧虑、用传闻转移注意",
    "if_busy": "尽快打发玩家",
    "if_desperate": "求得帮助、追问父亲下落",
    "if_distrustful": "回避、不愿深谈",
    "if_hostile": "驱逐或威胁玩家",
    "if_negotiating": "试探立场、保留筹码",
    "if_strict": "按门规处置、不纵容",
    "if_panicked": "急于汇报、语无伦次",
}

# 对话分支 → NPC 隐藏目标（不对玩家直说）
_BRANCH_NPC_GOAL: dict[str, str] = {
    "if_alerted": "不要泄露仓库与队长牵涉的实情",
    "if_suspicious": "不要泄露信息",
    "if_cooperative": "只透露部分真相以换取信任",
    "if_neutral": "完成公务、避免麻烦",
    "if_anxious": "保护酒馆与艾琳娜，不惹祸上身",
    "if_busy": "维持生意、少惹是非",
    "if_desperate": "让人相信父亲仍活着",
    "if_distrustful": "隐藏自己的恐惧",
    "if_hostile": "保住地盘与货物",
    "if_negotiating": "榨取利益或吓退玩家",
    "if_strict": "维持封印秩序、追究异动",
    "if_panicked": "避免独自承担失职",
}

_ABILITY_ADVANTAGE: dict[str, str] = {
    "STR": "力量占优",
    "DEX": "身手敏捷",
    "CON": "体格稳健",
    "INT": "思路清晰",
    "WIS": "高感知",
    "CHA": "口才见长",
}

_LOCATION_DANGER: dict[str, int] = {
    "村口": 25,
    "酒馆": 20,
    "仓库": 45,
    "森林小路": 70,
    "山门": 30,
    "藏经阁": 40,
    "禁地裂谷": 85,
}


def _compute_tension(state: GameState) -> int:
    panic = int(state.flags.get("village_panic", 35))
    crisis_p = compute_crisis_pressure(state)
    loc = _location_danger_score(state)
    alert_bonus = 22 if state.flags.get("thomas_alerted") else 0
    noise_bonus = 12 if state.flags.get("warehouse_noise") else 0
    raw = panic * 0.45 + crisis_p * 0.35 + loc * 0.2 + alert_bonus + noise_bonus
    return max(0, min(100, int(raw)))


def _risk_label(tension: int, state: GameState) -> str:
    danger = state.flags.get("danger_level", "中")
    bump = {"低": 0, "中": 8, "高": 18}.get(str(danger), 8)
    score = tension + bump
    if score < 38:
        return "low"
    if score < 68:
        return "medium"
    return "high"


def _location_danger_score(state: GameState) -> int:
    loc = state.location
    seed_locs = state.flags.get("seed_locations")
    if isinstance(seed_locs, list):
        for entry in seed_locs:
            if isinstance(entry, dict) and entry.get("name") == loc:
                danger = entry.get("danger", "中")
                pressure = entry.get("spiritual_pressure")
                if pressure is not None:
                    return min(100, int(pressure) * 12)
                return {"低": 20, "中": 45, "高": 70, "极高": 90}.get(str(danger), 40)
    return _LOCATION_DANGER.get(loc, 30)


def _resolve_hidden_truths(state: GameState) -> list[str]:
    """世界已确立、玩家未必知晓的真相（不得编造）。"""
    tid = resolve_template_id(state.flags.get("template_id"))
    truths: list[str] = []

    if tid == "xianxia_forbidden_land":
        truths.append("禁地封印出现裂痕，灵气紊乱")
        if state.flags.get("clue_found"):
            truths.append("藏经阁封印阵有被人动过的痕迹")
        return truths

    truths.append("商人马库斯失踪")
    if state.flags.get("clue_found") or state.flags.get("warehouse_searched"):
        truths.append("仓库与失踪案有关")
    if state.flags.get("guard_info"):
        truths.append("守卫知晓昨夜仓库有可疑人影")
    if state.flags.get("thomas_alerted"):
        truths.append("托马斯已察觉有人在刺探守卫谈话")
    if state.flags.get("varick_revealed"):
        truths.append("瓦里克与强盗控制森林商路")
    if state.flags.get("warehouse_noise"):
        truths.append("仓库曾发生异常声响")
    crisis = _ensure_crisis(state)
    hint = crisis.get("merchant_location_hint")
    if hint:
        truths.append(f"马库斯可能位置：{hint}")
    return truths


def _player_advantage(
    state: GameState,
    intent: dict[str, Any],
    dice: dict[str, Any] | None,
    changes: dict[str, Any],
) -> str:
    parts: list[str] = []
    ability = (intent.get("ability") or (dice or {}).get("ability") or "WIS").upper()
    parts.append(_ABILITY_ADVANTAGE.get(ability, "观察力"))

    if dice:
        outcome = dice.get("outcome", "")
        if outcome in ("大成功", "critical_success"):
            parts.append("形势有利")
        elif outcome in ("大失败", "critical_failure"):
            parts.append("处于劣势")
        elif not changes.get("check_succeeded", True):
            parts.append("行动受挫")

    p = state.player
    mod = p.get_modifier(ability)
    if mod >= 3:
        parts.append(f"属性突出（{ability}+{mod}）")
    return "；".join(dict.fromkeys(parts))


def _social_dynamics(state: GameState, intent: dict[str, Any]) -> str:
    panic = int(state.flags.get("village_panic", 35))
    present = [n.name for n in state.npc_at_location()]
    attitudes = [
        f"{n.name}({n.attitude})" for n in state.npc_at_location()
    ]
    parts: list[str] = []
    if panic >= 60:
        parts.append("村民恐慌，公开场合易激化情绪")
    elif panic >= 40:
        parts.append("人心浮动，私下议论增多")
    else:
        parts.append("表面尚稳，暗流未散")
    if len(present) >= 2:
        parts.append(f"在场：{'、'.join(present)}")
    if attitudes:
        parts.append(f"态度：{'，'.join(attitudes)}")
    rep_guard = state.faction_reputation.get("村庄守卫", 0)
    rep_village = state.faction_reputation.get("村民", 0)
    if rep_guard or rep_village:
        parts.append(f"声望（守卫{rep_guard}/村民{rep_village}）")
    action = intent.get("action_type", "")
    if action in ("talk", "persuade") and intent.get("target"):
        parts.append(f"社交焦点：{intent['target']}")
    return "；".join(parts)


def _infer_encounter_type(
    state: GameState,
    intent: dict[str, Any],
    target_behavior: dict[str, Any] | None,
) -> str:
    action = intent.get("action_type", "unknown")
    target = intent.get("target")
    loc = state.location
    tid = state.flags.get("template_id", "missing_merchant_medieval")
    branch = (target_behavior or {}).get("active_branch", "")

    if action == "rest":
        return "rest_break"
    if action == "move":
        return "travel_transition"
    if action == "combat":
        return "bandit_confrontation" if target == "瓦里克" else "bandit_confrontation"
    if action == "investigate":
        if loc == "仓库":
            return "warehouse_probe"
        if loc == "森林小路":
            return "forest_trail"
        return "warehouse_probe" if "仓库" in (intent.get("destination") or "") else "ambient_scene"

    if tid == "xianxia_forbidden_land":
        if action in ("talk", "persuade", "intimidate"):
            if target in ("玄尘道人", "青岚"):
                return "sect_crisis"
            if target in ("黑衣散修", "镇守残魂"):
                return "bandit_negotiation"
        tension = int(state.flags.get("tension", state.flags.get("village_panic", 0)))
        return "sect_crisis" if tension > 50 else "ambient_scene"

    if action in ("talk", "persuade", "intimidate"):
        if target == "托马斯":
            if branch in ("if_alerted", "if_suspicious"):
                return "suspicious_guard"
            if branch == "if_cooperative":
                return "guard_confession"
            return "suspicious_guard"
        if target == "艾琳娜":
            return "desperate_plea"
        if target == "米拉":
            return "inn_gossip"
        if target == "瓦里克":
            return "bandit_negotiation"

    if int(state.flags.get("village_panic", 35)) >= 65:
        return "village_unrest"
    return "ambient_scene"


def _target_npc_goal(
    state: GameState,
    target: str | None,
    branch: str,
) -> str:
    if not target or target not in state.npcs:
        return "维持现状"
    profiles = _ensure_profiles(state)
    profile = profiles.get(target, NPC_PROFILES.get(target, {}))
    return _BRANCH_NPC_GOAL.get(branch, profile.get("goal", "维持现状"))


def _target_npc_intent(branch: str, target: str | None) -> str:
    if branch in _BRANCH_NPC_INTENT:
        return _BRANCH_NPC_INTENT[branch]
    if target:
        return f"与{target}周旋、保留立场"
    return "观察局势"


def build_encounter_state(
    state: GameState,
    intent: dict[str, Any],
    changes: dict[str, Any],
    dice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    合成遭遇状态，供叙事层按「当前遭遇」渲染。

    组成：tension、npc_intent、hidden_info、danger、social_dynamics。
    """
    tension = _compute_tension(state)
    dialogue_ctx = resolve_scene_dialogue_behaviors(state, intent, changes)
    target = intent.get("target")
    target_npc: NPCState | None = state.npcs.get(target) if target else None
    target_behavior = dialogue_ctx.get("dialogue_target_behavior") or {}
    branch = target_behavior.get("active_branch", "if_neutral")

    hidden_truths = _resolve_hidden_truths(state)
    hidden_truth = hidden_truths[0] if len(hidden_truths) == 1 else "；".join(hidden_truths[:3])

    encounter_type = _infer_encounter_type(state, intent, target_behavior)
    # 遭遇类型对张力下限（保证叙事基调与场面一致）
    tension_floor = {
        "suspicious_guard": 58,
        "bandit_confrontation": 70,
        "desperate_plea": 50,
        "warehouse_probe": 48,
        "forest_trail": 55,
        "village_unrest": 62,
        "sect_crisis": 52,
    }
    tension = max(tension, tension_floor.get(encounter_type, 0))
    tension = min(100, tension)
    risk = _risk_label(tension, state)
    danger_level = state.flags.get("danger_level", "中")

    npc_intent = _target_npc_intent(branch, target)
    npc_goal = _target_npc_goal(state, target, branch)
    if target_npc:
        profiles = _ensure_profiles(state)
        prof = profiles.get(target, NPC_PROFILES.get(target, {}))
        npc_intent_detail = {
            "target": target,
            "intent": npc_intent,
            "goal": npc_goal,
            "profile_goal": prof.get("goal", ""),
            "emotion": target_behavior.get("active_branch", branch),
            "dialogue_branch": branch,
            "behaviors": target_behavior.get("behaviors", []),
        }
    else:
        npc_intent_detail = {
            "target": None,
            "intent": "无单一对话对象，场景自行演变",
            "goal": None,
        }

    return {
        "encounter_type": encounter_type,
        "encounter_tone": ENCOUNTER_TONE.get(encounter_type, "当前遭遇"),
        "tension": tension,
        "hidden_truth": hidden_truth,
        "hidden_info": hidden_truths,
        "npc_intent": npc_intent,
        "npc_goal": npc_goal,
        "player_advantage": _player_advantage(state, intent, dice, changes),
        "risk": risk,
        "danger": danger_level,
        "social_dynamics": _social_dynamics(state, intent),
        "location": state.location,
        "dialogue_target": target,
        "components": {
            "tension": {
                "score": tension,
                "village_panic": int(state.flags.get("village_panic", 35)),
                "crisis_pressure": round(compute_crisis_pressure(state), 1),
                "location_risk": _LOCATION_DANGER.get(state.location, 30),
            },
            "npc_intent": npc_intent_detail,
            "hidden_info": hidden_truths,
            "danger": {
                "level": danger_level,
                "location": state.location,
                "warehouse_noise": bool(state.flags.get("warehouse_noise")),
                "bandit_active": bool(state.flags.get("varick_revealed")),
            },
            "social_dynamics": _social_dynamics(state, intent),
        },
    }

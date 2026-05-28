"""仙侠模板叙事节拍 — 灵痕/阵纹/剑意语义，非商人仓库。"""
from __future__ import annotations

from typing import Any

from engine.narrative_beats import _merge_beat, _outcome_key
from engine.world_ontology import pick_clue
from engine.world_state import GameState


def build_event_beats_xianxia(
    state: GameState,
    intent: dict[str, Any],
    dice: dict[str, Any] | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    if intent.get("action_type") == "start":
        return _merge_beat()

    action = intent.get("action_type", "unknown")
    target = intent.get("target")
    succeeded = bool(changes.get("check_succeeded", True))
    outcome = _outcome_key(dice, succeeded)
    clue = pick_clue(state)
    loc = state.location

    if action == "move" and changes.get("moved_to"):
        return _merge_beat(
            direct_result=f"你抵达{changes['moved_to']}，灵压明显变化",
            scene_note=f"{loc}的灵息与山门不同",
        )

    if action == "talk" and target == "玄尘道人":
        if succeeded:
            return _merge_beat(
                direct_result="玄尘道人拂尘一顿，目光落在你身上",
                npc_reaction="玄尘道人：「结界裂痕又扩了一寸，勿轻入祭坛。」",
                new_information="封印祭坛方向异动最剧",
            )
        return _merge_beat(
            direct_result="玄尘道人摇头，不愿多言",
            npc_reaction="玄尘道人：「天机未稳，且去石林一看。」",
        )

    if action == "talk" and target == "青岚":
        if succeeded:
            return _merge_beat(
                direct_result="青岚按剑侧身，剑鞘轻颤",
                npc_reaction="青岚：「师弟最后消失在石林——那里有剑气残痕。」",
                new_information="断剑石林留有新灵痕",
            )
        return _merge_beat(
            npc_reaction="青岚：「勿挡我路。」",
            consequence="对话未取得新信息",
        )

    if action == "investigate":
        if succeeded:
            state.flags["clue_found"] = True
            return _merge_beat(
                direct_result=f"你在{loc}勘验地面与石壁",
                new_information=f"发现{clue}，灵息紊乱",
                consequence="残留灵痕已记录",
            )
        return _merge_beat(
            direct_result="灵雾干扰感知，难以辨明",
            consequence="本次调查未获新灵痕",
        )

    if action == "combat":
        return _merge_beat(
            direct_result="剑光交错，灵气四散",
            consequence="战况改变在场修士态度",
        )

    if succeeded:
        return _merge_beat(
            direct_result=f"你完成{action}，注意到{clue}",
            scene_note=f"{loc}的灵力波动尚未平复",
        )
    return _merge_beat(
        direct_result="行动受阻",
        consequence="局势未向有利方向变化",
    )

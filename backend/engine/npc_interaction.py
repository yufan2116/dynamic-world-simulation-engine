"""NPC 交互解析 — 结构化回答，禁止泛化 placeholder 文本。"""

from __future__ import annotations

from typing import Any

from engine.location_registry import is_location_public, resolve_direction_phrase
from engine.world_state import GameState


def resolve_npc_interaction(
    state: GameState,
    npc_name: str,
    topic: str,
    *,
    succeeded: bool,
    raw_input: str = "",
) -> dict[str, Any]:
    """
    返回：
    npc_answer, npc_reaction, revealed_fact, withheld_information, reason
    """
    topic_l = (topic or raw_input or "").lower()
    att = state.npcs.get(npc_name).attitude_value if npc_name in state.npcs else 0

    if npc_name == "托马斯":
        return _resolve_thomas(state, topic_l, succeeded=succeeded, attitude=att)
    if npc_name == "艾琳娜":
        return _resolve_elena(state, succeeded=succeeded)
    if npc_name == "米拉":
        return _resolve_mira(state, succeeded=succeeded)

    if succeeded:
        return {
            "npc_answer": f"{npc_name}简短回应了你的问题。",
            "npc_reaction": f"{npc_name}打量你一眼，没有再多说。",
            "revealed_fact": None,
            "withheld_information": None,
            "reason": None,
        }
    return {
        "npc_answer": f"{npc_name}摇了摇头，不愿继续这个话题。",
        "npc_reaction": "气氛有些尴尬。",
        "revealed_fact": None,
        "withheld_information": "对方不愿多说。",
        "reason": "relationship_too_low",
    }


def _resolve_thomas(
    state: GameState,
    topic_l: str,
    *,
    succeeded: bool,
    attitude: int,
) -> dict[str, Any]:
    asks_night = any(k in topic_l for k in ("昨夜", "异常", "动静", "巡逻", "失踪"))
    warehouse_public = is_location_public(state, "旧仓库")

    if not succeeded or attitude < -10:
        return {
            "npc_answer": "昨夜确实有些动静，但与你无关。",
            "npc_reaction": "托马斯把话题扯开，明显不愿继续。",
            "revealed_fact": None,
            "withheld_information": "托马斯没有说明昨夜异常的具体位置与细节。",
            "reason": "relationship_too_low" if attitude < -10 else "topic_sensitive",
        }

    if asks_night and not warehouse_public:
        outer = resolve_direction_phrase(state, "warehouse")
        return {
            "npc_answer": f"昨夜村口外侧确实有些动静，细节现在不能说。",
            "npc_reaction": "他压低声音，目光扫向木栅外，随即闭嘴。",
            "revealed_fact": {
                "id": "fact_thomas_acknowledged_night_activity",
                "type": "npc_info",
                "label": "托马斯承认昨夜村口外侧有动静",
                "source": "npc",
                "source_label": "托马斯",
                "description": "托马斯承认昨夜有异常，但拒绝说明具体位置。",
            },
            "withheld_information": "托马斯没有解释为何要加强村口外侧巡逻。",
            "reason": "topic_sensitive",
        }

    if asks_night and warehouse_public:
        return {
            "npc_answer": "昨夜旧仓库方向有人影晃动，我已加派哨岗。",
            "npc_reaction": "他语气沉重，显然对失踪案忧心忡忡。",
            "revealed_fact": {
                "id": "clue_guard_shadow_old_warehouse",
                "type": "clue",
                "label": "守卫提及昨夜可疑人影与旧仓库",
                "source": "npc",
                "source_label": "托马斯",
                "description": "托马斯确认昨夜旧仓库方向有可疑动静。",
            },
            "withheld_information": None,
            "reason": None,
        }

    return {
        "npc_answer": "先管好你自己的事，别在村口生事。",
        "npc_reaction": "托马斯转身去招呼守卫。",
        "revealed_fact": None,
        "withheld_information": None,
        "reason": "no_knowledge",
    }


def _resolve_elena(state: GameState, *, succeeded: bool) -> dict[str, Any]:
    if succeeded:
        return {
            "npc_answer": "求求你……我父亲答应今晚回来，他绝不会丢下我。",
            "npc_reaction": "艾琳娜眼眶发红，声音发颤。",
            "revealed_fact": {
                "id": "fact_elena_father_promise",
                "type": "npc_info",
                "label": "艾琳娜坚信父亲会回来",
                "source": "npc",
                "source_label": "艾琳娜",
                "description": "艾琳娜说父亲答应今晚回来。",
            },
            "withheld_information": None,
            "reason": None,
        }
    return {
        "npc_answer": "……我现在不想说话。",
        "npc_reaction": "她别过脸去，肩膀微微发抖。",
        "revealed_fact": None,
        "withheld_information": None,
        "reason": "relationship_too_low",
    }


def _resolve_mira(state: GameState, *, succeeded: bool) -> dict[str, Any]:
    if succeeded:
        loc_phrase = (
            "旧仓库附近"
            if is_location_public(state, "旧仓库")
            else "村外一侧"
        )
        return {
            "npc_answer": f"马库斯最后一趟往{loc_phrase}去了，雨太大，没人见他回来。",
            "npc_reaction": "米拉压低声音，神色惊忧。",
            "revealed_fact": {
                "id": "clue_marcus_last_seen_near_warehouse",
                "type": "clue",
                "label": f"马库斯最后出现在{loc_phrase}",
                "source": "npc",
                "source_label": "米拉",
                "description": f"米拉提到马库斯最后一趟去向与{loc_phrase}有关。",
            },
            "withheld_information": None,
            "reason": None,
        }
    return {
        "npc_answer": "我现在没心情聊这个。",
        "npc_reaction": "米拉别过脸去。",
        "revealed_fact": None,
        "withheld_information": None,
        "reason": "relationship_too_low",
    }

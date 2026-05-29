"""Legacy action_id → Universal Interaction V2 adapter."""

from __future__ import annotations

from typing import Any

from engine.npc_state import npc_id_from_name

ADAPTER_TABLE: dict[str, dict[str, Any]] = {
    "ask_thomas_last_night": {
        "interaction_type": "ask_about_topic",
        "target_npc_id": "thomas",
        "topic_id": "last_night_disturbance",
    },
    "ask_thomas_patrol_reason": {
        "interaction_type": "ask_about_topic",
        "target_npc_id": "thomas",
        "topic_id": "extra_patrol",
    },
    "ask_elena_father_details": {
        "interaction_type": "comfort",
        "target_npc_id": "elena",
        "topic_id": "missing_father",
        "secondary_type": "ask_about_topic",
    },
    "comfort_elena": {
        "interaction_type": "comfort",
        "target_npc_id": "elena",
        "topic_id": "missing_father",
    },
    "talk_elena_opening": {
        "interaction_type": "comfort",
        "target_npc_id": "elena",
        "topic_id": "missing_father",
    },
    "observe_mira_at_tavern": {
        "interaction_type": "observe",
        "target_npc_id": "mira",
        "observe_target_type": "npc",
    },
    "hear_thomas_order": {
        "interaction_type": "eavesdrop",
        "target_npc_id": "thomas",
        "topic_id": "extra_patrol",
        "special": "overhear_order",
    },
    "listen_thomas_order": {
        "interaction_type": "eavesdrop",
        "target_npc_id": "thomas",
        "topic_id": "extra_patrol",
        "special": "overhear_order",
    },
}


def adapt_action_id(
    action_id: str,
    intent: dict[str, Any],
) -> dict[str, Any] | None:
    """将旧 action_id 映射为 interaction_resolver 参数。"""
    if action_id in ADAPTER_TABLE:
        params = dict(ADAPTER_TABLE[action_id])
        params["action_id"] = action_id
        return params
    if action_id.startswith("talk_"):
        name = action_id.replace("talk_", "", 1)
        return {
            "interaction_type": "ask_about_topic",
            "target_npc_id": npc_id_from_name(name),
            "action_id": action_id,
        }
    if action_id.startswith("ask_"):
        return {
            "interaction_type": "ask_about_topic",
            "target_npc_id": _infer_npc_from_ask_id(action_id),
            "action_id": action_id,
        }
    if action_id.startswith("observe_"):
        if "mira" in action_id:
            return {
                "interaction_type": "observe",
                "target_npc_id": "mira",
                "observe_target_type": "npc",
                "action_id": action_id,
            }
        return {
            "interaction_type": "observe",
            "observe_target_type": "location",
            "action_id": action_id,
        }
    if action_id.startswith("follow_"):
        fid = str(intent.get("fact_id") or action_id.replace("follow_", "", 1))
        if "mira" in fid.lower():
            return {
                "interaction_type": "observe",
                "target_npc_id": "mira",
                "observe_target_type": "npc",
                "action_id": action_id,
            }
        return {
            "interaction_type": "follow",
            "fact_id": fid,
            "action_id": action_id,
        }
    if action_id.startswith("rumor_"):
        rid = action_id.replace("rumor_", "", 1)
        return {
            "interaction_type": "ask_about_topic",
            "rumor_id": rid,
            "action_id": action_id,
        }
    return None


def _infer_npc_from_ask_id(action_id: str) -> str:
    if "thomas" in action_id or "托马斯" in action_id:
        return "thomas"
    if "elena" in action_id or "艾琳娜" in action_id:
        return "elena"
    if "mira" in action_id:
        return "mira"
    return ""

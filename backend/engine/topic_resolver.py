"""Topic Resolution — 将玩家意图映射为结构化 topic。"""

from __future__ import annotations

import re
from typing import Any

TOPIC_REGISTRY: dict[str, dict[str, Any]] = {
    "last_night_disturbance": {
        "id": "last_night_disturbance",
        "label": "昨夜异常动静",
        "related_facts": ["fact_thomas_acknowledged_night_activity"],
        "sensitivity": 50,
        "known_by": ["thomas"],
        "public_surface": "昨夜村口外侧似乎有异常声响",
        "keywords": ("昨夜", "异常", "动静", "声响", "巡逻", "夜间"),
    },
    "missing_father": {
        "id": "missing_father",
        "label": "父亲失踪",
        "related_facts": ["pf_elena_help", "fact_elena_father_promise"],
        "sensitivity": 15,
        "known_by": ["elena", "mira"],
        "public_surface": "艾琳娜求助：父亲马库斯昨夜未归",
        "keywords": ("父亲", "失踪", "马库斯", "未归", "商人"),
    },
    "extra_patrol": {
        "id": "extra_patrol",
        "label": "加派巡逻",
        "related_facts": ["fact_thomas_extra_patrol"],
        "sensitivity": 40,
        "known_by": ["thomas"],
        "public_surface": "托马斯今夜要加强村口外侧巡逻",
        "keywords": ("巡逻", "哨岗", "加派", "加强"),
    },
    "warehouse_activity": {
        "id": "warehouse_activity",
        "label": "仓库方向异动",
        "sensitivity": 60,
        "known_by": ["thomas"],
        "public_surface": "仓库方向昨夜有人影",
        "keywords": ("仓库", "人影", "脚印", "货物"),
    },
    "cargo": {
        "id": "cargo",
        "label": "那批货",
        "related_facts": ["clue_elena_cargo", "fact_elena_cargo_detail"],
        "sensitivity": 35,
        "known_by": ["elena", "mira", "thomas"],
        "public_surface": "马库斯昨夜提到一批货物",
        "keywords": ("货", "货物", "布匹", "铁器", "入库"),
    },
    "last_seen": {
        "id": "last_seen",
        "label": "昨夜最后行踪",
        "related_facts": ["clue_elena_cargo", "clue_muddy_tracks"],
        "sensitivity": 25,
        "known_by": ["elena", "mira", "thomas"],
        "public_surface": "马库斯昨夜离开后的去向",
        "keywords": ("昨夜", "最后", "离开", "去向", "足迹"),
    },
}

ACTION_TOPIC_HINTS: dict[str, str] = {
    "ask_thomas_last_night": "last_night_disturbance",
    "ask_elena_father_details": "missing_father",
    "comfort_elena": "missing_father",
    "talk_elena_opening": "missing_father",
    "ask_thomas_patrol_reason": "warehouse_activity",
    "ask_elena_cargo_detail": "cargo",
}


def get_topic(topic_id: str) -> dict[str, Any] | None:
    t = TOPIC_REGISTRY.get(topic_id)
    return dict(t) if t else None


def resolve_topic(
    *,
    intent: dict[str, Any] | None = None,
    action_id: str | None = None,
    raw_text: str = "",
    topic_id: str | None = None,
) -> dict[str, Any] | None:
    if topic_id and topic_id in TOPIC_REGISTRY:
        return get_topic(topic_id)
    if action_id and action_id in ACTION_TOPIC_HINTS:
        return get_topic(ACTION_TOPIC_HINTS[action_id])
    intent = intent or {}
    if intent.get("topic_id"):
        return get_topic(str(intent["topic_id"]))
    blob = " ".join(
        str(x)
        for x in (
            intent.get("topic"),
            intent.get("raw_input"),
            raw_text,
            intent.get("target"),
        )
        if x
    ).lower()
    best_id: str | None = None
    best_score = 0
    for tid, spec in TOPIC_REGISTRY.items():
        score = sum(1 for kw in spec.get("keywords", ()) if kw in blob)
        if score > best_score:
            best_score = score
            best_id = tid
    if best_id and best_score > 0:
        return get_topic(best_id)
    return None


def player_knows_topic(player_knowledge: dict[str, Any], topic_id: str) -> bool:
    spec = TOPIC_REGISTRY.get(topic_id)
    if not spec:
        return False
    surface = str(spec.get("public_surface", ""))
    ids = set()
    for key in ("facts", "observations", "rumors", "questions"):
        for item in player_knowledge.get(key) or []:
            if isinstance(item, dict):
                if item.get("id"):
                    ids.add(str(item["id"]))
                txt = str(item.get("text") or "")
                if surface and surface[:12] in txt:
                    return True
    for rid in spec.get("related_facts") or []:
        if str(rid) in ids:
            return True
    return topic_id in (player_knowledge.get("known_topics") or [])


def register_player_topic(player_knowledge: dict[str, Any], topic_id: str) -> None:
    known = player_knowledge.setdefault("known_topics", [])
    if topic_id not in known:
        known.append(topic_id)

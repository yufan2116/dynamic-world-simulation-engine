"""Choice Validator — 返回前端前过滤非法/泛化选项。"""

from __future__ import annotations

import re
from typing import Any

from engine.player_knowledge import all_knowledge_ids, knowledge_item_by_id

GENERIC_LABEL_PATTERNS: tuple[str, ...] = (
    "你听到的传闻",
    "求证你听到的传闻",
    "沿着你刚确认的现象",
    "调查最近的异常动静",
    "向现场线索打听",
    "追查线索",
    "向.*求证你听到的传闻",
)

GENERIC_REGEX = tuple(re.compile(p) for p in GENERIC_LABEL_PATTERNS if ".*" in p)


def _label_is_generic(label: str) -> bool:
    t = label.strip()
    if not t:
        return True
    for p in GENERIC_LABEL_PATTERNS:
        if ".*" not in p and p in t:
            return True
    for rx in GENERIC_REGEX:
        if rx.search(t):
            return True
    if t.startswith("向") and "求证" in t and "传闻" in t:
        return True
    return False


def _rumor_label_without_rumor(label: str, player_knowledge: dict[str, Any]) -> bool:
    rumors = player_knowledge.get("rumors") or []
    if "传闻" not in label:
        return False
    if not rumors:
        return True
    if "你听到的传闻" in label or "求证" in label and "传闻" in label:
        # 有 rumor 时仍禁止泛化「求证传闻」措辞
        if "你听到的传闻" in label:
            return True
    return False


def validate_choice(
    choice: dict[str, Any],
    player_knowledge: dict[str, Any],
    *,
    consumed_actions: set[str] | None = None,
    seen_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """校验单条选项；不合格返回 None。"""
    if not isinstance(choice, dict):
        return None
    label = str(choice.get("label") or choice.get("text") or "").strip()
    cid = str(choice.get("id") or "").strip()
    source_fact = str(choice.get("source_fact") or "").strip()

    if not label or not cid:
        return None
    if not source_fact:
        return None
    if _label_is_generic(label):
        return None
    if _rumor_label_without_rumor(label, player_knowledge):
        return None

    valid_ids = all_knowledge_ids(player_knowledge)
    # scene 可见事件/地点：scene: 前缀视为合法锚点
    if source_fact.startswith("scene:"):
        if len(source_fact) <= len("scene:"):
            return None
    elif source_fact not in valid_ids:
        if knowledge_item_by_id(player_knowledge, source_fact) is None:
            return None

    if consumed_actions and cid in consumed_actions:
        return None
    if seen_ids is not None:
        if cid in seen_ids:
            return None
        seen_ids.add(cid)

    if not choice.get("unlocked", True):
        return None

    return choice


def validate_choices_payload(
    payload: dict[str, Any],
    player_knowledge: dict[str, Any],
    *,
    consumed_actions: list[str] | None = None,
) -> dict[str, Any]:
    """过滤 action_generator 的 grouped payload。"""
    out = dict(payload)
    consumed = set(consumed_actions or [])
    seen: set[str] = set()
    grouped = out.get("grouped") or {}
    if not isinstance(grouped, dict):
        return out

    new_grouped: dict[str, list[dict[str, Any]]] = {}
    flat: list[str] = []
    for cat, arr in grouped.items():
        if not isinstance(arr, list):
            continue
        kept: list[dict[str, Any]] = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            if str(cat) == "free" or item.get("id") == "free_input":
                kept.append(item)
                continue
            validated = validate_choice(item, player_knowledge, consumed_actions=consumed, seen_ids=seen)
            if validated:
                kept.append(validated)
                inp = validated.get("input") or ""
                if inp and validated.get("unlocked", True):
                    flat.append(str(inp))
        new_grouped[str(cat)] = kept

    out["grouped"] = new_grouped
    out["flat_inputs"] = flat[:8]
    return out

"""Player Knowledge — 玩家可见信息的唯一数据源。

所有 narrative choices、world panel、follow-up / rumor / clue 选项
必须只从 player_knowledge 生成。
"""

from __future__ import annotations

from typing import Any

from engine.world_state import GameState, ensure_player_known_facts

PLAYER_KNOWLEDGE_KEYS = (
    "facts",
    "rumors",
    "observations",
    "questions",
    "available_followups",
    "known_topics",
)


def _empty_knowledge() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[Any]] = {k: [] for k in PLAYER_KNOWLEDGE_KEYS}
    return out


def ensure_player_knowledge(state: GameState) -> dict[str, list[dict[str, Any]]]:
    """初始化 player_knowledge 并与 legacy player_known_facts 同步。"""
    ensure_player_known_facts(state)
    raw = state.flags.get("player_knowledge")
    if not isinstance(raw, dict):
        raw = _empty_knowledge()
    for k in PLAYER_KNOWLEDGE_KEYS:
        if not isinstance(raw.get(k), list):
            raw[k] = []
    sync_legacy_to_player_knowledge(state, raw)
    state.flags["player_knowledge"] = raw
    return raw


def get_player_knowledge(state: GameState) -> dict[str, list[dict[str, Any]]]:
    return ensure_player_knowledge(state)


def sync_legacy_to_player_knowledge(
    state: GameState,
    pk: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """将 player_known_facts 中已有条目迁入 player_knowledge（幂等）。"""
    pk = pk or ensure_player_knowledge(state)
    legacy = state.flags.get("player_known_facts") or {}
    if not isinstance(legacy, dict):
        return

    existing_ids = all_knowledge_ids(pk)

    for r in legacy.get("known_rumors") or []:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id", "")).strip()
        if not rid or rid in existing_ids:
            continue
        pk["rumors"].append(
            {
                "id": rid,
                "text": str(r.get("text", "")).strip(),
                "source": str(r.get("source_label") or r.get("source") or "未知来源"),
                "source_type": str(r.get("source_type", "npc")),
                "source_label": str(r.get("source_label", "")),
            }
        )
        existing_ids.add(rid)

    for f in legacy.get("player_facing_facts") or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id", "")).strip()
        if not fid or fid in existing_ids:
            continue
        text = str(f.get("text") or f.get("label") or "").strip()
        if not text:
            continue
        ftype = str(f.get("type") or "fact")
        entry = {
            "id": fid,
            "text": text,
            "source": str(f.get("source") or "narrative"),
            "type": ftype,
        }
        if ftype in ("observation", "clue", "environment"):
            pk["observations"].append(entry)
        else:
            pk["facts"].append(entry)
        existing_ids.add(fid)


def all_knowledge_ids(pk: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in PLAYER_KNOWLEDGE_KEYS:
        if key == "available_followups":
            continue
        for item in pk.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    for fu in pk.get("available_followups") or []:
        if isinstance(fu, dict) and fu.get("source_fact"):
            ids.add(str(fu["source_fact"]))
    for tid in pk.get("known_topics") or []:
        if tid:
            ids.add(str(tid))
    return ids


def knowledge_item_by_id(pk: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for key in ("facts", "rumors", "observations", "questions"):
        for item in pk.get(key) or []:
            if isinstance(item, dict) and str(item.get("id")) == item_id:
                return item
    return None


def apply_action_result(state: GameState, action_result: dict[str, Any]) -> None:
    """将 resolver 输出的 action_result 合并进 player_knowledge。"""
    if not isinstance(action_result, dict):
        return
    pk = ensure_player_knowledge(state)
    existing = all_knowledge_ids(pk)

    def _append_list(key: str, items: list[Any]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            iid = str(item.get("id", "")).strip()
            if not iid or iid in existing:
                continue
            pk[key].append(dict(item))
            existing.add(iid)

    _append_list("facts", action_result.get("new_facts") or [])
    _append_list("observations", action_result.get("new_observations") or [])
    _append_list("questions", action_result.get("new_questions") or [])
    _append_list("rumors", action_result.get("new_rumors") or [])

    fu_ids = {str(f.get("id")) for f in pk["available_followups"] if isinstance(f, dict)}
    for fu in action_result.get("available_followups") or []:
        if not isinstance(fu, dict):
            continue
        fid = str(fu.get("id", "")).strip()
        if not fid or fid in fu_ids:
            continue
        pk["available_followups"].append(dict(fu))
        fu_ids.add(fid)

    npc_changes = action_result.get("npc_state_changes")
    if isinstance(npc_changes, list) and npc_changes:
        from engine.npc_state import apply_npc_state_changes

        apply_npc_state_changes(state, npc_changes)

    for tid in action_result.get("known_topics") or []:
        if isinstance(tid, str) and tid.strip():
            known = pk.setdefault("known_topics", [])
            if tid not in known:
                known.append(tid)

    _sync_player_knowledge_to_legacy(state, pk)


def _sync_player_knowledge_to_legacy(state: GameState, pk: dict[str, Any]) -> None:
    """双向兼容：把 player_knowledge 写回 player_known_facts。"""
    legacy = ensure_player_known_facts(state)
    legacy["known_rumors"] = [
        {
            "id": r.get("id"),
            "text": r.get("text"),
            "source_label": r.get("source_label") or r.get("source"),
            "source_type": r.get("source_type", "npc"),
        }
        for r in (pk.get("rumors") or [])
        if isinstance(r, dict) and r.get("id")
    ]
    pf: list[dict[str, Any]] = []
    for obs in pk.get("observations") or []:
        if isinstance(obs, dict):
            pf.append(
                {
                    "id": obs.get("id"),
                    "type": obs.get("type", "observation"),
                    "text": obs.get("text"),
                    "source": obs.get("source"),
                    "introduced_in_narrative": True,
                    "visibility": "public",
                }
            )
    for fact in pk.get("facts") or []:
        if isinstance(fact, dict):
            pf.append(
                {
                    "id": fact.get("id"),
                    "type": fact.get("type", "fact"),
                    "text": fact.get("text"),
                    "source": fact.get("source"),
                    "introduced_in_narrative": True,
                    "visibility": "public",
                }
            )
    legacy["player_facing_facts"] = pf


def build_player_visible(
    scene_graph: dict[str, Any],
    player_knowledge: dict[str, Any],
    *,
    location: str = "",
    known_locations: list[str] | None = None,
    known_npcs: list[str] | None = None,
) -> dict[str, Any]:
    """从 scene_graph 提取玩家可见子集（action_generator 唯一可读的场景信息）。"""
    visible_npcs = []
    for n in scene_graph.get("visible_npcs") or []:
        if isinstance(n, dict):
            visible_npcs.append(
                {
                    "name": n.get("name"),
                    "role": n.get("role"),
                    "emotion": n.get("emotion"),
                    "current_action": n.get("current_action"),
                }
            )
    public_events = [
        ev
        for ev in (scene_graph.get("active_events") or [])
        if isinstance(ev, dict) and ev.get("public", True)
    ]
    return {
        "location": scene_graph.get("location") or location,
        "time": scene_graph.get("time"),
        "weather": scene_graph.get("weather"),
        "visible_npcs": visible_npcs,
        "interactive_objects": list(scene_graph.get("interactive_objects") or []),
        "active_events": public_events,
        "known_locations": list(known_locations or []),
        "known_npcs": list(known_npcs or []),
        "knowledge_ids": sorted(all_knowledge_ids(player_knowledge)),
    }


def empty_action_result() -> dict[str, Any]:
    return {
        "narrative_blocks": [],
        "new_facts": [],
        "new_observations": [],
        "new_questions": [],
        "new_rumors": [],
        "available_followups": [],
    }

"""Grounded Action / Narrative helpers.

目标：
- 所有对玩家可见的选项与叙事，必须只基于 player_known_facts（已知事实）与本回合显式提供的信息。
- 对于不在已知事实中的敏感词，做模糊化处理，避免“提前剧透”。
"""

from __future__ import annotations

from typing import Any

from engine.location_registry import resolve_location_display
from engine.text_sanitizer import sanitize_player_text, contains_forbidden
from engine.world_state import GameState


SENSITIVE_TERMS: dict[str, str] = {
    # 注意：禁止使用“某处/某个方向/失踪者”等 placeholder
    "马库斯的银币": "一处异常痕迹",
    "银币": "痕迹",
    "货箱": "杂物堆",
    "木箱": "杂物堆",
    "强盗营地": "林中深处",
}

UNSOURCED_PHRASES: tuple[str, ...] = (
    "有人说",
    "据说",
    "听说",
    "传闻说",
    "不知从哪里传来",
    "村里都在说",
    "大家都知道",
    "有村民提到",
)


def get_player_known_facts(state: GameState) -> dict[str, list[str]]:
    raw = (state.flags or {}).get("player_known_facts") or (state.flags or {}).get("known_facts")
    if not isinstance(raw, dict):
        raw = {}
    def _lst(k: str) -> list[str]:
        v = raw.get(k)
        if isinstance(v, list):
            return [str(x) for x in v if str(x)]
        return []

    # 玩家可见事实：抽取 text/label 进入 allowlist（用于 scene_requirements.required_known_facts）
    known_fact_terms: list[str] = []
    pf = raw.get("player_facing_facts")
    if isinstance(pf, list):
        for f in pf:
            if isinstance(f, dict):
                lbl = str(f.get("text") or f.get("label") or "").strip()
                if lbl:
                    known_fact_terms.append(lbl)

    return {
        "known_locations": _lst("known_locations"),
        "known_clues": list(dict.fromkeys(_lst("known_clues") + known_fact_terms)),
        "known_npcs": _lst("known_npcs"),
        "known_objects": _lst("known_objects"),
        # known_rumors 在 flags 中为 list[dict]，这里返回其 text 列表用于 allowlist
        "known_rumors": _lst("known_rumors"),
    }


def get_known_rumor_sources(state: GameState) -> set[str]:
    facts = (state.flags or {}).get("player_known_facts") or {}
    if not isinstance(facts, dict):
        return set()
    raw = facts.get("known_rumors")
    if not isinstance(raw, list):
        return set()
    out: set[str] = set()
    for r in raw:
        if isinstance(r, dict):
            lbl = str(r.get("source_label", "")).strip()
            if lbl:
                out.add(lbl)
    return out


def _allowed_terms(state: GameState) -> set[str]:
    facts = get_player_known_facts(state)
    allow: set[str] = set()
    for arr in facts.values():
        allow.update(arr)
    # 当前场景的显式可见对象也允许出现
    allow.add(str(state.location))
    for npc in state.npc_at_location():
        allow.add(npc.name)
    return allow


def filter_unknown_text(text: str, state: GameState) -> str:
    """把未解锁敏感词替换为更模糊的表述（最小侵入，避免剧透）。"""
    if not text:
        return text
    # 先处理“无来源传闻”措辞
    if any(p in text for p in UNSOURCED_PHRASES):
        sources = get_known_rumor_sources(state)
        # 没有任何已知 source 时，直接改为不带“有人说/听说”的中性表述
        if not sources:
            for p in UNSOURCED_PHRASES:
                text = text.replace(p, "")
            text = text.replace("：", "：").strip()
        else:
            # 有 source，但 text 里未提到任何 source_label，则去掉这类措辞
            if not any(lbl in text for lbl in sources):
                for p in UNSOURCED_PHRASES:
                    text = text.replace(p, "")
                text = text.strip()
    allow = _allowed_terms(state)
    out = text
    for term, repl in SENSITIVE_TERMS.items():
        if term in out and term not in allow:
            out = out.replace(term, repl)
    # 仓库/马库斯：用 location_registry 安全表述，禁止“某个方向/失踪者”
    if "仓库" in out and "仓库" not in allow and "旧仓库" not in allow:
        safe = resolve_location_display(state, "仓库")
        out = out.replace("仓库方向", safe)
        out = out.replace("仓库", safe)
    if "马库斯" in out and "马库斯" not in allow:
        out = out.replace("马库斯", "那名商人")
    out = sanitize_player_text(out, state) or out
    if contains_forbidden(out):
        return ""
    return out


def filter_action_obj(action: dict[str, Any], state: GameState) -> dict[str, Any]:
    a = dict(action)
    # rumor：禁止 location 作 source_type
    src = a.get("source")
    if isinstance(src, dict) and str(src.get("type", "")).lower() == "location":
        a["unlocked"] = False
        a["lock_reason"] = "传闻必须有明确说话者，地点不能作为来源"
    label = a.get("label") if isinstance(a.get("label"), str) else ""
    if label and ("打听：" in label or "向村口打听" in label):
        a["unlocked"] = False
        a["lock_reason"] = "请使用行动化选项，而非信息标题式打听"
    if label and any(p in label for p in UNSOURCED_PHRASES):
        src = a.get("source")
        if not (isinstance(src, dict) and str(src.get("label", "")).strip()):
            a["unlocked"] = False
            a["lock_reason"] = "该信息缺少明确来源，无法作为可靠行动线索"
    for k in ("label", "description", "input"):
        if isinstance(a.get(k), str):
            a[k] = filter_unknown_text(a[k], state)
    return a


def _satisfy_scene_requirements(req: dict[str, Any], state: GameState) -> bool:
    if not isinstance(req, dict):
        return True
    loc = req.get("required_location")
    if loc and str(loc) != str(state.location):
        return False
    # visible_npcs: 允许写具体名字，或写一个虚拟标签
    required_npcs = req.get("required_visible_npcs") or []
    if isinstance(required_npcs, list) and required_npcs:
        visible_names = {n.name for n in state.npc_at_location()}
        for n in required_npcs:
            if str(n) in ("guard_patrol_or_two_guards",):
                # 简化：guard_patrol_active 视为“至少两名守卫/巡逻队存在”
                if not state.flags.get("guard_patrol_active"):
                    return False
            else:
                if str(n) not in visible_names:
                    return False
    required_events = req.get("required_active_events") or []
    if isinstance(required_events, list) and required_events:
        scene = state.flags.get("last_scene_graph")
        active_ids: set[str] = set()
        if isinstance(scene, dict):
            for ev in scene.get("active_events") or []:
                if isinstance(ev, dict) and ev.get("id"):
                    active_ids.add(str(ev["id"]))
        for eid in required_events:
            if str(eid) not in active_ids:
                return False
    required_facts = req.get("required_known_facts") or []
    if isinstance(required_facts, list) and required_facts:
        facts = get_player_known_facts(state)
        allow = set()
        for arr in facts.values():
            allow.update(arr)
        for f in required_facts:
            if str(f) not in allow:
                return False
    return True


def filter_actions_payload(payload: dict[str, Any], state: GameState) -> dict[str, Any]:
    """过滤 action_generator 输出，避免选项泄露未发现内容。"""
    out = dict(payload)
    grouped = out.get("grouped") or {}
    if isinstance(grouped, dict):
        new_grouped: dict[str, list[dict[str, Any]]] = {}
        for cat, arr in grouped.items():
            if not isinstance(arr, list):
                continue
            filtered: list[dict[str, Any]] = []
            for x in arr:
                if not isinstance(x, dict):
                    continue
                y = filter_action_obj(x, state)
                # 硬性：follow_clue 只能来自已发现事实
                if "follow_clue" in (y.get("tags") or []):
                    uses = y.get("uses_known_fact") or []
                    if not isinstance(uses, list) or not uses:
                        continue
                    facts = state.flags.get("player_known_facts") or {}
                    pf = facts.get("player_facing_facts") if isinstance(facts, dict) else None
                    known_ids = {str(f.get("id")) for f in (pf or []) if isinstance(f, dict)}
                    if not any(str(u) in known_ids for u in uses):
                        continue
                if not _satisfy_scene_requirements(y.get("scene_requirements") or {}, state):
                    continue
                if not y.get("unlocked", True):
                    continue
                filtered.append(y)
            new_grouped[str(cat)] = filtered
        out["grouped"] = new_grouped
    if isinstance(out.get("flat_inputs"), list):
        out["flat_inputs"] = [filter_unknown_text(str(x), state) for x in out["flat_inputs"]]
    return out


"""Demo — 预设 outcome + 正式版 generate_actions 生成选项（outcome-only，不预设按钮）。"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from engine.narrative_formatter import format_narrative_html
from engine.player_knowledge import apply_action_result, ensure_player_knowledge, get_player_knowledge
from engine.rule_engine import DiceRollInfo, RollOutcome
from engine.text_sanitizer import contains_forbidden, sanitize_player_text
from engine.world_state import GameState


class DemoOutcomeMissingError(KeyError):
    """演示模式下 action_id 无对应 outcome（开发期应补齐脚本或过滤选项）。"""

    def __init__(self, action_id: str) -> None:
        super().__init__(f"Demo outcome missing for action_id={action_id!r}")
        self.action_id = action_id


# action_id → 已有这些 fact/observation id 时不再展示（不靠 consumed_actions）
_DEMO_REDUNDANCY: dict[str, list[str]] = {
    "ask_elena_father_details": ["clue_elena_cargo"],
    "comfort_elena": ["clue_elena_cargo"],
    "ask_elena_cargo_detail": ["fact_elena_cargo_detail"],
    "observe_thomas_reaction": ["observation_thomas_nervous"],
    "observe_elena_reaction": ["observation_elena_anxious_warehouse"],
    "ask_thomas_last_night": ["clue_thomas_patrol"],
    "ask_thomas_patrol_reason": ["clue_thomas_patrol"],
    "ask_thomas_extra_patrol": ["clue_thomas_patrol"],
    "ask_thomas_last_night_disturbance": ["clue_thomas_patrol"],
    "ask_thomas_warehouse_activity": ["clue_thomas_patrol"],
    "inspect_村口_environment": ["clue_muddy_tracks"],
    "talk_米拉": ["clue_mira_guard"],
    "move_村口_酒馆": ["clue_mira_guard"],
    "move_村口_仓库": ["clue_warehouse_crate"],
}

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "demo_scripts" / "ravenford_demo.json"
)
_CACHE: dict[str, Any] | None = None

_NPC_TRUST_KEYS = {
    "elena": "艾琳娜",
    "thomas": "托马斯",
    "mira": "米拉",
}

_ABILITY_ZH: dict[str, str] = {
    "WIS": "感知",
    "CHA": "交涉",
    "DEX": "敏捷",
    "STR": "力量",
    "INT": "智力",
    "CON": "体质",
}

# 调查笔记条目（按推理链顺序展示）
_JOURNAL_CHAIN: list[tuple[str, str]] = [
    ("clue_elena_cargo", "马库斯失踪前提到一批需要连夜确认的货物"),
    ("fact_elena_cargo_detail", "货物为布匹与铁器，须连夜清点入库"),
    ("clue_warehouse_crate", "马库斯最后出现地点：仓库（货箱被撬空）"),
    ("clue_thomas_patrol", "托马斯证实：昨夜二更天马库斯驾车往仓库去"),
    ("clue_mira_guard", "米拉看见守卫深夜调动，马库斯最后前往仓库"),
    ("clue_muddy_tracks", "泥地车辙延伸向黑森林，沿途有拖拽痕迹"),
    ("obs_confirm_warehouse_route", "线索印证：马库斯昨夜确实前往仓库"),
]

_FORBIDDEN_OUTPUT = (
    "你你你你",
    "unknown",
    "undefined",
    "null",
    "guarding_gate",
    "followup",
    "hook",
    "某个方向",
)


def load_demo_script() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        with open(_SCRIPT_PATH, encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def is_demo_story_mode(state: GameState) -> bool:
    return bool(state.flags.get("demo_story_mode"))


def _runtime(state: GameState) -> dict[str, Any]:
    raw = state.flags.get("demo_runner")
    if not isinstance(raw, dict):
        raw = {}
        state.flags["demo_runner"] = raw
    return raw


def init_demo_story(state: GameState) -> None:
    script = load_demo_script()
    meta = script.get("meta") or {}
    state.flags["demo_story_mode"] = True
    state.flags.pop("investigation_mode", None)
    state.flags.pop("demo_story", None)
    state.flags["demo_runner"] = {
        "script_id": script.get("id", "ravenford_demo"),
        "remaining_turns": int(meta.get("max_turns", 6)),
        "choices_log": [],
    }
    state.flags["seed_chapter"] = script.get("chapter") or {"number": 1, "title": "失踪的商人"}
    state.flags.pop("consumed_actions", None)
    crisis = state.flags.get("crisis")
    if not isinstance(crisis, dict):
        crisis = {}
        state.flags["crisis"] = crisis
    crisis.setdefault("pressure", 22.0)
    crisis.setdefault("merchant_status", "missing")


def get_outcomes() -> dict[str, Any]:
    return load_demo_script().get("outcomes") or {}


def _raw_outcome(action_id: str) -> dict[str, Any] | None:
    out = get_outcomes().get(action_id)
    return out if isinstance(out, dict) else None


def _outcome_aliases() -> dict[str, str]:
    raw = load_demo_script().get("outcome_aliases") or {}
    return {str(k): str(v) for k, v in raw.items() if k and v}


def _pk_has_any_id(state: GameState, ids: list[str]) -> bool:
    pk = get_player_knowledge(state)
    known: set[str] = set()
    for bucket in ("facts", "observations", "rumors"):
        for item in pk.get(bucket) or []:
            if isinstance(item, dict) and item.get("id"):
                known.add(str(item["id"]))
    return any(i in known for i in ids)


def resolve_demo_outcome_id(state: GameState | None, action_id: str | None) -> str | None:
    """将 generate_actions 的 action_id 映射到 outcomes 表中的 canonical key。"""
    if not action_id:
        return None
    aid = str(action_id).strip()
    if not aid or aid == "free_input":
        return None
    if _raw_outcome(aid):
        return aid
    aliased = _outcome_aliases().get(aid)
    if aliased and _raw_outcome(aliased):
        return aliased
    if aid.startswith("ask_thomas_"):
        return "ask_thomas_last_night"
    if aid == "ask_elena_cargo_detail" or (aid.startswith("ask_elena_") and "cargo" in aid):
        if state and _pk_has_any_id(state, ["clue_elena_cargo"]):
            return "ask_elena_cargo_detail"
        return "ask_elena_father_details"
    if aid.startswith("ask_elena_"):
        return "ask_elena_father_details"
    if aid.startswith("verify_"):
        return "demo_verify_topic"
    if aid.startswith("observe_") and aid.endswith("_reaction"):
        npc = aid[len("observe_") : -len("_reaction")]
        for key in (f"observe_{npc}_reaction", "observe_thomas_reaction", "observe_elena_reaction"):
            if _raw_outcome(key):
                return key
    if aid.startswith("move_"):
        if "酒馆" in aid:
            return "talk_米拉"
        if "仓库" in aid:
            return "move_村口_仓库"
        if "森林" in aid:
            return "move_村口_森林小路"
    return None


def canonical_demo_action_id(
    state: GameState | None,
    action_id: str | None,
) -> str | None:
    return resolve_demo_outcome_id(state, action_id)


def has_demo_outcome(state: GameState | None, action_id: str | None) -> bool:
    if not action_id:
        return False
    aid = str(action_id).strip()
    if aid == "free_input":
        return True
    key = resolve_demo_outcome_id(state, aid)
    return bool(key and _raw_outcome(key))


def demo_action_redundant(state: GameState, action_id: str) -> bool:
    aid = str(action_id).strip()
    keys = _DEMO_REDUNDANCY.get(aid)
    if not keys:
        canon = resolve_demo_outcome_id(state, aid)
        if canon:
            keys = _DEMO_REDUNDANCY.get(canon)
    if not keys:
        return False
    return _pk_has_any_id(state, keys)


def filter_demo_actions_payload(payload: dict[str, Any], state: GameState) -> dict[str, Any]:
    """仅保留有 outcome 且未因 knowledge 饱和的行动；free_input 始终保留。"""
    out = dict(payload)
    grouped = out.get("grouped")
    if not isinstance(grouped, dict):
        return out
    new_grouped: dict[str, list[dict[str, Any]]] = {}
    flat: list[str] = []
    for cat, arr in grouped.items():
        if not isinstance(arr, list):
            continue
        kept: list[dict[str, Any]] = []
        for act in arr:
            if not isinstance(act, dict):
                continue
            aid = str(act.get("id") or "").strip()
            if not aid:
                continue
            if aid == "free_input":
                kept.append(act)
                continue
            if not has_demo_outcome(state, aid):
                continue
            if demo_action_redundant(state, aid):
                continue
            if not act.get("unlocked", True):
                continue
            kept.append(act)
        new_grouped[str(cat)] = kept
        for act in kept:
            if act.get("category") != "free" and act.get("input"):
                flat.append(str(act["input"]))
    out["grouped"] = new_grouped
    out["flat_inputs"] = flat[:8]
    return out


def all_registered_demo_outcome_keys() -> set[str]:
    keys = set(get_outcomes().keys())
    keys.update(_outcome_aliases().keys())
    keys.add("free_input")
    return keys


def find_outcome(action_id: str) -> dict[str, Any] | None:
    canon = canonical_demo_action_id(None, action_id) or str(action_id).strip()
    return _raw_outcome(canon)


find_step = find_outcome


def find_option(action_id: str) -> dict[str, Any] | None:
    return find_outcome(action_id)


def _normalize_label(text: str) -> str:
    t = re.sub(r"^\[[^\]]+\]\s*", "", (text or "").strip())
    t = re.sub(r"\s+", "", t)
    return t


def ensure_demo_choice_cache(state: GameState) -> list[dict[str, Any]]:
    """与正式版一致：按当前 state 重建可选行动缓存（供 action_id 解析）。"""
    from engine.action_generator import generate_actions
    from engine.choice_renderer import build_inline_choices
    from engine.encounter_state import build_encounter_state
    from engine.narrative_formatter import format_inline_choices

    action_data = generate_actions(state)
    state.flags["last_available_actions"] = action_data
    scene = state.flags.get("last_scene_graph")
    if not isinstance(scene, dict):
        scene = {}
    enc = build_encounter_state(state, {}, {}, None)
    inline = build_inline_choices(state, enc, scene, action_data)
    inline = format_inline_choices(inline, state)
    state.flags["last_inline_choices"] = inline
    return inline


def _iter_last_actions(state: GameState) -> list[dict[str, Any]]:
    last = state.flags.get("last_available_actions") or {}
    grouped = last.get("grouped") if isinstance(last, dict) else None
    out: list[dict[str, Any]] = []
    if isinstance(grouped, dict):
        for arr in grouped.values():
            if isinstance(arr, list):
                out.extend(a for a in arr if isinstance(a, dict))
    return out


def _labels_match(needle: str, label: str) -> bool:
    if not needle or not label:
        return False
    if needle == label or needle in label or label in needle:
        return True
    nn = _normalize_label(needle)
    ln = _normalize_label(label)
    if nn and ln and (nn == ln or nn in ln or ln in nn):
        return True
    return False


def _find_action_id_by_label(state: GameState, text: str) -> str | None:
    needle = (text or "").strip()
    if not needle:
        return None
    if state.flags.get("demo_story_mode"):
        ensure_demo_choice_cache(state)
    inline = state.flags.get("last_inline_choices")
    if isinstance(inline, list):
        for ch in inline:
            if not isinstance(ch, dict):
                continue
            label = str(ch.get("text") or "").strip()
            if _labels_match(needle, label):
                cid = str(ch.get("id") or "").strip()
                if cid and cid != "free_input":
                    return cid
    for act in _iter_last_actions(state):
        for field in ("label", "input"):
            label = str(act.get(field) or "").strip()
            if _labels_match(needle, label):
                aid = str(act.get("id") or "").strip()
                if aid:
                    return aid
    return None


def can_resolve_demo_action(state: GameState | None, action_id: str | None) -> bool:
    if not state or not state.flags.get("demo_story_mode"):
        return False
    if not action_id:
        return True
    aid = str(action_id).strip()
    if canonical_demo_action_id(state, aid):
        return True
    return any(str(a.get("id")) == aid for a in _iter_last_actions(state))


def _key_clue_count(state: GameState) -> int:
    script = load_demo_script()
    keys = set(script.get("key_clue_ids") or [])
    pk = get_player_knowledge(state)
    found: set[str] = set()
    for bucket in ("facts", "observations", "rumors"):
        for item in pk.get(bucket) or []:
            if isinstance(item, dict) and str(item.get("id", "")) in keys:
                found.add(str(item["id"]))
    return len(found)


def _dice_from_preset(preset: dict[str, Any] | None, *, label: str = "") -> DiceRollInfo | None:
    if not isinstance(preset, dict):
        return None
    raw = str(preset.get("result") or preset.get("outcome") or "success").lower()
    if raw in ("success", "critical_success"):
        outcome = RollOutcome.SUCCESS if raw != "critical_success" else RollOutcome.CRITICAL_SUCCESS
    elif raw in ("failure", "critical_failure"):
        outcome = RollOutcome.FAILURE if raw != "critical_failure" else RollOutcome.CRITICAL_FAILURE
    else:
        outcome = RollOutcome.SUCCESS
    natural = int(preset.get("roll") or preset.get("die_roll") or 10)
    mod = int(preset.get("modifier") or 0)
    total = int(preset.get("total") or natural + mod)
    return DiceRollInfo(
        ability=str(preset.get("ability") or "WIS").upper(),
        dc=int(preset.get("dc") or 10),
        die_roll=natural,
        modifier=mod,
        total=total,
        outcome=outcome,
        description=label or f"{preset.get('ability', 'WIS')} 检定",
    )


def _esc(text: str) -> str:
    return html.escape(str(text or "").strip(), quote=False)


def _known_knowledge_ids(state: GameState) -> set[str]:
    pk = get_player_knowledge(state)
    ids: set[str] = set()
    for bucket in ("facts", "observations", "rumors"):
        for item in pk.get(bucket) or []:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    return ids


def _format_dice_check_html(preset: dict[str, Any]) -> str:
    ability = str(preset.get("ability") or "WIS").upper()
    skill = _ABILITY_ZH.get(ability, ability)
    roll = int(preset.get("roll") or preset.get("die_roll") or 10)
    mod = int(preset.get("modifier") or 0)
    total = int(preset.get("total") or roll + mod)
    raw = str(preset.get("result") or preset.get("outcome") or "success").lower()
    if raw in ("success", "critical_success"):
        outcome_zh = "成功"
    elif raw in ("failure", "critical_failure"):
        outcome_zh = "失败"
    else:
        outcome_zh = "成功"
    mod_s = f"+ {mod}" if mod >= 0 else str(mod)
    return (
        f'<div class="dice-check">'
        f'<p class="dice-check-title">【{skill}检定】</p>'
        f'<p class="dice-check-roll">D20 = {roll} {mod_s} = {total}</p>'
        f'<p class="dice-check-outcome">结果：{outcome_zh}</p>'
        f"</div>"
    )


def _build_journal_lines_html(lines: list[str]) -> str:
    items = [f"<li>✓ {_esc(line)}</li>" for line in lines if str(line).strip()]
    if not items:
        return ""
    return (
        f'<div class="investigation-journal">'
        f'<p class="journal-title">调查笔记更新：</p>'
        f'<ul class="journal-list">{"".join(items)}</ul>'
        f"</div>"
    )


def _build_investigation_journal_html(state: GameState) -> str:
    known = _known_knowledge_ids(state)
    lines: list[str] = []
    for fid, label in _JOURNAL_CHAIN:
        if fid in known:
            lines.append(f"<li>✓ {_esc(label)}</li>")
    if not lines:
        return ""
    return (
        f'<div class="investigation-journal">'
        f'<p class="journal-title">调查笔记更新：</p>'
        f'<ul class="journal-list">{"".join(lines)}</ul>'
        f"</div>"
    )


def _sanitize_demo_text(text: str, state: GameState) -> str:
    t = sanitize_player_text(text, state=state) if text else ""
    t = re.sub(r"你{3,}", "你", t)
    for bad in _FORBIDDEN_OUTPUT:
        if bad in t:
            t = t.replace(bad, "")
    return t.strip()


def blocks_to_html(
    *,
    player_action_echo: str | None = None,
    narrative_blocks: list[dict[str, Any]] | None = None,
    world_events: list[dict[str, Any]] | None = None,
    ending_blocks: list[dict[str, Any]] | None = None,
    dice_preset: dict[str, Any] | None = None,
    append_journal: bool = False,
    notebook_lines: list[str] | None = None,
    state: GameState,
) -> str:
    parts: list[str] = []
    if player_action_echo:
        echo = _sanitize_demo_text(player_action_echo, state)
        if echo:
            inner = echo
            if "你选择" in echo and "<strong>" not in echo:
                m = re.search(r"你选择[：:]\s*[「\"“]?(.+?)[」\"”]?\s*$", echo)
                inner = (
                    f'你选择：<strong>「{html.escape(m.group(1))}」</strong>'
                    if m
                    else html.escape(echo)
                )
            parts.append(f'<p class="player-action">{inner}</p>')

    if isinstance(dice_preset, dict) and dice_preset:
        parts.append(_format_dice_check_html(dice_preset))

    for block in narrative_blocks or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "scene")
        if btype == "dice_check" and isinstance(block.get("dice"), dict):
            parts.append(_format_dice_check_html(block["dice"]))
            continue
        text = _sanitize_demo_text(str(block.get("text") or ""), state)
        if not text and btype not in ("journal",):
            if btype != "dialogue":
                continue
        if text and contains_forbidden(text):
            continue
        if btype == "dialogue":
            speaker = _sanitize_demo_text(str(block.get("speaker") or ""), state)
            parts.append(
                f'<p class="dialogue"><strong>{_esc(speaker)}：</strong>{_esc(text)}</p>'
            )
        elif btype == "thought":
            parts.append(f'<p class="thought">{_esc(text)}</p>')
        elif btype == "result":
            parts.append(f'<p class="result">{_esc(text)}</p>')
        elif btype == "clue":
            parts.append(f'<p class="clue-acquired">【获得线索：{_esc(text)}】</p>')
        elif btype == "clue_confirm":
            parts.append(f'<p class="clue-confirm">【线索印证：{_esc(text)}】</p>')
        elif btype == "consequence":
            if text.startswith("获得线索") or text.startswith("【获得线索"):
                inner = text.replace("获得线索：", "").replace("【获得线索：", "").rstrip("】")
                parts.append(f'<p class="clue-acquired">【获得线索：{_esc(inner)}】</p>')
            else:
                parts.append(f'<p class="consequence">{_esc(text)}</p>')
        elif btype == "world":
            parts.append(f'<p class="world">{_esc(text)}</p>')
        elif btype == "note":
            parts.append(f'<p class="player-note">{_esc(text)}</p>')
        else:
            parts.append(f'<p class="scene">{_esc(text)}</p>')

    for ev in world_events or []:
        if isinstance(ev, dict):
            text = _sanitize_demo_text(str(ev.get("text") or ""), state)
            if text:
                parts.append(f'<p class="world">{_esc(text)}</p>')

    for block in ending_blocks or []:
        if isinstance(block, dict):
            text = _sanitize_demo_text(str(block.get("text") or ""), state)
            if text:
                btype = str(block.get("type") or "scene")
                cls = "consequence" if btype == "consequence" else "result"
                parts.append(f'<p class="{cls}">{_esc(text)}</p>')

    if append_journal:
        journal = ""
        if notebook_lines:
            journal = _build_journal_lines_html(notebook_lines)
        elif state.flags.get("scripted_demo_mode"):
            rt = state.flags.get("scripted_demo")
            if isinstance(rt, dict) and rt.get("notebook"):
                journal = _build_journal_lines_html(list(rt.get("notebook") or []))
        if not journal:
            journal = _build_investigation_journal_html(state)
        if journal:
            parts.append(journal)

    return "\n".join(parts)


def get_opening_narrative_html(state: GameState) -> str:
    opening = load_demo_script().get("opening") or {}
    html_body = blocks_to_html(narrative_blocks=opening.get("narrative_blocks"), state=state)
    return format_narrative_html(html_body, state)


def get_demo_prologue(state: GameState) -> str:
    opening = load_demo_script().get("opening") or {}
    blocks = opening.get("narrative_blocks") or []
    if blocks and isinstance(blocks[0], dict):
        text = str(blocks[0].get("text") or "")
        if text:
            return f"<p>{_esc(text)}</p>"
    return "<p>雨后的雷文福德笼罩在灰蓝色晨光里。</p>"


get_demo_opening_narrative = get_opening_narrative_html


def _resolve_dynamic_outcome(
    state: GameState,
    action_id: str,
    base: dict[str, Any],
    *,
    source_action_id: str = "",
    player_label: str = "",
) -> dict[str, Any]:
    script = load_demo_script()
    meta = script.get("meta") or {}
    min_safe = int(meta.get("min_key_clues_for_forest_safe", 3))
    min_rescue = int(meta.get("min_key_clues_for_rescue", 4))
    kc = _key_clue_count(state)
    dynamic = str(base.get("dynamic") or "")

    if dynamic == "forest_entry" or action_id == "move_村口_森林小路":
        echo = "你选择：“直接前往黑森林入口。”"
        if kc < min_safe:
            return {
                "player_action_echo": echo,
                "dice": {"ability": "DEX", "roll": 6, "modifier": 2, "total": 8, "dc": 14, "result": "failure"},
                "narrative_blocks": [
                    {"type": "scene", "text": "你刚踏入林间，脚下绳索猛然收紧。"},
                    {"type": "result", "text": "瓦里克的笑声从雾后传来——你闯入了尚未摸清底细的陷阱。"},
                ],
                "state_changes": {"remaining_turns": -1, "ending_id": "ending_d_trap"},
            }
        if kc >= min_rescue:
            return {
                "player_action_echo": echo,
                "dice": {"ability": "WIS", "roll": 16, "modifier": 2, "total": 18, "dc": 13, "result": "success"},
                "narrative_blocks": [
                    {"type": "scene", "text": "你沿足迹深入林间空地，在枯树下找到了被绑的马库斯。"},
                    {"type": "result", "text": "瓦里克退入雾中，马库斯跌跪在地。"},
                ],
                "state_changes": {
                    "remaining_turns": -1,
                    "location": "森林小路",
                    "ending_id": "ending_a_rescue",
                },
            }
        return {
            "player_action_echo": echo,
            "dice": {"ability": "WIS", "roll": 14, "modifier": 2, "total": 16, "dc": 12, "result": "success"},
            "narrative_blocks": [
                {"type": "scene", "text": "你在林缘发现被丢弃的麻绳与血迹，深处仍有埋伏。"},
                {"type": "consequence", "text": "已确认黑森林方向异常，但线索仍不足以安全深入。"},
            ],
            "new_facts": [
                {
                    "id": "clue_forest_path",
                    "text": "黑森林入口有绑架拖拽痕迹",
                    "source": "现场调查",
                    "type": "clue",
                }
            ],
            "state_changes": {"remaining_turns": -1, "location": "森林小路"},
        }

    if dynamic == "forest_rescue" or action_id == "track_forest":
        if kc >= min_rescue:
            return {
                "player_action_echo": "你选择：“沿小路追踪可疑脚印。”",
                "dice": {"ability": "WIS", "roll": 17, "modifier": 2, "total": 19, "dc": 13, "result": "success"},
                "narrative_blocks": [
                    {"type": "result", "text": "你在林间空地救出了马库斯。"},
                ],
                "state_changes": {"remaining_turns": -1, "ending_id": "ending_a_rescue"},
            }
        return {
            "player_action_echo": "你选择：“沿小路追踪可疑脚印。”",
            "narrative_blocks": [
                {"type": "result", "text": "浓雾遮住视线，足迹在林间消失，你需要更多村口线索。"},
            ],
            "state_changes": {"remaining_turns": -1},
        }

    if action_id == "demo_verify_topic":
        echo = player_label or "你选择：“向在场者求证你已掌握的线索。”"
        sid = str(source_action_id or "")
        if "thomas" in sid and ("last_seen" in sid or "warehouse" in sid or "cargo" in sid):
            return {
                **base,
                "player_action_echo": echo,
                "narrative_blocks": [
                    {"type": "scene", "text": "你转向托马斯，把艾琳娜的说法简要复述了一遍。"},
                    {"type": "scene", "text": "守卫长沉默片刻，才缓缓开口。"},
                    {"type": "dialogue", "speaker": "托马斯", "text": "我见过马库斯。"},
                    {"type": "dialogue", "speaker": "托马斯", "text": "昨晚大概二更天，他驾着马车往仓库去了。当时还下着雨，我记得很清楚。"},
                    {"type": "scene", "text": "托马斯皱起眉。"},
                    {"type": "dialogue", "speaker": "托马斯", "text": "后来他没再回来。"},
                    {"type": "result", "text": "这与艾琳娜的说法完全一致。"},
                    {"type": "clue_confirm", "text": "马库斯昨夜确实前往仓库"},
                ],
                "new_observations": [
                    {
                        "id": "obs_confirm_warehouse_route",
                        "text": "托马斯印证：马库斯昨夜二更天驾车前往仓库，此后未归",
                        "source": "托马斯",
                        "type": "observation",
                    }
                ],
            }
        if "elena" in sid and "cargo" in sid:
            return {
                **base,
                "player_action_echo": echo,
                "narrative_blocks": [
                    {"type": "scene", "text": "艾琳娜用力点头，把昨夜的话又重复了一遍。"},
                    {"type": "dialogue", "speaker": "艾琳娜", "text": "父亲出门前一直念叨那批货……他说必须今晚确认清楚，不能耽误商队启程。"},
                    {"type": "clue_confirm", "text": "马库斯失踪前确曾提到连夜确认的货物"},
                ],
            }
        if "mira" in sid:
            return {
                **base,
                "player_action_echo": echo,
                "narrative_blocks": [
                    {"type": "scene", "text": "米拉擦了擦吧台，压低声音。"},
                    {"type": "dialogue", "speaker": "米拉", "text": "没错，我亲眼看见——最后一趟马车也是往仓库方向去的，守卫那阵子忙得很。"},
                    {"type": "clue_confirm", "text": "马库斯最后前往仓库，守卫深夜有调动"},
                ],
            }
        return {
            **base,
            "player_action_echo": echo,
            "narrative_blocks": [
                {"type": "scene", "text": "对方听你把已知线索逐一列出，神情渐渐松动。"},
                {"type": "result", "text": "细节与先前所得相互吻合，只是措辞与顺序略有不同——这反而更像真话。"},
            ],
        }

    if action_id == "inspect_村口_environment":
        prefix: list[dict[str, Any]] = []
        if _pk_has_any_id(
            state,
            ["clue_elena_cargo", "clue_thomas_patrol", "clue_mira_guard", "clue_warehouse_crate"],
        ):
            prefix = [
                {
                    "type": "thought",
                    "text": "仓库是马库斯最后出现的地点。如果他离开仓库后失踪，那么仓库附近应该还能留下痕迹——",
                },
                {"type": "scene", "text": "你决定检查村口泥地。"},
            ]
        blocks = prefix + list(base.get("narrative_blocks") or [])
        return {**base, "narrative_blocks": blocks}

    return base


def _outcome_to_action_result(outcome: dict[str, Any]) -> dict[str, Any]:
    npc_changes = []
    for key, delta in (outcome.get("npc_trust_changes") or {}).items():
        nid = str(key).lower()
        npc_changes.append(
            {
                "npc_id": nid,
                "trust_delta": int(delta),
                "suspicion_delta": -int(delta) // 2 if int(delta) > 0 else 0,
            }
        )
    return {
        "new_facts": list(outcome.get("new_facts") or []),
        "new_observations": list(outcome.get("new_observations") or []),
        "new_rumors": list(outcome.get("new_rumors") or []),
        "new_questions": list(outcome.get("new_questions") or []),
        "known_topics": list(outcome.get("new_topics") or []),
        "npc_state_changes": npc_changes,
    }


def _apply_outcome_state(state: GameState, outcome: dict[str, Any]) -> dict[str, Any]:
    rt = _runtime(state)
    out: dict[str, Any] = {"demo_runner": dict(rt)}
    sc = outcome.get("state_changes") if isinstance(outcome.get("state_changes"), dict) else {}

    delta_turns = int(sc.get("remaining_turns") or 0)
    if not delta_turns and int(outcome.get("remaining_turns") or 0):
        delta_turns = int(outcome["remaining_turns"])
    if delta_turns:
        rt["remaining_turns"] = max(0, int(rt.get("remaining_turns", 6)) + delta_turns)
        out["remaining_turns"] = rt["remaining_turns"]

    cp = int(outcome.get("crisis_pressure_delta") or sc.get("crisis_pressure") or 0)
    if cp:
        crisis = state.flags.setdefault("crisis", {})
        if isinstance(crisis, dict):
            crisis["pressure"] = min(100.0, max(0.0, float(crisis.get("pressure", 22)) + cp))
        out["crisis_pressure_delta"] = cp

    loc = sc.get("location")
    if loc:
        state.location = str(loc)
        out["moved_to"] = str(loc)

    ending_id = sc.get("ending_id")
    if ending_id:
        _apply_ending(state, str(ending_id))
        out["ending_id"] = str(ending_id)

    return out


def _apply_ending(state: GameState, ending_id: str) -> None:
    script = load_demo_script()
    copy = (script.get("endings") or {}).get(ending_id) or {}
    state.flags["chapter_ending_id"] = ending_id
    state.flags["chapter_complete"] = True
    state.flags["game_phase"] = "chapter_complete"
    crisis = state.flags.get("crisis")
    if isinstance(crisis, dict):
        if ending_id == "ending_a_rescue":
            crisis["merchant_status"] = "resolved"
            crisis["pressure"] = max(0.0, float(crisis.get("pressure", 30)) - 25)
        else:
            crisis["merchant_status"] = "dead"
            crisis["pressure"] = min(100.0, float(crisis.get("pressure", 50)) + 20)
    for q in state.quests:
        if q.id == "missing_merchant":
            q.status = "completed" if ending_id == "ending_a_rescue" else "failed"
    rt = _runtime(state)
    rt["ending_title"] = copy.get("title", "")


def _check_turn_limit_ending(state: GameState) -> str | None:
    if state.flags.get("chapter_complete"):
        return None
    rt = _runtime(state)
    if int(rt.get("remaining_turns", 0)) > 0:
        return None
    min_safe = int((load_demo_script().get("meta") or {}).get("min_key_clues_for_forest_safe", 3))
    if _key_clue_count(state) < min_safe:
        return "ending_c_coverup"
    return None


def resolve_demo_action_id(
    *,
    state: GameState | None = None,
    action_id: str | None = None,
    intent_payload: dict[str, Any] | None = None,
    player_text: str = "",
) -> str | None:
    def _resolve_id(raw_id: str | None) -> str | None:
        if not raw_id:
            return None
        aid = str(raw_id).strip()
        if not aid or aid == "free_input":
            return None
        if state and has_demo_outcome(state, aid):
            return aid
        return None

    demo = bool(state and state.flags.get("demo_story_mode"))

    if action_id:
        resolved = _resolve_id(str(action_id))
        if resolved and has_demo_outcome(state, resolved):
            return str(action_id).strip()

    if isinstance(intent_payload, dict):
        iid = intent_payload.get("action_id")
        if iid:
            resolved = _resolve_id(str(iid))
            if resolved and has_demo_outcome(state, resolved):
                return str(iid).strip()

    text = (player_text or "").strip()
    if text and state is not None:
        if demo:
            ensure_demo_choice_cache(state)
        by_label = _find_action_id_by_label(state, text)
        if by_label:
            return _resolve_id(by_label) or (by_label if demo else None)
        for oid, opt in get_outcomes().items():
            if not isinstance(opt, dict):
                continue
            for field in ("label", "player_action_echo"):
                label = str(opt.get(field) or "")
                if label and label in text:
                    return oid

    if demo and text:
        return _find_action_id_by_label(state, text)
    return None


def build_session_summary(state: GameState, ending_id: str) -> dict[str, Any]:
    script = load_demo_script()
    copy = (script.get("endings") or {}).get(ending_id) or {}
    pk = get_player_knowledge(state)
    all_items = []
    for k in ("facts", "observations", "rumors"):
        all_items.extend(pk.get(k) or [])
    return {
        "chapter": state.flags.get("seed_chapter") or script.get("chapter"),
        "ending": {
            "id": ending_id,
            "title": copy.get("title", ""),
            "subtitle": copy.get("subtitle", ""),
            "epigraph": copy.get("epigraph", ""),
        },
        "key_choices": list(_runtime(state).get("choices_log") or [])[-12:],
        "clues": {
            "discovered": [
                str(x.get("text", "")) for x in all_items if isinstance(x, dict) and x.get("text")
            ],
        },
        "turns_played": len(_runtime(state).get("choices_log") or []),
        "seed_id": state.flags.get("seed_id"),
    }


def process_demo_action(
    state: GameState,
    action_id: str,
    *,
    player_label: str = "",
    turn: int = 0,
) -> dict[str, Any]:
    """应用预设 outcome；下一步选项由 game_loop 调用 generate_actions 生成。"""
    if str(action_id).strip() == "free_input":
        raise ValueError("演示模式请从叙事选项中选择具体行动，或使用选项中的自由输入入口")

    canon = resolve_demo_outcome_id(state, action_id)
    if not canon:
        raise DemoOutcomeMissingError(str(action_id))
    base = find_outcome(canon)
    if not base:
        raise DemoOutcomeMissingError(str(action_id))

    outcome = _resolve_dynamic_outcome(
        state,
        canon,
        dict(base),
        source_action_id=str(action_id),
        player_label=player_label,
    )
    apply_action_result(state, _outcome_to_action_result(outcome))
    changes = _apply_outcome_state(state, outcome)

    script = load_demo_script()
    ending_id = (outcome.get("state_changes") or {}).get("ending_id")
    ending_blocks: list[dict[str, Any]] = []
    if ending_id:
        ending_blocks = list((script.get("endings") or {}).get(str(ending_id), {}).get("narrative_blocks") or [])

    narrative = blocks_to_html(
        player_action_echo=str(outcome.get("player_action_echo") or player_label or ""),
        narrative_blocks=outcome.get("narrative_blocks"),
        world_events=outcome.get("world_events"),
        ending_blocks=ending_blocks,
        dice_preset=outcome.get("dice") if isinstance(outcome.get("dice"), dict) else None,
        append_journal=True,
        state=state,
    )
    narrative = format_narrative_html(narrative, state)

    turn_ending = _check_turn_limit_ending(state)
    if turn_ending and not state.flags.get("chapter_complete"):
        ending_id = turn_ending
        _apply_ending(state, turn_ending)
        end_copy = (script.get("endings") or {}).get(turn_ending) or {}
        narrative += "\n" + blocks_to_html(
            ending_blocks=end_copy.get("narrative_blocks"),
            state=state,
        )
        changes["ending_id"] = turn_ending

    rt = _runtime(state)
    rt.setdefault("choices_log", []).append(
        {"turn": turn, "action_id": action_id, "label": player_label or outcome.get("player_action_echo", "")}
    )

    dice = _dice_from_preset(
        outcome.get("dice") if isinstance(outcome.get("dice"), dict) else None,
        label=action_id,
    )

    session_summary = None
    if state.flags.get("chapter_complete") and ending_id:
        session_summary = build_session_summary(state, str(ending_id))

    return {
        "narrative": narrative,
        "changes": changes,
        "dice": dice,
        "ending_id": ending_id,
        "session_summary": session_summary,
        "chapter_complete": bool(state.flags.get("chapter_complete")),
        "action_result": _outcome_to_action_result(outcome),
    }


apply_demo_option = process_demo_action
resolve_demo_option_id = resolve_demo_action_id

# 禁止从脚本读取 next_actions — 测试可 patch 此函数
def get_script_next_actions() -> None:
    """Demo 不使用脚本 next_actions；保留供测试断言。"""
    return None

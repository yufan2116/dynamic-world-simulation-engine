"""持久调查板 — 实体常驻、交互可重复、随线索/信任解锁（Demo 调查模式）。"""
from __future__ import annotations

from typing import Any

from engine.investigation_mode import (
    KEY_CLUES,
    PRESSURE_PER_TURN,
    _add_clue,
    _apply_delta,
    _clue_count,
    _inv,
    apply_ending,
    evaluate_ending,
    get_discovered_clues,
)
from engine.world_state import GameState

ENTITIES: list[dict[str, Any]] = [
    {"id": "npc_thomas", "kind": "npc", "name": "托马斯", "subtitle": "村口守卫", "location": "村口"},
    {"id": "npc_elena", "kind": "npc", "name": "艾琳娜", "subtitle": "失踪者的女儿", "location": "村口"},
    {"id": "npc_mira", "kind": "npc", "name": "米拉", "subtitle": "酒馆老板娘", "location": "酒馆"},
    {"id": "loc_gate", "kind": "location", "name": "村口", "subtitle": "泥泞小径与火把", "location": "村口"},
    {"id": "loc_tavern", "kind": "location", "name": "酒馆", "subtitle": "低语与麦酒的气味", "location": "酒馆"},
    {"id": "loc_warehouse", "kind": "location", "name": "仓库", "subtitle": "旧货箱与潮气", "location": "仓库"},
    {"id": "loc_forest", "kind": "location", "name": "黑森林入口", "subtitle": "脚印没入林间", "location": "森林小路"},
]

INTERACTIONS: list[dict[str, Any]] = [
    # —— 艾琳娜 ——
    {
        "id": "int_elena_father",
        "entity_id": "npc_elena",
        "category": "social",
        "skill": "交涉",
        "label": "询问父亲最后去向",
        "ability": "WIS",
        "dc": 10,
        "clue_id": "clue_elena_last_seen",
        "on_success": {"clue": "clue_elena_last_seen", "elena_trust": 1},
        "on_fail": {"elena_trust": -1},
        "success_narrative": (
            "<p class=\"result\">艾琳娜哽咽着说：父亲昨夜答应去<strong>仓库</strong>清点货物，"
            "雨太大，再也没回来。</p>"
        ),
        "fail_narrative": "<p class=\"result\">她别过脸，只能反复说「昨晚没回来」。</p>",
        "repeat_narrative": "<p class=\"result\">艾琳娜又提起父亲去了仓库，语气里满是恐惧。</p>",
    },
    {
        "id": "int_elena_comfort",
        "entity_id": "npc_elena",
        "category": "social",
        "skill": "交涉",
        "label": "安慰并建立信任",
        "ability": "CHA",
        "dc": 9,
        "on_success": {"elena_trust": 1},
        "on_fail": {},
        "success_narrative": "<p class=\"result\">她稍稍平复，愿意把你当作可以依靠的人。</p>",
        "fail_narrative": "<p class=\"result\">她摇了摇头，仍被恐慌攫住。</p>",
        "repeat_narrative": "<p class=\"result\">你陪在她身边，她低声道谢。</p>",
    },
    # —— 托马斯 ——
    {
        "id": "int_thomas_patrol",
        "entity_id": "npc_thomas",
        "category": "social",
        "skill": "交涉",
        "label": "询问昨夜巡逻",
        "ability": "CHA",
        "dc": 12,
        "clue_id": "clue_patrol_anomaly",
        "on_success": {"clue": "clue_patrol_anomaly", "thomas_trust": 1},
        "on_fail": {"thomas_suspicion": 1},
        "success_narrative": (
            "<p class=\"result\">托马斯压低声音：昨夜<strong>旧仓库方向</strong>有人影，"
            "他已加派哨岗，但上面不让声张。</p>"
        ),
        "fail_narrative": "<p class=\"result\">托马斯手按剑柄：「昨夜的事与你无关。」</p>",
        "repeat_narrative": "<p class=\"result\">他再次提到仓库方向的不寻常动静。</p>",
    },
    {
        "id": "int_thomas_warehouse",
        "entity_id": "npc_thomas",
        "category": "social",
        "skill": "交涉",
        "label": "追问仓库方向异常",
        "ability": "CHA",
        "dc": 13,
        "requires_clues": ["clue_patrol_anomaly"],
        "clue_id": "clue_merchant_records",
        "on_success": {"clue": "clue_merchant_records", "thomas_trust": 1},
        "on_fail": {"thomas_suspicion": 1},
        "success_narrative": (
            "<p class=\"result\">托马斯翻出值班簿：马库斯昨夜签过<strong>商队记录</strong>，"
            "之后便再无登记。</p>"
        ),
        "fail_narrative": "<p class=\"result\">他合上册子：「没有更多了。」</p>",
        "repeat_narrative": "<p class=\"result\">值班簿上马库斯的名字仍停在那夜。</p>",
    },
    {
        "id": "int_thomas_private",
        "entity_id": "npc_thomas",
        "category": "social",
        "skill": "交涉",
        "label": "私下询问真正原因",
        "ability": "CHA",
        "dc": 11,
        "min_trust": {"thomas_trust": 2},
        "on_success": {"thomas_trust": 1, "thomas_suspicion": -1},
        "on_fail": {"thomas_suspicion": 1},
        "success_narrative": (
            "<p class=\"result\">托马斯终于承认：队长下令封锁消息，怕引起恐慌。"
            "但他相信马库斯仍活着。</p>"
        ),
        "fail_narrative": "<p class=\"result\">他别过脸：「别逼我违令。」</p>",
        "repeat_narrative": "<p class=\"result\">他仍坚持马库斯可能还活着。</p>",
    },
    {
        "id": "int_thomas_face",
        "entity_id": "npc_thomas",
        "category": "investigate",
        "skill": "感知",
        "label": "留意他的表情",
        "ability": "WIS",
        "dc": 11,
        "on_success": {"thomas_suspicion": -1},
        "on_fail": {"thomas_suspicion": 1},
        "success_narrative": "<p class=\"result\">他眼神闪躲，但不像在撒谎——更像在害怕什么。</p>",
        "fail_narrative": "<p class=\"result\">他立刻板起脸，不再与你对视。</p>",
        "repeat_narrative": "<p class=\"result\">他的不安没有消退。</p>",
    },
    {
        "id": "int_thomas_gear",
        "entity_id": "npc_thomas",
        "category": "investigate",
        "skill": "感知",
        "label": "检查装备泥痕",
        "ability": "WIS",
        "dc": 10,
        "requires_clues": ["clue_muddy_tracks"],
        "on_success": {},
        "on_fail": {"stamina": -1},
        "success_narrative": (
            "<p class=\"result\">他靴底沾着与村口相同的黑泥——昨夜他确实去过林缘。</p>"
        ),
        "fail_narrative": "<p class=\"result\">泥痕太淡，你无法确认。</p>",
        "repeat_narrative": "<p class=\"result\">黑泥仍粘在靴跟。</p>",
    },
    # —— 米拉 ——
    {
        "id": "int_mira_gossip",
        "entity_id": "npc_mira",
        "category": "social",
        "skill": "交涉",
        "label": "打听村里传闻",
        "ability": "CHA",
        "dc": 11,
        "clue_id": "clue_mira_saw_guard",
        "on_success": {"clue": "clue_mira_saw_guard", "mira_trust": 1},
        "on_fail": {"mira_trust": -1},
        "success_narrative": (
            "<p class=\"result\">米拉凑近你：她看见<strong>守卫深夜调动</strong>，"
            "马库斯最后一趟也往仓库方向去了。</p>"
        ),
        "fail_narrative": "<p class=\"result\">米拉摇头：「我现在没心情聊这个。」</p>",
        "repeat_narrative": "<p class=\"result\">她仍坚持守卫昨夜有异动。</p>",
    },
    {
        "id": "int_mira_records",
        "entity_id": "npc_mira",
        "category": "social",
        "skill": "交涉",
        "label": "询问商队登记",
        "ability": "CHA",
        "dc": 10,
        "requires_clues": ["clue_elena_last_seen"],
        "on_success": {"mira_trust": 1},
        "on_fail": {},
        "success_narrative": (
            "<p class=\"result\">米拉翻出账本：马库斯曾托她保管一份<strong>商队记录</strong>副本。</p>"
        ),
        "fail_narrative": "<p class=\"result\">她找不到那本副本了。</p>",
        "repeat_narrative": "<p class=\"result\">她指了指柜台下的抽屉。</p>",
    },
    # —— 村口 ——
    {
        "id": "int_gate_mud",
        "entity_id": "loc_gate",
        "category": "investigate",
        "skill": "感知",
        "label": "检查泥地痕迹",
        "ability": "WIS",
        "dc": 11,
        "clue_id": "clue_muddy_tracks",
        "on_success": {"clue": "clue_muddy_tracks"},
        "on_fail": {"stamina": -1},
        "success_narrative": (
            "<p class=\"result\">泥地里留着车辙与凌乱脚印，方向指向<strong>黑森林</strong>，"
            "边缘有拖拽痕迹。</p>"
        ),
        "fail_narrative": "<p class=\"result\">雨水冲刷了大部分痕迹。</p>",
        "repeat_narrative": "<p class=\"result\">脚印仍指向森林深处。</p>",
    },
    {
        "id": "int_gate_torch",
        "entity_id": "loc_gate",
        "category": "investigate",
        "skill": "感知",
        "label": "观察火把与门楼",
        "ability": "WIS",
        "dc": 9,
        "on_success": {},
        "on_fail": {},
        "success_narrative": (
            "<p class=\"result\">火把油渍新鲜，说明守卫整夜未松懈——"
            "却仍有东西从门下溜出。</p>"
        ),
        "fail_narrative": "<p class=\"result\">风雨掩盖了细节。</p>",
        "repeat_narrative": "<p class=\"result\">门楼静立，雨后的潮气扑面。</p>",
    },
    # —— 酒馆 ——
    {
        "id": "int_tavern_listen",
        "entity_id": "loc_tavern",
        "category": "investigate",
        "skill": "感知",
        "label": "偷听酒客低语",
        "ability": "WIS",
        "dc": 10,
        "on_success": {"mira_trust": 1},
        "on_fail": {},
        "success_narrative": (
            "<p class=\"result\">酒客议论：昨夜仓库有火光，守卫却说是「走火」。</p>"
        ),
        "fail_narrative": "<p class=\"result\">人声太杂，你听不清要点。</p>",
        "repeat_narrative": "<p class=\"result\">「仓库」「火光」仍是最多的词。</p>",
    },
    # —— 仓库 ——
    {
        "id": "int_warehouse_crate",
        "entity_id": "loc_warehouse",
        "category": "investigate",
        "skill": "感知",
        "label": "检查可疑木箱",
        "ability": "WIS",
        "dc": 12,
        "requires_clues": ["clue_elena_last_seen"],
        "clue_id": "clue_suspicious_crate",
        "on_success": {"clue": "clue_suspicious_crate"},
        "on_fail": {"stamina": -1},
        "success_narrative": (
            "<p class=\"result\">木箱边沿有新鲜撬痕，内里空无一物——"
            "像有人匆忙运走了什么。</p>"
        ),
        "fail_narrative": "<p class=\"result\">箱子里只有潮湿的稻草。</p>",
        "repeat_narrative": "<p class=\"result\">撬痕仍在，货物已空。</p>",
    },
    {
        "id": "int_warehouse_ledgers",
        "entity_id": "loc_warehouse",
        "category": "investigate",
        "skill": "感知",
        "label": "翻查货单记录",
        "ability": "INT",
        "dc": 11,
        "requires_clues": ["clue_merchant_records"],
        "on_success": {},
        "on_fail": {},
        "success_narrative": (
            "<p class=\"result\">货单显示马库斯清点的是一批要运往林边的布匹——"
            "与绑匪营地有关。</p>"
        ),
        "fail_narrative": "<p class=\"result\">墨迹模糊，难以辨认。</p>",
        "repeat_narrative": "<p class=\"result\">布匹条目旁有马库斯的签名。</p>",
    },
    # —— 黑森林 ——
    {
        "id": "int_forest_enter",
        "entity_id": "loc_forest",
        "category": "survival",
        "skill": "行动",
        "label": "深入追踪下落",
        "ability": "DEX",
        "dc": 0,
        "requires_roll": False,
        "min_clues": 3,
        "clue_id": "clue_forest_trail",
        "on_success": {},
        "success_narrative": (
            "<p class=\"result\">你沿脚印深入黑森林，在营地边缘发现了被押送的商人——"
            "真相就在眼前。</p>"
        ),
        "fail_narrative": "",
        "repeat_narrative": "<p class=\"result\">林间小径仍通向那座营地。</p>",
    },
]

# 扩展 KEY_CLUES 展示（与 investigation_mode 合并展示）
BOARD_CLUES: list[dict[str, str]] = [
    {"id": "clue_elena_last_seen", "label": "艾琳娜：父亲昨夜去了仓库"},
    {"id": "clue_patrol_anomaly", "label": "托马斯：昨夜巡逻异常"},
    {"id": "clue_mira_saw_guard", "label": "米拉：看见守卫深夜调动"},
    {"id": "clue_muddy_tracks", "label": "村口：泥泞脚印指向黑森林"},
    {"id": "clue_suspicious_crate", "label": "仓库：可疑木箱撬痕"},
    {"id": "clue_merchant_records", "label": "商队记录：马库斯昨夜登记"},
    {"id": "clue_forest_trail", "label": "黑森林：马库斯被带往营地"},
]

CATEGORY_LABELS = {"social": "交涉", "investigate": "观察", "survival": "行动"}


def _interaction_def(iid: str) -> dict[str, Any] | None:
    for it in INTERACTIONS:
        if it["id"] == iid:
            return it
    return None


def _entity_def(eid: str) -> dict[str, Any] | None:
    for ent in ENTITIES:
        if ent["id"] == eid:
            return ent
    return None


def _trust_value(inv: dict[str, Any], key: str) -> int:
    return int(inv.get(key, 0))


def _interaction_unlocked(state: GameState, it: dict[str, Any]) -> tuple[bool, str | None]:
    if state.flags.get("chapter_complete"):
        return False, "章节已结束"
    inv = _inv(state)
    if int(inv.get("remaining_turns", 0)) <= 0:
        return False, "回合已用尽"
    discovered = set(get_discovered_clues(state))
    for cid in it.get("requires_clues") or []:
        if cid not in discovered:
            label = next((c["label"] for c in BOARD_CLUES if c["id"] == cid), cid)
            return False, f"需要先获得线索：{label}"
    min_clues = int(it.get("min_clues", 0))
    if min_clues > 0 and _clue_count(inv) < min_clues:
        return False, f"需要至少 {min_clues} 条关键线索（当前 {_clue_count(inv)}）"
    for key, need in (it.get("min_trust") or {}).items():
        if _trust_value(inv, key) < int(need):
            names = {"thomas_trust": "托马斯信任", "elena_trust": "艾琳娜信任", "mira_trust": "米拉信任"}
            return False, f"需要更高{names.get(key, key)}"
    if int(inv.get("stamina", 0)) <= 0 and it.get("id") == "int_gate_mud":
        return False, "体力不足"
    return True, None


def _is_new_interaction(state: GameState, it: dict[str, Any]) -> bool:
    seen = set(_inv(state).get("seen_interactions") or [])
    return it["id"] not in seen


def build_investigation_board(state: GameState) -> dict[str, Any]:
    """持久调查板：实体常驻，交互列表随知识解锁。"""
    inv = _inv(state)
    entities_out: list[dict[str, Any]] = []
    for ent in ENTITIES:
        interactions: list[dict[str, Any]] = []
        for it in INTERACTIONS:
            if it.get("entity_id") != ent["id"]:
                continue
            unlocked, lock_reason = _interaction_unlocked(state, it)
            interactions.append(
                {
                    "id": it["id"],
                    "label": f"[{it.get('skill', '行动')}] {it['label']}",
                    "short_label": it["label"],
                    "category": it.get("category", "investigate"),
                    "entity_id": ent["id"],
                    "unlocked": unlocked,
                    "locked": not unlocked,
                    "lock_reason": lock_reason,
                    "is_new": unlocked and _is_new_interaction(state, it),
                    "intent": {
                        "target": it["id"],
                        "entity_id": ent["id"],
                        "action_type": it.get("category", "investigate"),
                    },
                }
            )
        entities_out.append(
            {
                **ent,
                "interaction_count": len(interactions),
                "unlocked_count": sum(1 for x in interactions if x["unlocked"]),
                "interactions": interactions,
            }
        )
    return {
        "entities": entities_out,
        "category_labels": CATEGORY_LABELS,
        "mode": "persistent_board",
    }


def board_clues_for_ui(state: GameState) -> list[dict[str, Any]]:
    discovered = set(get_discovered_clues(state))
    clues = BOARD_CLUES if BOARD_CLUES else KEY_CLUES
    return [{"id": c["id"], "label": c["label"], "found": c["id"] in discovered} for c in clues]


def get_board_guidance(state: GameState) -> str:
    if state.flags.get("chapter_complete"):
        return ""
    inv = _inv(state)
    remaining = int(inv.get("remaining_turns", 0))
    clues = _clue_count(inv)
    if remaining <= 0:
        return "回合已用尽，结局即将揭晓。"
    if clues >= 3:
        return "左侧点击人物或地点继续调查；线索足够后可从「黑森林入口」深入追踪。"
    return (
        f"世界持续存在：可反复访问左侧实体（剩余 {remaining} 回合）。"
        f"新对话随线索与信任解锁（当前线索 {clues} 条）。"
    )


def resolve_board_interaction(
    state: GameState,
    interaction_id: str,
    *,
    succeeded: bool,
    player_label: str = "",
    turn: int = 0,
) -> dict[str, Any]:
    it = _interaction_def(interaction_id)
    if not it:
        return {
            "narrative": "<p class=\"scene\">你无法执行该行动。</p>",
            "changes": {},
            "ending_id": None,
        }
    unlocked, reason = _interaction_unlocked(state, it)
    if not unlocked:
        return {
            "narrative": f"<p class=\"result\">{reason or '条件尚未满足'}。</p>",
            "changes": {},
            "ending_id": None,
        }

    inv = _inv(state)
    ent = _entity_def(str(it.get("entity_id", "")))
    if ent and ent.get("location"):
        state.location = str(ent["location"])

    seen = inv.setdefault("seen_interactions", [])
    if interaction_id not in seen:
        seen.append(interaction_id)

    clue_id = it.get("clue_id")
    already_has_clue = clue_id and clue_id in (inv.get("discovered_clues") or [])

    parts: list[str] = [
        f'<p class="player-action">你对<strong>{ent["name"] if ent else "此处"}</strong>：'
        f'「{player_label or it["label"]}」</p>'
    ]

    forest = interaction_id == "int_forest_enter"
    if forest:
        clues_n = _clue_count(inv)
        if clues_n < 3:
            ending_id = evaluate_ending(state, forest_attempt=True)
            assert ending_id
            parts.append(
                it.get("fail_narrative")
                or "<p class=\"result\">线索不足，你在林中迷失了方向。</p>"
            )
            parts.append(apply_ending(state, ending_id))
            inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
            return {
                "narrative": "\n".join(parts),
                "changes": {"investigation": dict(inv), "chapter_complete": True},
                "ending_id": ending_id,
            }
        _add_clue(inv, "clue_forest_trail")
        parts.append(it["success_narrative"])
        inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
        inv["crisis_pressure"] = min(100, int(inv.get("crisis_pressure", 0)) + PRESSURE_PER_TURN)
        ending_id = evaluate_ending(state, forest_attempt=True)
        if ending_id:
            parts.append(apply_ending(state, ending_id))
        return {
            "narrative": "\n".join(parts),
            "changes": {"investigation": dict(inv), "chapter_complete": bool(state.flags.get("chapter_complete"))},
            "ending_id": ending_id or state.flags.get("chapter_ending_id"),
        }

    inv["remaining_turns"] = max(0, int(inv.get("remaining_turns", 0)) - 1)
    inv["crisis_pressure"] = min(100, int(inv.get("crisis_pressure", 0)) + PRESSURE_PER_TURN)

    if succeeded:
        if already_has_clue and it.get("repeat_narrative"):
            parts.append(it["repeat_narrative"])
        else:
            parts.append(it["success_narrative"])
        _apply_delta(inv, it.get("on_success") or {})
    else:
        parts.append(it.get("fail_narrative") or "<p class=\"result\">这次没有进展。</p>")
        _apply_delta(inv, it.get("on_fail") or {})

    if int(inv.get("stamina", 0)) < 0:
        inv["stamina"] = 0

    log = inv.setdefault("choices_log", [])
    log.append(
        {
            "turn": turn,
            "label": player_label or it["label"],
            "entity": ent["name"] if ent else "",
            "success": succeeded,
            "clues_after": _clue_count(inv),
        }
    )

    from engine.investigation_mode import _sync_npc_attitudes_from_investigation

    _sync_npc_attitudes_from_investigation(state)

    ending_id = evaluate_ending(state)
    if ending_id:
        parts.append(apply_ending(state, ending_id))

    if int(inv.get("crisis_pressure", 0)) >= 70 and not state.flags.get("chapter_complete"):
        parts.append('<p class="world">远处传来急促的哨声，黑森林里的局势正在恶化。</p>')
    elif int(inv.get("remaining_turns", 0)) <= 1 and not state.flags.get("chapter_complete"):
        parts.append('<p class="scene">时间所剩无几，你必须做出抉择。</p>')

    return {
        "narrative": "\n".join(parts),
        "changes": {
            "investigation": dict(inv),
            "check_succeeded": succeeded,
            "chapter_complete": bool(state.flags.get("chapter_complete")),
        },
        "ending_id": ending_id or state.flags.get("chapter_ending_id"),
    }


def interaction_requires_roll(interaction_id: str) -> tuple[str, int, bool]:
    it = _interaction_def(interaction_id)
    if not it:
        return "WIS", 12, True
    if it.get("requires_roll") is False:
        return str(it.get("ability", "WIS")), 0, False
    return str(it.get("ability", "WIS")), int(it.get("dc", 12)), True


def resolve_board_action_id(
    *,
    action_id: str | None = None,
    intent_payload: dict[str, Any] | None = None,
    player_text: str = "",
) -> str | None:
    if action_id and str(action_id).startswith("int_"):
        return str(action_id)
    if isinstance(intent_payload, dict):
        target = intent_payload.get("target")
        if target and str(target).startswith("int_"):
            return str(target)
    text = (player_text or "").strip()
    if not text:
        return None
    for it in INTERACTIONS:
        label = str(it.get("label") or "")
        if label and label in text:
            return str(it["id"])
    return None

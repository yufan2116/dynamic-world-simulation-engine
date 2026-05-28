"""动态行动生成 — 由世界状态驱动，非 hardcode 列表。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.crisis_escalation import get_crisis_ui
from engine.rumor_network import rumors_at_location
from engine.world_state import GameState
from engine.world_templates import location_connections_for_state

CATEGORIES = ("investigate", "social", "stealth", "survival", "free")
CATEGORY_LABELS = {
    "investigate": "调查",
    "social": "社交",
    "stealth": "潜行",
    "survival": "生存",
    "free": "自由行动",
}


class DynamicAction(BaseModel):
    id: str
    label: str
    input: str
    category: str
    description: str = ""
    unlocked: bool = True
    lock_reason: str | None = None
    tags: list[str] = Field(default_factory=list)


def _is_night(state: GameState) -> bool:
    return state.time_of_day in ("凌晨", "深夜")


def _is_stormy(state: GameState) -> bool:
    return state.weather in ("暴雨", "暴雨初歇", "阴云", "浓雾")


def _player_mod(state: GameState, ability: str) -> int:
    return state.player.get_modifier(ability)


def _crisis(state: GameState) -> dict[str, Any]:
    return get_crisis_ui(state)


def _has_clue(state: GameState, key: str) -> bool:
    return bool(state.flags.get(key))


def _npc_here(state: GameState, name: str):
    for n in state.npc_at_location():
        if n.name == name:
            return n
    return None


def _add(
    bucket: dict[str, list[DynamicAction]],
    action: DynamicAction,
) -> None:
    cat = action.category if action.category in CATEGORIES else "investigate"
    if action.id not in {a.id for a in bucket.get(cat, [])}:
        bucket.setdefault(cat, []).append(action)


def _move_label(state: GameState, dest: str) -> str:
    if _is_night(state):
        return f"趁夜色潜行前往{dest}"
    if _is_stormy(state):
        return f"冒雨赶往{dest}"
    if state.time_of_day == "正午":
        return f"在日光下步行至{dest}"
    return f"沿小路前往{dest}"


def generate_actions(state: GameState) -> dict[str, Any]:
    """根据完整世界状态生成分组行动。"""
    loc = state.location
    crisis = _crisis(state)
    player = state.player
    wis_mod = _player_mod(state, "WIS")
    cha_mod = _player_mod(state, "CHA")
    dex_mod = _player_mod(state, "DEX")
    night = _is_night(state)
    storm = _is_stormy(state)

    buckets: dict[str, list[DynamicAction]] = {c: [] for c in CATEGORIES}

    # --- 调查 ---
    obs_desc = "留意脚印、血迹与异常声响"
    if storm:
        obs_desc = "雨声掩盖了很多声音，但仍可寻找被冲乱的新痕迹"
    if night:
        obs_desc = "夜色中细节难辨，需格外专注"
    _add(
        buckets,
        DynamicAction(
            id=f"observe_{loc}",
            label=f"仔细观察{loc}周围的环境",
            input=f"仔细观察{loc}周围的环境",
            category="investigate",
            description=obs_desc,
            tags=["perception"],
        ),
    )

    if wis_mod >= 2 and not _has_clue(state, "clue_found"):
        _add(
            buckets,
            DynamicAction(
                id="keen_sense",
                label="屏息凝神，搜寻被忽略的细节",
                input="屏息凝神搜寻环境中的隐藏细节",
                category="investigate",
                description=f"高感知（WIS {player.wisdom}）让你更易发现蛛丝马迹",
                tags=["wis", "unlock"],
            ),
        )

    clues = crisis.get("suspicious_clues") or []
    for i, clue in enumerate(clues[-2:]):
        _add(
            buckets,
            DynamicAction(
                id=f"follow_clue_{i}",
                label=f"追查线索：{clue[:18]}…" if len(clue) > 18 else f"追查线索：{clue}",
                input=f"追查线索：{clue}",
                category="investigate",
                description="已掌握的疑点值得进一步验证",
                tags=["clue"],
            ),
        )

    if loc == "仓库" and not state.flags.get("warehouse_searched"):
        _add(
            buckets,
            DynamicAction(
                id="search_warehouse",
                label="翻查货箱与角落，寻找失踪者痕迹",
                input="搜查仓库中的货物与箱子",
                category="investigate",
                description="仓库与商人失踪直接相关",
            ),
        )

    if loc == "森林小路":
        if not state.flags.get("varick_revealed"):
            _add(
                buckets,
                DynamicAction(
                    id="track_forest",
                    label="沿泥泞小径追踪可疑足迹",
                    input="沿小路追踪可疑脚印",
                    category="investigate",
                    description="林间的足迹或许指向真相",
                    unlocked=_has_clue(state, "clue_found") or wis_mod >= 1,
                    lock_reason="尚无方向，需先在别处找到线索" if not (_has_clue(state, "clue_found") or wis_mod >= 1) else None,
                ),
            )
        else:
            _add(
                buckets,
                DynamicAction(
                    id="confront_varick",
                    label="直面瓦里克与其手下",
                    input="与瓦里克对峙",
                    category="investigate",
                    description="强盗现身，必须做出抉择",
                ),
            )

    if state.flags.get("plea_letter_found") and loc in ("森林小路", "仓库"):
        _add(
            buckets,
            DynamicAction(
                id="follow_plea_letter",
                label="按求救信残页指示的方向搜索",
                input="调查求救信提到的方向",
                category="investigate",
                description="残页上的字迹或许指向马库斯",
            ),
        )

    if crisis.get("recent_anomalies"):
        anomaly = crisis["recent_anomalies"][-1]
        _add(
            buckets,
            DynamicAction(
                id="probe_anomaly",
                label="调查最近的异常动静",
                input=f"调查异常：{anomaly[:24]}",
                category="investigate",
                description="世界简报提到的异象值得查访",
                tags=["world_event"],
            ),
        )

    # --- 社交 ---
    if state.flags.get("opening_scene") and loc == "村口":
        _add(
            buckets,
            DynamicAction(
                id="talk_elena_opening",
                label="上前安慰冲进广场的艾琳娜，询问细节",
                input="安慰艾琳娜并询问商人失踪的细节",
                category="social",
                description="她刚刚哭喊着冲进来，或许知道关键细节",
                tags=["opening"],
            ),
        )

    for npc in state.npc_at_location():
        att = npc.attitude_value
        if att >= 20:
            tone = "友好地"
            desc = f"{npc.name}对你态度尚可（{npc.attitude}）"
        elif att <= -20:
            tone = "谨慎地"
            desc = f"{npc.name}对你保持警惕（{npc.attitude}）"
        else:
            tone = ""
            desc = f"{npc.name}态度{npc.attitude}"

        if npc.name == "艾琳娜":
            label = f"{tone}安慰艾琳娜，询问她父亲失踪的细节".strip()
            inp = "安慰艾琳娜并询问商人失踪的细节"
        elif npc.name == "托马斯":
            label = f"{tone}向托马斯打听昨夜异常情况".strip()
            inp = "向托马斯打听昨夜异常情况"
        elif npc.name == "米拉":
            label = f"{tone}与米拉交谈，探听酒馆里的消息".strip()
            inp = "与米拉交谈"
        elif npc.name == "瓦里克":
            label = "与瓦里克交涉，试探其底线"
            inp = "与瓦里克对话"
        else:
            label = f"{tone}与{npc.name}交谈".strip()
            inp = f"与{npc.name}交谈"

        _add(
            buckets,
            DynamicAction(
                id=f"talk_{npc.name}",
                label=label,
                input=inp,
                category="social",
                description=desc,
            ),
        )

        if cha_mod >= 2 and att < 20:
            _add(
                buckets,
                DynamicAction(
                    id=f"persuade_{npc.name}",
                    label=f"尝试说服{npc.name}透露更多内情",
                    input=f"说服{npc.name}告诉我所知的一切",
                    category="social",
                    description=f"魅力（CHA {player.charisma}）或可打开局面",
                    unlocked=att > -40,
                    lock_reason=f"{npc.name}对你过于敌意，难以说服" if att <= -40 else None,
                    tags=["cha", "unlock"],
                ),
            )

    for rumor in rumors_at_location(state, loc)[-2:]:
        rid = rumor.get("id", rumor.get("text", "")[:8])
        _add(
            buckets,
            DynamicAction(
                id=f"rumor_{rid}",
                label=f"向在场者打听：「{rumor['text'][:22]}…」",
                input=f"向路人打听传闻：{rumor['text']}",
                category="social",
                description="本地流传的消息或许并非空穴来风",
                tags=["rumor"],
            ),
        )

    if loc == "村口" and not state.npc_at_location() and crisis.get("pressure", 0) > 30:
        _add(
            buckets,
            DynamicAction(
                id="ask_villagers",
                label="拦住村民，询问他们对失踪案的看法",
                input="询问村民关于商人失踪的传闻",
                category="social",
                description="恐慌蔓延，人们或许知道些什么",
            ),
        )

    # --- 潜行 ---
    if _npc_here(state, "托马斯") and loc in ("村口", "仓库"):
        _add(
            buckets,
            DynamicAction(
                id="eavesdrop_guards",
                label="隐蔽起来，偷听守卫的私下谈话",
                input="偷听守卫谈话",
                category="stealth",
                description="守卫或许知道未公开的内情",
                unlocked=night or dex_mod >= 2,
                lock_reason="白天难以不被发现，需更高敏捷或等待夜晚" if not (night or dex_mod >= 2) else None,
                tags=["dex", "night", "unlock"],
            ),
        )

    if loc == "酒馆" and (night or cha_mod >= 1):
        _add(
            buckets,
            DynamicAction(
                id="pretend_drunk",
                label="假装喝醉，接近谈话的人群",
                input="我假装喝醉接近守卫",
                category="stealth",
                description="酒馆的喧嚣是天然的掩护",
                tags=["cha", "roleplay"],
            ),
        )

    if loc != "森林小路" and night and not state.flags.get("bandit_raid"):
        dest = "仓库" if loc != "仓库" else "酒馆"
        if dest in location_connections_for_state(state).get(loc, []):
            _add(
                buckets,
                DynamicAction(
                    id=f"sneak_{dest}",
                    label=f"借夜色掩护，悄悄摸向{dest}",
                    input=f"悄悄前往{dest}",
                    category="stealth",
                    description="避开耳目，不惊动任何人",
                    unlocked=dex_mod >= 1,
                    lock_reason="敏捷不足，难以无声移动" if dex_mod < 1 else None,
                    tags=["dex", "unlock"],
                ),
            )

    if crisis.get("pressure", 0) > 50 and loc == "仓库":
        _add(
            buckets,
            DynamicAction(
                id="hide_among_crates",
                label="躲进货箱阴影，观察来者",
                input="躲进货箱后观察仓库动静",
                category="stealth",
                description="危机加剧，暗中观察或许更安全",
            ),
        )

    # --- 生存 / 移动 ---
    for dest in location_connections_for_state(state).get(loc, []):
        if dest == loc:
            continue
        danger_note = ""
        if dest == "森林小路" and crisis.get("pressure", 0) > 45:
            danger_note = " · 森林方向风险升高"
        _add(
            buckets,
            DynamicAction(
                id=f"move_{loc}_{dest}",
                label=_move_label(state, dest),
                input=f"前往{dest}",
                category="survival",
                description=f"从{loc}出发{dest}{danger_note}",
                tags=["move"],
            ),
        )

    rest_label = "在原地休整，恢复体力"
    rest_desc = "时间仍会流逝，世界不会停下"
    if night:
        rest_label = "找避风处过夜，等待黎明"
        rest_desc = "漫长的一夜可能发生许多事"
    elif crisis.get("pressure", 0) > 55:
        rest_desc = "危机正在恶化——拖延可能让局面更糟"
    _add(
        buckets,
        DynamicAction(
            id="rest",
            label=rest_label,
            input="在原地休整片刻" if not night else "在此过夜休息",
            category="survival",
            description=rest_desc,
            tags=["rest"],
        ),
    )

    if player.class_name in ("骑士", "游侠") and loc == "村口":
        _add(
            buckets,
            DynamicAction(
                id="scout_perimeter",
                label="沿村界巡逻一圈，标记异常",
                input="沿村庄四周观察环境与脚印",
                category="survival",
                description=f"{player.class_name}的素养适合系统性侦察",
                tags=["class"],
            ),
        )

    if storm and loc != "酒馆":
        _add(
            buckets,
            DynamicAction(
                id="seek_shelter",
                label="寻找可避雨的遮蔽处等待天气好转",
                input="寻找遮蔽处等待天气好转",
                category="survival",
                description="恶劣天气下贸然行动风险更高",
            ),
        )

    # --- 自由行动 ---
    _add(
        buckets,
        DynamicAction(
            id="free_input",
            label="自由描述你想做的事…",
            input="",
            category="free",
            description="例如：「我假装喝醉接近守卫」「用军徽换取托马斯的信任」",
            tags=["custom"],
        ),
    )

    # 限制每组数量，优先已解锁
    grouped: dict[str, list[dict[str, Any]]] = {}
    flat: list[str] = []
    for cat in CATEGORIES:
        actions = buckets.get(cat, [])
        unlocked_first = sorted(actions, key=lambda a: (not a.unlocked, a.label))
        trimmed = unlocked_first[:5] if cat != "free" else unlocked_first[:1]
        grouped[cat] = [a.model_dump() for a in trimmed]
        for a in trimmed:
            if a.unlocked and a.input and a.category != "free":
                flat.append(a.input)

    return {
        "grouped": grouped,
        "category_labels": CATEGORY_LABELS,
        "flat_inputs": flat[:8],
    }


def generate_options(state: GameState) -> list[str]:
    """兼容旧接口：返回可执行 input 字符串列表。"""
    data = generate_actions(state)
    return data["flat_inputs"] or ["仔细观察周围环境"]

"""世界状态与玩家模型，含失踪商人剧本初始状态。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def ability_modifier(score: int) -> int:
    """D&D 5e 属性调整值。"""
    return (score - 10) // 2


class Player(BaseModel):
    name: str = "无名冒险者"
    class_name: str = "游侠"
    background: str = "流浪调查员"
    strength: int = Field(14, serialization_alias="STR")
    dexterity: int = Field(12, serialization_alias="DEX")
    constitution: int = Field(13, serialization_alias="CON")
    intelligence: int = Field(11, serialization_alias="INT")
    wisdom: int = Field(13, serialization_alias="WIS")
    charisma: int = Field(10, serialization_alias="CHA")
    equipment: list[str] = Field(default_factory=lambda: ["短剑", "皮甲", "火把", "调查笔记"])
    portrait_url: str | None = None
    portrait_asset_key: str | None = None

    model_config = {"populate_by_name": True}

    def get_modifier(self, ability: str) -> int:
        mapping = {
            "STR": self.strength,
            "DEX": self.dexterity,
            "CON": self.constitution,
            "INT": self.intelligence,
            "WIS": self.wisdom,
            "CHA": self.charisma,
        }
        return ability_modifier(mapping.get(ability.upper(), 10))


class NPCState(BaseModel):
    name: str
    location: str
    attitude: str
    attitude_value: int = 0  # -100 ~ 100
    memories: list[str] = Field(default_factory=list)
    present: bool = True
    asset_key: str | None = None


class QuestState(BaseModel):
    id: str
    title: str
    description: str
    status: str = "active"  # active | completed | failed
    objectives: list[str] = Field(default_factory=list)


class GameState(BaseModel):
    location: str = "村口"
    location_asset_key: str | None = None
    time_of_day: str = "清晨"
    day: int = 1
    weather: str = "薄雾"
    active_npcs: list[str] = Field(default_factory=list)
    npcs: dict[str, NPCState] = Field(default_factory=dict)
    quests: list[QuestState] = Field(default_factory=list)
    faction_reputation: dict[str, int] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    player: Player = Field(default_factory=Player)

    def npc_at_location(self) -> list[NPCState]:
        return [n for n in self.npcs.values() if n.location == self.location and n.present]


def ensure_player_known_facts(state: GameState) -> dict[str, Any]:
    """初始化/修复 player_known_facts。"""
    raw = state.flags.get("player_known_facts")
    if not isinstance(raw, dict):
        raw = {}
    defaults: dict[str, Any] = {
        "known_locations": [],
        "known_npcs": [],
        "known_objects": [],
        # known_rumors: list[dict]（来源可追溯）；兼容旧 list[str]
        "known_rumors": [],
        # 内部事实：系统知道，可用于模拟/决策，但不允许直接展示
        "internal_facts": [],
        # 玩家可见事实：必须已在 narrative 中明确写出 / 玩家行动发现 / NPC 明确说出
        "player_facing_facts": [],
        # 兼容：旧 known_facts 迁移到 internal_facts
        "known_facts": [],
        # 兼容：旧 known_clues 迁移到 internal_facts
        "known_clues": [],
    }
    for k, v in defaults.items():
        if k not in raw:
            raw[k] = [] if isinstance(v, list) else v
        if isinstance(v, list) and not isinstance(raw.get(k), list):
            raw[k] = []
    # 兼容：旧 known_rumors 可能是 list[str]
    if raw.get("known_rumors") and all(isinstance(x, str) for x in raw.get("known_rumors", [])):
        raw["known_rumors"] = [
            {
                "id": f"legacy_{i}",
                "text": str(t),
                "source_label": "未知来源",
                "heard_at_turn": int(state.flags.get("last_turn", 1) or 1),
                "heard_at_location": str(state.location),
            }
            for i, t in enumerate(raw.get("known_rumors", []))
        ]
    # 兼容：旧 known_facts 可能为空或类型不对
    if not isinstance(raw.get("known_facts"), list):
        raw["known_facts"] = []
    if not isinstance(raw.get("internal_facts"), list):
        raw["internal_facts"] = []
    if not isinstance(raw.get("player_facing_facts"), list):
        raw["player_facing_facts"] = []

    # 迁移：known_facts(list[dict]) → internal_facts（避免旧逻辑直接让其进入选项）
    if isinstance(raw.get("known_facts"), list) and raw.get("known_facts"):
        for f in list(raw.get("known_facts", [])):
            if isinstance(f, dict) and f.get("id"):
                if not any(isinstance(x, dict) and x.get("id") == f.get("id") for x in raw["internal_facts"]):
                    raw["internal_facts"].append(f)
        raw["known_facts"] = []
    # 迁移：known_clues(list[str]) → known_facts(list[dict])（保留但不再依赖 known_clues）
    if isinstance(raw.get("known_clues"), list) and raw.get("known_clues"):
        for i, clue in enumerate(list(raw.get("known_clues", []))):
            if not isinstance(clue, str) or not clue.strip():
                continue
            cid = f"legacy_clue_{abs(hash(clue))%100000}_{i}"
            if any(isinstance(x, dict) and x.get("label") == clue for x in raw["internal_facts"]):
                continue
            raw["internal_facts"].append(
                {
                    "id": cid,
                    "type": "clue",
                    "label": clue.strip(),
                    "visibility": "hidden",
                    "source": "legacy",
                    "source_label": "历史线索",
                    "discovered_turn": int(state.flags.get("last_turn", 1) or 1),
                    "discovered_at": str(state.location),
                    "description": "从旧存档迁移的线索记录。",
                }
            )
        raw["known_clues"] = []
    # 起始：当前地点、当前可见 NPC 默认为已知
    loc = str(state.location)
    if loc and loc not in raw["known_locations"]:
        raw["known_locations"].append(loc)
    for npc in state.npc_at_location():
        if npc.name not in raw["known_npcs"]:
            raw["known_npcs"].append(npc.name)
    state.flags["player_known_facts"] = raw
    return raw


# 兼容旧导入；新代码请使用 world_templates.get_locations_for_template
LOCATIONS = ["村口", "酒馆", "仓库", "森林小路"]

LOCATION_CONNECTIONS: dict[str, list[str]] = {
    "村口": ["酒馆", "仓库"],
    "酒馆": ["村口", "仓库", "森林小路"],
    "仓库": ["村口", "酒馆"],
    "森林小路": ["酒馆"],
}

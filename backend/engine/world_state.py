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


# 兼容旧导入；新代码请使用 world_templates.get_locations_for_template
LOCATIONS = ["村口", "酒馆", "仓库", "森林小路"]

LOCATION_CONNECTIONS: dict[str, list[str]] = {
    "村口": ["酒馆", "仓库"],
    "酒馆": ["村口", "仓库", "森林小路"],
    "仓库": ["村口", "酒馆"],
    "森林小路": ["酒馆"],
}

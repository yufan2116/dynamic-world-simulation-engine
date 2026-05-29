"""演示种子加载 — 从 data/seeds/<name>/ 构建稳定初始 GameState。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.world_state import GameState, NPCState, Player, QuestState
from engine.world_templates import build_image_entity_registry

SEEDS_ROOT = Path(__file__).resolve().parent.parent / "data" / "seeds"

_SEED_FILES = (
    "world.json",
    "locations.json",
    "npcs.json",
    "factions.json",
    "quests.json",
    "rumors.json",
    "crisis.json",
    "player.json",
    "opening_events.json",
)


def list_seeds() -> list[str]:
    if not SEEDS_ROOT.is_dir():
        return []
    return sorted(
        p.name
        for p in SEEDS_ROOT.iterdir()
        if p.is_dir() and (p / "world.json").is_file()
    )


def _load_json(seed_dir: Path, filename: str) -> dict[str, Any]:
    path = seed_dir / filename
    if not path.is_file():
        raise FileNotFoundError(f"种子缺少文件: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"种子 {filename} 须为 JSON 对象")
    return data


def load_seed_bundle(seed_name: str) -> dict[str, Any]:
    """加载种子目录下全部 JSON（供调试或 API 元数据）。"""
    seed_dir = SEEDS_ROOT / seed_name
    if not seed_dir.is_dir():
        raise KeyError(f"未知种子: {seed_name}")
    return {name: _load_json(seed_dir, name) for name in _SEED_FILES}


def get_opening_events(seed_name: str) -> list[dict[str, Any]]:
    bundle = load_seed_bundle(seed_name)
    raw = bundle.get("opening_events.json") or {}
    events = raw.get("events")
    return events if isinstance(events, list) else []


def load_seed_world(seed_name: str) -> GameState:
    """
    从种子构建 GameState。

    仅负责初始世界快照；不包含固定 Day N 剧情。
    后续由 world_tick / npc_ai / rumor_network / faction_sim / crisis_escalation 推进。
    """
    bundle = load_seed_bundle(seed_name)
    world = bundle["world.json"]
    locations = bundle["locations.json"]
    npcs_data = bundle["npcs.json"]
    factions_data = bundle["factions.json"]
    quests_data = bundle["quests.json"]
    rumors_data = bundle["rumors.json"]
    crisis_data = bundle["crisis.json"]
    player_data = bundle["player.json"]

    from engine.world_template_manager import resolve_template_id

    template_id = resolve_template_id(world.get("template_id", "medieval_dark_fantasy"))
    default_loc = world.get("default_location", "村口")

    npcs: dict[str, NPCState] = {}
    profiles: dict[str, dict[str, Any]] = {}
    current_actions: dict[str, str] = {}

    for entry in npcs_data.get("npcs", []):
        name = entry["name"]
        npcs[name] = NPCState(
            name=name,
            location=entry.get("location", default_loc),
            attitude=entry.get("attitude", "中立"),
            attitude_value=int(entry.get("attitude_value", 0)),
            memories=list(entry.get("memories", [])),
            present=bool(entry.get("present", True)),
        )
        if entry.get("profile"):
            profiles[name] = dict(entry["profile"])
        if entry.get("current_action"):
            current_actions[name] = str(entry["current_action"])

    active = [n for n, npc in npcs.items() if npc.present and npc.location == world.get("default_location", default_loc)]
    if world.get("scene_npcs"):
        active = list(world["scene_npcs"])

    crisis_flags = crisis_data.get("flags") or {}
    seed_flags: dict[str, Any] = {
        "seed_id": world.get("seed_id", seed_name),
        "seed_loaded": True,
        "template_id": template_id,
        "village_name": world.get("village_name", "Ravenford"),
        "background_urls": {},
        "npc_portraits": {},
        "world_minutes": int(world.get("world_minutes", 480)),
        "clock": world.get("clock", "08:00"),
        "village_panic": int(world.get("village_panic", 35)),
        "danger_level": world.get("danger_level", "中"),
        "war_risk": int(world.get("war_risk", 25)),
        "opening_scene": bool(world.get("opening_scene", True)),
        "scene_npcs": world.get("scene_npcs", active),
        "rumors": list(rumors_data.get("rumors", [])),
        "factions": dict(factions_data.get("factions", {})),
        "faction_relations": {
            k: v.get("relation_to_player")
            for k, v in factions_data.get("factions", {}).items()
            if isinstance(v, dict) and v.get("relation_to_player")
        },
        "npc_profiles": profiles,
        "npc_current_actions": current_actions,
        "seed_locations": locations.get("locations", []),
        "seed_location_connections": locations.get("connections", {}),
        "seed_world_background": world.get("background", ""),
        "seed_chapter": world.get("chapter", {}),
        "vertical_slice_demo": bool(world.get("vertical_slice_demo", seed_name == "ravenford_demo")),
        "slice_routes": {"thomas": 0, "mira": 0, "elena": 0},
        "slice_choices": [],
        "economy": {},
        "crisis": dict(crisis_data.get("crisis", {})),
        "last_simulated_at": None,
        **crisis_flags,
    }

    quests = [
        QuestState(
            id=q["id"],
            title=q["title"],
            description=q["description"],
            status=q.get("status", "active"),
            objectives=list(q.get("objectives", [])),
        )
        for q in quests_data.get("quests", [])
    ]

    player = Player(
        name=player_data.get("name", "凯尔"),
        class_name=player_data.get("class_name", "骑士"),
        background=player_data.get("background", ""),
        strength=int(player_data.get("strength", 14)),
        dexterity=int(player_data.get("dexterity", 12)),
        constitution=int(player_data.get("constitution", 13)),
        intelligence=int(player_data.get("intelligence", 11)),
        wisdom=int(player_data.get("wisdom", 13)),
        charisma=int(player_data.get("charisma", 10)),
        equipment=list(player_data.get("equipment", [])),
    )

    state = GameState(
        location=default_loc,
        time_of_day=world.get("time_of_day", "清晨"),
        day=int(world.get("day", 1)),
        weather=world.get("weather", "薄雾"),
        active_npcs=active,
        npcs=npcs,
        quests=quests,
        faction_reputation=dict(factions_data.get("faction_reputation", {})),
        flags=seed_flags,
        player=player,
    )

    from engine.world_ontology import attach_ontology_to_state, init_economy_from_ontology

    if not state.flags.get("economy"):
        init_economy_from_ontology(state)
    attach_ontology_to_state(state)
    state.flags["image_entities"] = build_image_entity_registry(template_id, state)
    return state

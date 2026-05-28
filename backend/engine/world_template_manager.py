"""世界模板管理器 — 从 data/world_templates/<id>/ 加载完整世界包。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.world_state import GameState, NPCState, Player, QuestState

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "data" / "world_templates"
DEFAULT_TEMPLATE_ID = "medieval_dark_fantasy"

TEMPLATE_ALIASES: dict[str, str] = {
    "missing_merchant_medieval": "medieval_dark_fantasy",
    "xianxia_forbidden": "xianxia_forbidden_land",
}

TEMPLATE_FILES = (
    "world.json",
    "locations.json",
    "npcs.json",
    "factions.json",
    "rumors.json",
    "crisis.json",
    "art_style.json",
    "narrative_style.json",
    "world_terms.json",
)


def resolve_template_id(template_id: str | None) -> str:
    tid = (template_id or DEFAULT_TEMPLATE_ID).strip()
    return TEMPLATE_ALIASES.get(tid, tid)


def _template_dir(template_id: str) -> Path:
    tid = resolve_template_id(template_id)
    path = TEMPLATE_ROOT / tid
    if not path.is_dir() or not (path / "world.json").is_file():
        raise KeyError(f"未知世界模板: {template_id} (resolved: {tid})")
    return path


def _load_json_file(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 须为 JSON 对象")
    return data


def load_world_template(template_id: str | None) -> dict[str, Any]:
    """
    加载完整世界模板包。

    返回 seed_data, art_style, narrative_style, ui_theme, scene_defaults 及元数据。
    """
    tid = resolve_template_id(template_id)
    tdir = _template_dir(tid)
    bundle = {name: _load_json_file(tdir / name) for name in TEMPLATE_FILES}

    world = bundle["world.json"]
    locations = bundle["locations.json"]
    loc_list = locations.get("locations", [])
    connections = locations.get("connections", {})

    scene_defaults: dict[str, dict[str, Any]] = {}
    for loc in loc_list:
        name = loc.get("name")
        if not name:
            continue
        scene_defaults[name] = {
            "lighting": loc.get("lighting", ""),
            "soundscape": list(loc.get("soundscape", [])),
            "interactive_objects": list(loc.get("interactive_objects", [])),
            "danger": loc.get("danger", ""),
            "spiritual_pressure": loc.get("spiritual_pressure"),
            "visual_tags": list(loc.get("visual_tags", [])),
            "player_position": loc.get("player_position", f"{name}入口"),
            "npc_positions": dict(loc.get("npc_positions", {})),
        }

    art = bundle["art_style.json"]
    narrative = bundle["narrative_style.json"]
    ui_theme = art.get("ui_theme") or world.get("ui_theme") or {}

    seed_data = {
        "template_id": tid,
        "world": world,
        "locations": loc_list,
        "connections": connections,
        "npcs": bundle["npcs.json"].get("npcs", []),
        "factions": bundle["factions.json"],
        "rumors": bundle["rumors.json"].get("rumors", []),
        "crisis": bundle["crisis.json"],
        "quests": world.get("quests", []),
        "player": world.get("player", {}),
    }

    world_terms = bundle.get("world_terms.json", {})

    return {
        "template_id": tid,
        "name": world.get("name", tid),
        "world_terms": world_terms,
        "chapter_title": world.get("chapter_title", "第一章"),
        "default_location": world.get("default_location", ""),
        "seed_data": seed_data,
        "art_style": art,
        "narrative_style": narrative,
        "ui_theme": ui_theme,
        "scene_defaults": scene_defaults,
        "locations_meta": {loc["name"]: loc for loc in loc_list if loc.get("name")},
        "npc_visual": bundle["npcs.json"].get("visual", []),
    }


@lru_cache(maxsize=8)
def _cached_bundle(template_id: str) -> dict[str, Any]:
    return load_world_template(template_id)


def list_templates() -> list[dict[str, Any]]:
    if not TEMPLATE_ROOT.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(TEMPLATE_ROOT.iterdir()):
        if not path.is_dir() or not (path / "world.json").is_file():
            continue
        try:
            bundle = load_world_template(path.name)
            art = bundle["art_style"]
            ui = bundle.get("ui_theme") or {}
            terms = bundle.get("world_terms") or {}
            ui_block = terms.get("ui") or {}
            out.append(
                {
                    "id": bundle["template_id"],
                    "name": bundle["name"],
                    "art_style": art.get("prompt_suffix", art.get("base_style", "")),
                    "ui_theme": ui,
                    "world_ontology": {
                        "template_id": bundle["template_id"],
                        "core": terms.get("core", {}),
                        "ui": ui_block,
                    },
                }
            )
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
    return out


def get_art_style_prompt(template_id: str | None) -> str:
    bundle = _cached_bundle(resolve_template_id(template_id))
    art = bundle["art_style"]
    return str(art.get("base_style", art.get("prompt_suffix", "")))


def get_style_guardrail(template_id: str | None) -> str:
    bundle = _cached_bundle(resolve_template_id(template_id))
    return str(bundle["art_style"].get("guardrail", ""))


def get_narrative_style(template_id: str | None) -> dict[str, Any]:
    bundle = _cached_bundle(resolve_template_id(template_id))
    return dict(bundle["narrative_style"])


def get_scene_defaults(template_id: str | None) -> dict[str, dict[str, Any]]:
    bundle = _cached_bundle(resolve_template_id(template_id))
    return dict(bundle["scene_defaults"])


def get_locations_for_template(template_id: str | None) -> list[str]:
    bundle = _cached_bundle(resolve_template_id(template_id))
    return [loc["name"] for loc in bundle["seed_data"]["locations"] if loc.get("name")]


def get_location_connections(template_id: str | None) -> dict[str, list[str]]:
    bundle = _cached_bundle(resolve_template_id(template_id))
    raw = bundle["seed_data"].get("connections", {})
    return {k: list(v) for k, v in raw.items()}


def create_game_state_from_template(template_id: str | None = None) -> GameState:
    """从模板 JSON 构建初始 GameState（替代硬编码 seed）。"""
    bundle = load_world_template(template_id)
    seed = bundle["seed_data"]
    world = seed["world"]
    tid = seed["template_id"]
    default_loc = world.get("default_location", bundle["default_location"])

    npcs: dict[str, NPCState] = {}
    profiles: dict[str, dict[str, Any]] = {}
    current_actions: dict[str, str] = {}

    for entry in seed["npcs"]:
        name = entry["name"]
        npcs[name] = NPCState(
            name=name,
            location=entry.get("location", default_loc),
            attitude=entry.get("attitude", "中立"),
            attitude_value=int(entry.get("attitude_value", 0)),
            memories=list(entry.get("memories", [])),
            present=bool(entry.get("present", True)),
        )
        profile: dict[str, Any] = {}
        for key in (
            "cultivation_level",
            "sect",
            "dao_heart",
            "personality",
            "goal",
            "fear",
            "current_emotion",
            "role",
            "role_label",
        ):
            if entry.get(key) is not None:
                profile[key] = entry[key]
        if not profile.get("role_label") and entry.get("role"):
            role_labels = (bundle.get("world_terms") or {}).get("role_labels", {})
            profile["role_label"] = role_labels.get(
                str(entry["role"]), str(entry["role"])
            )
        if entry.get("profile"):
            profile.update(entry["profile"])
        if profile:
            profiles[name] = profile
        if entry.get("current_action"):
            current_actions[name] = str(entry["current_action"])

    active = [n for n, npc in npcs.items() if npc.present and npc.location == default_loc]
    if world.get("scene_npcs"):
        active = list(world["scene_npcs"])

    factions_data = seed["factions"]
    crisis_data = seed["crisis"]
    crisis_flags = crisis_data.get("flags") or {}

    flags: dict[str, Any] = {
        "template_id": tid,
        "world_name": world.get("world_name", world.get("village_name", "")),
        "village_name": world.get("village_name", world.get("world_name", "")),
        "background_urls": {},
        "npc_portraits": {},
        "world_minutes": int(world.get("world_minutes", 480)),
        "clock": world.get("clock", "08:00"),
        "village_panic": int(world.get("village_panic", world.get("tension", 35))),
        "danger_level": world.get("danger_level", "中"),
        "war_risk": int(world.get("war_risk", 25)),
        "opening_scene": bool(world.get("opening_scene", True)),
        "scene_npcs": world.get("scene_npcs", active),
        "rumors": list(seed["rumors"]),
        "factions": dict(factions_data.get("factions", {})),
        "faction_relations": {
            k: v.get("relation_to_player")
            for k, v in factions_data.get("factions", {}).items()
            if isinstance(v, dict) and v.get("relation_to_player")
        },
        "npc_profiles": profiles,
        "npc_current_actions": current_actions,
        "seed_locations": seed["locations"],
        "seed_location_connections": seed["connections"],
        "seed_world_background": world.get("background", ""),
        "economy": {},
        "crisis": dict(crisis_data.get("crisis", {})),
        "last_simulated_at": None,
        "ui_theme": bundle["ui_theme"],
        "narrative_style_id": tid,
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
        for q in seed.get("quests", [])
    ]

    player_raw = seed.get("player") or {}
    player = Player(
        name=player_raw.get("name", "旅人"),
        class_name=player_raw.get("class_name", "冒险者"),
        background=player_raw.get("background", ""),
        strength=int(player_raw.get("strength", 12)),
        dexterity=int(player_raw.get("dexterity", 12)),
        constitution=int(player_raw.get("constitution", 12)),
        intelligence=int(player_raw.get("intelligence", 11)),
        wisdom=int(player_raw.get("wisdom", 12)),
        charisma=int(player_raw.get("charisma", 10)),
        equipment=list(player_raw.get("equipment", [])),
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
        flags=flags,
        player=player,
    )
    from engine.world_templates import build_image_entity_registry

    from engine.world_ontology import attach_ontology_to_state, init_economy_from_ontology

    if not state.flags.get("economy"):
        init_economy_from_ontology(state)
    attach_ontology_to_state(state)
    state.flags["image_entities"] = build_image_entity_registry(tid, state)
    return state


def get_template_manifest(template_id: str | None) -> dict[str, Any]:
    """兼容旧 get_template() 调用 — 返回图像/章节元数据。"""
    bundle = _cached_bundle(resolve_template_id(template_id))
    world = bundle["seed_data"]["world"]
    art = bundle["art_style"]
    npcs_visual = []
    for entry in bundle["seed_data"]["npcs"]:
        vis = entry.get("visual") or {}
        npcs_visual.append(
            {
                "entity_id": vis.get("entity_id", f"npc:{entry['name']}"),
                "name": entry["name"],
                "role": entry.get("role", vis.get("role", "character")),
                "description": vis.get("description", entry.get("personality", "")),
                "image_prompt_override": vis.get("image_prompt_override"),
            }
        )
    locs_visual = []
    for loc in bundle["seed_data"]["locations"]:
        vis = loc.get("visual") or {}
        locs_visual.append(
            {
                "entity_id": vis.get("entity_id", f"loc:{loc['name']}"),
                "name": loc["name"],
                "description": vis.get("description", loc.get("description", "")),
                "image_prompt_override": vis.get("image_prompt_override"),
            }
        )
    return {
        "id": bundle["template_id"],
        "name": bundle["name"],
        "art_style": art.get("base_style", ""),
        "chapter_title": bundle["chapter_title"],
        "default_location": bundle["default_location"],
        "npcs": npcs_visual,
        "locations": locs_visual,
        "player_portrait_roles": art.get("player_portrait_roles", {}),
        "ui_theme": bundle["ui_theme"],
        "banner_motifs": art.get("banner_motifs", []),
    }

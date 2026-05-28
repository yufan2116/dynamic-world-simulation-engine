"""多世界模板 — 图像 prompt 与兼容层；数据来自 world_template_manager。"""
from __future__ import annotations

from typing import Any

from engine.world_state import GameState, Player
from engine.world_template_manager import (
    DEFAULT_TEMPLATE_ID,
    create_game_state_from_template,
    get_art_style_prompt,
    get_location_connections,
    get_locations_for_template,
    get_style_guardrail,
    get_template_manifest,
    list_templates,
    resolve_template_id,
)

__all__ = [
    "DEFAULT_TEMPLATE_ID",
    "list_templates",
    "get_template",
    "get_art_style",
    "finalize_image_prompt",
    "build_portrait_prompt",
    "build_background_prompt",
    "build_player_portrait_prompt",
    "build_image_entity_registry",
    "create_initial_game_state",
    "get_locations_for_template",
    "get_location_connections",
    "location_connections_for_state",
    "all_locations_for_state",
    "resolve_template_id",
]


def get_template(template_id: str | None) -> dict[str, Any]:
    return get_template_manifest(template_id)


def get_art_style(template_id: str | None) -> str:
    return get_art_style_prompt(template_id)


def finalize_image_prompt(prompt: str, template_id: str | None = None) -> str:
    base = prompt.strip().rstrip(".")
    guardrail = get_style_guardrail(template_id)
    return f"{base}. {guardrail}"


def build_portrait_prompt(npc: dict[str, Any], art_style: str, template_id: str | None = None) -> str:
    if npc.get("image_prompt_override"):
        body = npc["image_prompt_override"]
    else:
        role = npc.get("role", "character")
        desc = npc.get("description", "")
        body = f"Portrait of {role}, {desc}"
    return finalize_image_prompt(f"{body}, {art_style}, square format", template_id)


def build_background_prompt(loc: dict[str, Any], art_style: str, template_id: str | None = None) -> str:
    if loc.get("image_prompt_override"):
        body = loc["image_prompt_override"]
    else:
        name = loc.get("name", "location")
        desc = loc.get("description", "")
        body = f"Wide landscape of {name}, {desc}"
    return finalize_image_prompt(f"{body}, {art_style}, 16:9 wide composition", template_id)


def build_player_portrait_prompt(player: Player, template_id: str | None) -> str:
    tpl = get_template(template_id)
    art_style = tpl.get("art_style", "")
    roles: dict[str, Any] = tpl.get("player_portrait_roles", {})
    entry = roles.get(player.class_name)
    if not entry:
        for key, val in roles.items():
            if key in player.class_name:
                entry = val
                break
    if entry:
        role = entry.get("role", player.class_name)
        desc = entry.get("description", player.background)
        body = f"Portrait of {role}, {desc}"
    else:
        body = f"Portrait of {player.class_name}, {player.background}"
    return finalize_image_prompt(f"{body}, {art_style}, square format", template_id)


def build_image_entity_registry(template_id: str, state: GameState) -> dict[str, dict[str, Any]]:
    from engine.image_assets import hash_prompt

    tid = resolve_template_id(template_id)
    tpl = get_template(tid)
    registry: dict[str, dict[str, Any]] = {}

    tpl_npc_names = {n["name"]: n for n in tpl.get("npcs", [])}
    for name, npc_state in state.npcs.items():
        tpl_npc = tpl_npc_names.get(name)
        if tpl_npc:
            eid = tpl_npc.get("entity_id") or f"npc:{name}"
            prompt = build_portrait_prompt(tpl_npc, tpl["art_style"], tid)
        else:
            eid = f"npc:{name}"
            prompt = (
                f"Portrait of fantasy NPC {name}, {npc_state.attitude}, "
                f"{tpl['art_style']}, square format"
            )
            prompt = finalize_image_prompt(prompt, tid)
        registry[eid] = {
            "type": "portrait",
            "prompt": prompt,
            "prompt_hash": hash_prompt(prompt),
            "name": name,
        }

    tpl_locs = {loc["name"]: loc for loc in tpl.get("locations", [])}
    for loc_name in tpl_locs:
        loc = tpl_locs[loc_name]
        eid = loc.get("entity_id") or f"loc:{loc_name}"
        prompt = build_background_prompt(loc, tpl["art_style"], tid)
        registry[eid] = {
            "type": "background",
            "prompt": prompt,
            "prompt_hash": hash_prompt(prompt),
            "name": loc_name,
        }

    player_prompt = build_player_portrait_prompt(state.player, tid)
    registry["player:portrait"] = {
        "type": "portrait",
        "prompt": player_prompt,
        "prompt_hash": hash_prompt(player_prompt),
        "name": state.player.name,
    }
    return registry


def create_initial_game_state(template_id: str | None = None) -> GameState:
    return create_game_state_from_template(template_id)


def location_connections_for_state(state: GameState) -> dict[str, list[str]]:
    tid = state.flags.get("template_id") if state.flags else None
    if state.flags.get("seed_location_connections"):
        raw = state.flags["seed_location_connections"]
        if isinstance(raw, dict):
            return {k: list(v) for k, v in raw.items()}
    return get_location_connections(tid)


def all_locations_for_state(state: GameState) -> list[str]:
    if state.flags.get("seed_locations"):
        locs = state.flags["seed_locations"]
        if isinstance(locs, list) and locs:
            if isinstance(locs[0], dict):
                return [loc["name"] for loc in locs if loc.get("name")]
            return list(locs)
    return get_locations_for_template(state.flags.get("template_id") if state.flags else None)

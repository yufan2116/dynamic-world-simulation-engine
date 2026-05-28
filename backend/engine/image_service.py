"""游戏流程图像 URL — 从 prompt_hash 缓存同步解析。"""
from __future__ import annotations

from typing import Any

from engine.image_assets import get_image_url, placeholder_url
from engine.world_state import GameState


def ensure_image_entities(state: GameState) -> dict[str, dict[str, Any]]:
    """旧存档可能缺少 image_entities，按当前模板重建映射。"""
    reg = state.flags.get("image_entities")
    if isinstance(reg, dict) and reg:
        return reg
    from engine.world_templates import build_image_entity_registry

    tid = state.flags.get("template_id") or "missing_merchant_medieval"
    state.flags.setdefault("template_id", tid)
    reg = build_image_entity_registry(tid, state)
    state.flags["image_entities"] = reg
    return reg


def _registry(state: GameState) -> dict[str, dict[str, Any]]:
    return ensure_image_entities(state)


def _url_for_entity(state: GameState, entity_id: str) -> str:
    ent = _registry(state).get(entity_id)
    if ent and ent.get("prompt_hash"):
        url = get_image_url(ent["prompt_hash"])
        if url:
            return url
    return placeholder_url()


def npc_entity_id(name: str) -> str:
    return f"npc:{name}"


def loc_entity_id(location: str) -> str:
    return f"loc:{location}"


def resolve_player_portrait(state: GameState) -> str:
    # 若已有有效缓存 URL（非占位图），直接复用
    if state.player.portrait_url and "placeholder" not in state.player.portrait_url:
        ph = state.player.portrait_asset_key
        if ph and get_image_url(ph) and state.player.portrait_url == get_image_url(ph):
            return state.player.portrait_url
    url = _url_for_entity(state, "player:portrait")
    state.player.portrait_url = url
    ent = _registry(state).get("player:portrait")
    if ent:
        state.player.portrait_asset_key = ent.get("prompt_hash")
    return url


def resolve_location_background(state: GameState, location: str | None = None) -> str:
    loc = location or state.location
    eid = loc_entity_id(loc)
    ent = _registry(state).get(eid)
    if ent:
        state.location_asset_key = ent.get("prompt_hash")
    url = _url_for_entity(state, eid)
    cached = state.flags.setdefault("background_urls", {})
    if isinstance(cached, dict):
        cached[loc] = url
    state.flags["current_background_url"] = url
    return url


def scene_npc_names(state: GameState) -> list[str]:
    """场景舞台应展示的 NPC（可与 strict 地点逻辑略有出入，如开场）。"""
    custom = state.flags.get("scene_npcs")
    if isinstance(custom, list) and custom:
        return [str(n) for n in custom if str(n) in state.npcs]
    names: list[str] = []
    for name in state.active_npcs:
        npc = state.npcs.get(name)
        if npc and npc.present:
            names.append(name)
    for npc in state.npc_at_location():
        if npc.name not in names:
            names.append(npc.name)
    return names


def sync_opening_scene_npcs(state: GameState) -> None:
    """开场村口：叙事中的关键人物同台展示。"""
    if not state.flags.get("opening_scene"):
        return
    if state.location != "村口":
        return
    tid = state.flags.get("template_id") or "missing_merchant_medieval"
    if tid != "missing_merchant_medieval":
        return
    state.flags["scene_npcs"] = ["托马斯", "艾琳娜"]
    for name in ("托马斯", "艾琳娜"):
        npc = state.npcs.get(name)
        if not npc:
            continue
        updated = npc.model_copy(update={"location": "村口", "present": True})
        state.npcs[name] = updated
    active = list(state.active_npcs)
    for name in ("托马斯", "艾琳娜"):
        if name not in active:
            active.append(name)
    state.active_npcs = active


def resolve_all_npc_portraits(state: GameState) -> dict[str, str]:
    """模板内全部 NPC 的肖像 URL（供前端缓存与行动面板使用）。"""
    portraits: dict[str, str] = {}
    reg = _registry(state)
    for eid, ent in reg.items():
        if not eid.startswith("npc:"):
            continue
        name = str(ent.get("name") or eid[4:])
        portraits[name] = _url_for_entity(state, eid)
    state.flags["npc_portraits"] = portraits
    return portraits


def resolve_npc_portraits_at_location(state: GameState) -> dict[str, str]:
    sync_opening_scene_npcs(state)
    all_p = resolve_all_npc_portraits(state)
    return {n: all_p.get(n, placeholder_url()) for n in scene_npc_names(state)}


def attach_image_urls(
    state: GameState,
    *,
    include_portrait: bool = True,
    include_background: bool = True,
    include_npcs: bool = False,
    location_changed: bool = False,
) -> dict[str, Any]:
    tid = state.flags.get("template_id", "missing_merchant_medieval")
    urls: dict[str, Any] = {
        "image_style": tid,
        "template_id": tid,
    }

    if include_portrait:
        urls["portrait_url"] = resolve_player_portrait(state)

    if include_background or location_changed:
        urls["background_url"] = resolve_location_background(state)
    else:
        cached = state.flags.get("background_urls")
        if isinstance(cached, dict) and state.location in cached:
            urls["background_url"] = cached[state.location]
        else:
            urls["background_url"] = (
                state.flags.get("current_background_url")
                or resolve_location_background(state)
            )

    sync_opening_scene_npcs(state)
    if include_npcs:
        urls["npc_portraits"] = resolve_all_npc_portraits(state)
        urls["scene_npcs"] = scene_npc_names(state)
    else:
        all_npc = state.flags.get("npc_portraits")
        if isinstance(all_npc, dict) and all_npc:
            urls["npc_portraits"] = dict(all_npc)
        else:
            urls["npc_portraits"] = resolve_all_npc_portraits(state)
        urls["scene_npcs"] = scene_npc_names(state)

    registry = _registry(state)
    urls["image_entities"] = {
        eid: {
            "url": get_image_url(ent.get("prompt_hash", "")) or placeholder_url(),
            "prompt_hash": ent.get("prompt_hash"),
            "type": ent.get("type"),
        }
        for eid, ent in registry.items()
    }

    return urls


def apply_player_portrait_prompt(state: GameState) -> str:
    """玩家职业/描述变化后重建 player:portrait 注册表项。"""
    from engine.world_templates import build_image_entity_registry

    tid = state.flags.get("template_id", "missing_merchant_medieval")
    reg = build_image_entity_registry(tid, state)
    state.flags["image_entities"] = reg
    state.player.portrait_url = None
    return resolve_player_portrait(state)

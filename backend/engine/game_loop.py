"""游戏主循环编排。"""
from __future__ import annotations

from typing import Any

from engine.event_system import EventSystem
from engine.intent_parser import parse_intent
from engine.action_generator import generate_actions
from engine.narrative_engine import generate_narrative
from engine.narrative_log import append_narrative, ensure_narrative_log, seed_opening_narratives
from engine.opening_narrative import get_opening_narrative, get_opening_prologue
from engine.crisis_escalation import get_crisis_ui
from engine.offline_sim import catch_up_offline, stamp_simulation_time
from engine.rumor_network import add_rumor
from engine.world_tick import format_offline_summary, run_world_ticks
from engine.npc_memory import apply_stored_memories, sync_memories_to_db
from engine.rule_engine import DiceRollInfo, dice_roll_to_dict, perform_check
from engine.world_simulator import apply_world_simulation
from engine.world_state import GameState
from engine.seed_loader import get_opening_events, load_seed_world
from engine.world_template_manager import DEFAULT_TEMPLATE_ID, get_narrative_style, resolve_template_id
from engine.world_templates import create_initial_game_state, get_template
from engine.choice_renderer import package_narrative_choices
from engine.encounter_state import build_encounter_state
from engine.scene_graph import build_scene_graph
from engine.image_assets import ensure_template_assets, get_image_url, is_ai_images_enabled
from engine.image_assets import warm_url_cache_from_db
from engine.image_service import (
    apply_player_portrait_prompt,
    attach_image_urls,
    ensure_image_entities,
    sync_opening_scene_npcs,
)
from engine.image_ws import image_ws_hub
from storage import db


class GameLoop:
    def __init__(self) -> None:
        self.state: GameState | None = None
        self.events = EventSystem()

    def _package_choices(
        self,
        narrative: str,
        action_data: dict[str, Any],
        *,
        intent: dict[str, Any] | None = None,
        changes: dict[str, Any] | None = None,
        dice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.state:
            return {
                "narrative": narrative,
                "narrative_with_choices": narrative,
                "inline_choices": [],
                "choice_transition": "",
            }
        intent = intent or {}
        changes = changes or {}
        encounter = build_encounter_state(self.state, intent, changes, dice)
        scene_graph = build_scene_graph(self.state, intent, changes)
        return package_narrative_choices(
            self.state,
            narrative,
            action_data,
            encounter=encounter,
            scene_graph=scene_graph,
        )

    async def start_new_game(self, template_id: str | None = None) -> dict[str, Any]:
        await db.clear_game()
        await db.init_db()
        self.events.reset()
        tid = resolve_template_id(template_id or DEFAULT_TEMPLATE_ID)
        self.state = create_initial_game_state(tid)
        self.state.flags["template_id"] = tid
        self._init_world_systems()
        return await self._finalize_new_game(tid, mode="random")

    async def start_new_demo_game(self, seed_name: str = "ravenford_demo") -> dict[str, Any]:
        """演示种子开局 — 固定 Ravenford 初始世界，后续仍动态模拟。"""
        await db.clear_game()
        await db.init_db()
        self.events.reset()
        self.state = load_seed_world(seed_name)
        tid = self.state.flags.get("template_id", "missing_merchant_medieval")
        stamp_simulation_time(self.state)
        for ev in get_opening_events(seed_name):
            await self.events.record(
                ev.get("event_type", "world_change"),
                ev.get("payload", {}),
            )
        return await self._finalize_new_game(tid, mode="demo", seed_name=seed_name)

    async def _finalize_new_game(
        self,
        tid: str,
        *,
        mode: str = "random",
        seed_name: str | None = None,
    ) -> dict[str, Any]:
        turn = self.events.next_turn()
        await self._persist()

        label = "【演示世界已载入】" if mode == "demo" else "【游戏开始】"
        intent_data = {
            "action_type": "start",
            "description": "演示种子开局" if mode == "demo" else "游戏开始",
            "seed": seed_name,
        }
        await self.events.record_action(label, intent_data)

        prologue = get_opening_prologue(self.state, tid)
        narrative = get_opening_narrative(self.state, tid)
        action_data = generate_actions(self.state)
        choice_pkg = self._package_choices(narrative, action_data)
        seed_opening_narratives(
            self.state, prologue, choice_pkg["narrative_with_choices"], turn
        )
        self.state.flags["last_turn"] = turn
        await self.events.record_narrative_meta({"narrative": "opening", "phase": "prologue"})

        tpl = get_template(tid)
        image_urls = self._image_urls(
            include_portrait=True,
            include_background=True,
            include_npcs=True,
        )

        import asyncio

        async def _on_ready(msg: dict) -> None:
            await image_ws_hub.broadcast(tid, msg)

        total_entities = len(self.state.flags.get("image_entities", {}))
        completed = sum(
            1
            for ent in (self.state.flags.get("image_entities") or {}).values()
            if ent.get("prompt_hash") and get_image_url(ent["prompt_hash"])
        )
        ai_on = is_ai_images_enabled()
        needs_generation = ai_on and total_entities > 0 and completed < total_entities

        if needs_generation:
            asyncio.create_task(
                ensure_template_assets(tid, state=self.state, on_ready=_on_ready)
            )

        visuals_pending = needs_generation

        chapter = self.state.flags.get("seed_chapter") if mode == "demo" else None
        if not isinstance(chapter, dict) or not chapter.get("title"):
            chapter = {"number": 1, "title": tpl.get("chapter_title", "第一章")}
        elif "number" not in chapter:
            chapter = {**chapter, "number": 1}

        tpl_bundle = get_template(tid)
        ui_theme = tpl_bundle.get("ui_theme") or self.state.flags.get("ui_theme", {})
        from engine.world_ontology import attach_ontology_to_state, ontology_for_state

        attach_ontology_to_state(self.state)
        world_ontology = ontology_for_state(self.state)

        return {
            "prologue": prologue,
            "narrative": narrative,
            "visuals_pending": visuals_pending,
            "chapter": chapter,
            "template_id": tid,
            "ui_theme": ui_theme,
            "world_ontology": world_ontology,
            "seed_id": seed_name or self.state.flags.get("seed_id"),
            "game_mode": mode,
            "world_state": self.state.model_dump(by_alias=True),
            "available_options": action_data["flat_inputs"],
            "available_actions": action_data,
            "inline_choices": choice_pkg["inline_choices"],
            "choice_transition": choice_pkg["choice_transition"],
            "dice_roll_info": None,
            "turn": turn,
            "crisis_state": get_crisis_ui(self.state),
            "image_generation": {
                "enabled": ai_on,
                "total": total_entities,
                "completed": completed,
            },
            **image_urls,
        }

    async def process_action(self, player_input: str) -> dict[str, Any]:
        if not self.state:
            loaded = await self._load()
            if not loaded:
                tid = self.state.flags.get("template_id") if self.state else None
                return await self.start_new_game(tid)

        assert self.state is not None
        turn = self.events.next_turn()
        context = {"location": self.state.location, "quests": [q.id for q in self.state.quests]}

        intent = await parse_intent(player_input, context)
        await self.events.record_action(player_input, intent.model_dump())

        dice: DiceRollInfo | None = None
        if intent.requires_roll and intent.action_type not in ("move", "rest", "unknown"):
            desc = f"{intent.action_type}"
            if intent.target:
                desc += f" vs {intent.target}"
            dice = perform_check(
                self.state.player,
                intent.ability,
                intent.dc,
                description=desc,
            )
            await self.events.record_dice(dice_roll_to_dict(dice))
        elif intent.action_type == "unknown":
            dice = perform_check(
                self.state.player,
                "WIS",
                12,
                description="模糊意图感知",
            )
            await self.events.record_dice(dice_roll_to_dict(dice))

        changes = apply_world_simulation(self.state, intent, dice)
        tick_events = run_world_ticks(self.state, ticks=1)
        changes["world_tick_events"] = tick_events
        await self.events.record_world_change(changes)

        dice_dict = dice_roll_to_dict(dice) if dice else None
        narrative = await generate_narrative(
            self.state,
            intent.model_dump(),
            dice,
            changes,
            self.events.list_events(),
        )
        await self.events.record_narrative_meta({"length": len(narrative)})

        self.state.flags["opening_scene"] = False
        action_data = generate_actions(self.state)
        choice_pkg = self._package_choices(
            narrative,
            action_data,
            intent=intent.model_dump(),
            changes=changes,
            dice=dice_dict,
        )
        append_narrative(
            self.state,
            choice_pkg["narrative_with_choices"],
            kind="narrative",
            turn=turn,
        )
        self.state.flags["last_turn"] = turn

        await self._persist()

        tid = self.state.flags.get("template_id", DEFAULT_TEMPLATE_ID)
        tpl = get_template(tid)
        location_changed = bool(changes.get("moved_to"))
        image_urls = self._image_urls(
            include_portrait=True,
            include_background=location_changed,
            include_npcs=location_changed or intent.action_type == "talk",
            location_changed=location_changed,
        )

        return {
            "narrative": choice_pkg["narrative"],
            "inline_choices": choice_pkg["inline_choices"],
            "choice_transition": choice_pkg["choice_transition"],
            "chapter": {
                "number": 1,
                "title": tpl.get("chapter_title", "第一章"),
            },
            "world_state_changes": changes,
            "available_options": action_data["flat_inputs"],
            "available_actions": action_data,
            "dice_roll_info": dice_dict,
            "world_state": self.state.model_dump(by_alias=True),
            "turn": turn,
            "crisis_state": get_crisis_ui(self.state),
            **image_urls,
        }

    async def get_state(self) -> dict[str, Any]:
        if not self.state:
            await self._load()
        if not self.state:
            return {"initialized": False}

        await warm_url_cache_from_db()
        ensure_image_entities(self.state)
        sync_opening_scene_npcs(self.state)

        offline = catch_up_offline(self.state)
        offline_narrative = ""
        if offline.get("ticks_run", 0) > 0:
            await self._persist()
            offline_narrative = format_offline_summary(offline.get("summary", []))

        events_db = await db.get_events(limit=100)
        memories = sync_memories_to_db(self.state)
        image_urls = self._image_urls(
            include_portrait=True,
            include_background=True,
            include_npcs=True,
        )
        history = ensure_narrative_log(self.state)
        action_data = generate_actions(self.state)
        choice_pkg = self._package_choices("", action_data)

        from engine.world_ontology import attach_ontology_to_state, ontology_for_state

        attach_ontology_to_state(self.state)
        await self._persist()
        return {
            "initialized": True,
            "world_state": self.state.model_dump(by_alias=True),
            "world_ontology": ontology_for_state(self.state),
            "npc_memories": memories,
            "events": events_db,
            "event_log": self.events.list_events(),
            "offline_summary": offline,
            "offline_narrative": offline_narrative,
            "narrative_history": history,
            "crisis_state": get_crisis_ui(self.state),
            "available_actions": action_data,
            "inline_choices": choice_pkg["inline_choices"],
            "choice_transition": choice_pkg["choice_transition"],
            **image_urls,
        }

    def _image_urls(self, **kwargs: Any) -> dict[str, Any]:
        if not self.state:
            return {}
        try:
            return attach_image_urls(self.state, **kwargs)
        except Exception:
            return {
                "portrait_url": getattr(self.state.player, "portrait_url", None),
                "background_url": self.state.flags.get("current_background_url"),
                "npc_portraits": {},
                "image_style": self.state.flags.get("image_style", "storybook"),
            }

    async def refresh_player_portrait(self) -> dict[str, Any]:
        if not self.state:
            await self._load()
        if not self.state:
            raise ValueError("游戏未初始化")
        url = apply_player_portrait_prompt(self.state)
        await self._persist()
        return {
            "portrait_url": url,
            "portrait_asset_key": self.state.player.portrait_asset_key or "",
        }

    async def _persist(self) -> None:
        if not self.state:
            return
        stamp_simulation_time(self.state)
        await db.save_game_state(self.state.model_dump(by_alias=True))
        await db.save_npc_memories(sync_memories_to_db(self.state))

    def _init_world_systems(self) -> None:
        if not self.state:
            return
        if self.state.flags.get("seed_loaded"):
            stamp_simulation_time(self.state)
            return
        tid = resolve_template_id(self.state.flags.get("template_id"))
        tpl = get_template(tid)
        origin = tpl.get("default_location", self.state.location)
        rumors = self.state.flags.get("rumors")
        if isinstance(rumors, list) and rumors:
            stamp_simulation_time(self.state)
            return
        style = get_narrative_style(tid)
        rumor_text = style.get("default_rumor", "附近有异动传闻。")
        add_rumor(self.state, rumor_text, origin, credibility=0.6)
        stamp_simulation_time(self.state)

    async def _load(self) -> bool:
        data = await db.load_game_state()
        if not data:
            return False
        self.state = GameState.model_validate(data)
        self.state.flags["template_id"] = resolve_template_id(
            self.state.flags.get("template_id")
        )
        await warm_url_cache_from_db()
        ensure_image_entities(self.state)
        stored = await db.load_npc_memories()
        if stored:
            apply_stored_memories(self.state, stored)
        await self.events.load_from_db()
        return True


game_loop = GameLoop()

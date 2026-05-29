"""游戏主循环编排。"""
from __future__ import annotations

import copy
import hashlib
import base64
import pickle
import random
from typing import Any

from engine.event_system import EventSystem
from engine.intent_parser import ParsedIntent
from engine.action_generator import generate_actions
from engine.narrative_engine import build_narrative_proof, generate_narrative
from engine.narrative_log import append_narrative, ensure_narrative_log, seed_opening_narratives
from engine.opening_narrative import get_opening_narrative, get_opening_prologue
from engine.crisis_escalation import get_crisis_ui
from engine.offline_sim import catch_up_offline, stamp_simulation_time
from engine.rumor_network import add_rumor
from engine.world_tick import format_offline_summary, run_world_ticks
from engine.npc_memory import apply_stored_memories, sync_memories_to_db
from engine.rule_engine import DiceRollInfo, dice_roll_to_dict, outcome_succeeds, perform_check
from engine.world_simulator import apply_world_simulation
from engine.world_state import GameState
from engine.world_state import ensure_player_known_facts
from engine.player_knowledge import apply_action_result, ensure_player_knowledge, get_player_knowledge
from engine.narrative_validator import validate_narrative
from engine.narrative_formatter import format_narrative_html
from engine.rumor_network import add_rumor
from engine.seed_loader import get_opening_events, load_seed_world
from engine.world_template_manager import DEFAULT_TEMPLATE_ID, get_narrative_style, resolve_template_id
from engine.world_templates import create_initial_game_state, get_template
from engine.choice_renderer import package_narrative_choices
from engine.chapter_slice import (
    apply_chapter_ending,
    build_session_summary as build_slice_session_summary,
    evaluate_chapter_ending,
    is_vertical_slice,
    package_chapter_complete_response,
    track_slice_turn,
)
from engine.scripted_demo_runner import (
    get_opening_package,
    get_scripted_state_package,
    init_scripted_demo,
    is_scripted_demo_mode,
    process_scripted_demo_choice,
    resolve_scripted_choice_id,
)
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

    def _rng_state_b64(self) -> str:
        raw = pickle.dumps(random.getstate())
        return base64.b64encode(raw).decode("ascii")

    def _set_rng_state_b64(self, b64: str | None) -> None:
        if not b64:
            return
        try:
            raw = base64.b64decode(b64.encode("ascii"))
            random.setstate(pickle.loads(raw))
        except Exception:
            return

    async def _save_snapshot(self, turn: int) -> None:
        if not self.state:
            return
        branch_id = str(self.state.flags.get("branch_id") or "")
        if not branch_id:
            return
        await db.save_snapshot(
            branch_id=branch_id,
            turn=int(turn),
            state_dict=self.state.model_dump(by_alias=True),
            events=await db.get_events_range(),
            rng_state_b64=self._rng_state_b64(),
        )

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

    async def start_new_game(self, template_id: str | None = None, *, seed_id: str | None = None) -> dict[str, Any]:
        await db.clear_game()
        await db.init_db()
        self.events.reset()
        tid = resolve_template_id(template_id or DEFAULT_TEMPLATE_ID)
        self.state = create_initial_game_state(tid)
        self.state.flags["template_id"] = tid
        use_seed = seed_id or self.state.flags.get("seed_id") or f"{tid}:default"
        self.state.flags["seed_id"] = use_seed
        # 新会话默认新分支（可 fork/rewind）
        branch_id = await db.create_branch(seed_id=str(use_seed), template_id=tid, label="main")
        self.state.flags["branch_id"] = branch_id
        self.state.flags["branch_label"] = "main"
        # 固定 RNG seed：同 seed_id + 同操作序列 => 可复现分叉差异
        random.seed(str(use_seed))
        self._init_world_systems()
        result = await self._finalize_new_game(tid, mode="random")
        await self._save_snapshot(result.get("turn") or 1)
        return result

    async def start_new_demo_game(self, seed_name: str = "ravenford_demo") -> dict[str, Any]:
        """演示种子开局 — 固定 Ravenford 初始世界，后续仍动态模拟。"""
        await db.clear_game()
        await db.init_db()
        self.events.reset()
        self.state = load_seed_world(seed_name)
        tid = self.state.flags.get("template_id", "missing_merchant_medieval")
        seed_id = self.state.flags.get("seed_id") or seed_name
        self.state.flags["seed_id"] = seed_id
        branch_id = await db.create_branch(seed_id=str(seed_id), template_id=str(tid), label="main")
        self.state.flags["branch_id"] = branch_id
        self.state.flags["branch_label"] = "main"
        random.seed("ravenford_demo_vslice_2025")
        self.state.flags["vertical_slice_demo"] = True
        init_scripted_demo(self.state)
        stamp_simulation_time(self.state)
        for ev in get_opening_events(seed_name):
            await self.events.record(
                ev.get("event_type", "world_change"),
                ev.get("payload", {}),
            )
        result = await self._finalize_new_game(tid, mode="demo", seed_name=seed_name)
        await self._save_snapshot(result.get("turn") or 1)
        return result

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
        ensure_player_known_facts(self.state)
        ensure_player_knowledge(self.state)
        # 开场信息登记为已知事实（来源：开场 NPC / 场景）
        if self.state.flags.get("opening_scene"):
            facts = ensure_player_known_facts(self.state)
            # NPC 可见状态即为“玩家亲眼看到”
            if "艾琳娜" in self.state.npcs and "艾琳娜" not in facts["known_npcs"]:
                facts["known_npcs"].append("艾琳娜")
            if "托马斯" in self.state.npcs and "托马斯" not in facts["known_npcs"]:
                facts["known_npcs"].append("托马斯")
            if "米拉" in self.state.npcs and "米拉" not in facts["known_npcs"]:
                facts["known_npcs"].append("米拉")
            # 开场 player_facing_facts：只登记正文明确出现的内容（禁止脚印/痕迹/遗留物等）
            pf = facts.get("player_facing_facts")
            if isinstance(pf, list):
                pf.extend(
                    [
                        {
                            "id": "pf_location_village_gate",
                            "type": "location",
                            "text": "当前地点：雷文福德村口",
                            "source": "narrative_opening",
                            "introduced_in_narrative": True,
                            "visibility": "public",
                        },
                        {
                            "id": "pf_elena_help",
                            "type": "npc_statement",
                            "text": "艾琳娜公开求助：父亲马库斯昨晚未归。",
                            "source": "npc_statement",
                            "source_label": "艾琳娜",
                            "introduced_in_narrative": True,
                            "visibility": "public",
                        },
                        {
                            "id": "pf_thomas_guarding",
                            "type": "observation",
                            "text": "托马斯在村口警戒，手按剑柄。",
                            "source": "player_observation",
                            "introduced_in_narrative": True,
                            "visibility": "public",
                        },
                        {
                            "id": "pf_mira_observing",
                            "type": "observation",
                            "text": "米拉站在酒馆门帘后观察，神色惊忧。",
                            "source": "player_observation",
                            "introduced_in_narrative": True,
                            "visibility": "public",
                        },
                        {
                            "id": "pf_gate_env",
                            "type": "environment",
                            "text": "村口环境：木栅、火把、泥泞广场、酒馆方向灯火。",
                            "source": "narrative_opening",
                            "introduced_in_narrative": True,
                            "visibility": "public",
                        },
                    ]
                )
            pk = ensure_player_knowledge(self.state)
            for pf_item in facts.get("player_facing_facts") or []:
                if not isinstance(pf_item, dict):
                    continue
                pid = str(pf_item.get("id", ""))
                ptext = str(pf_item.get("text") or "").strip()
                if not pid or not ptext:
                    continue
                bucket = "observations" if pf_item.get("type") in ("observation", "clue", "environment") else "facts"
                if not any(isinstance(x, dict) and x.get("id") == pid for x in pk.get(bucket, [])):
                    pk[bucket].append({"id": pid, "text": ptext, "source": pf_item.get("source", "narrative")})
            # 把“艾琳娜求助”登记为来源明确的 rumor（用于复盘/证明，不作为选项直接信息化展示）
            add_rumor(
                self.state,
                "艾琳娜哭喊：父亲昨晚没有回来。",
                origin=str(self.state.location),
                credibility=0.95,
                source_type="npc",
                source_id="elena",
                source_label="艾琳娜",
                visibility="public",
                known_to_player=True,
            )
        if is_scripted_demo_mode(self.state):
            opening_pkg = get_opening_package(self.state)
            prologue = opening_pkg.get("prologue") or ""
            narrative = opening_pkg["narrative"]
            action_data = opening_pkg["available_actions"]
            from engine.choice_renderer import format_choices_html

            ch_html = format_choices_html(
                opening_pkg.get("inline_choices") or [],
                transition=opening_pkg.get("choice_transition") or "",
            )
            choice_pkg = {
                "narrative": narrative,
                "narrative_with_choices": f"{narrative}\n{ch_html}",
                "inline_choices": opening_pkg.get("inline_choices") or [],
                "choice_transition": opening_pkg.get("choice_transition") or "",
            }
            self.state.flags["last_available_actions"] = action_data
            self.state.flags["last_inline_choices"] = choice_pkg.get("inline_choices") or []
        else:
            action_data = generate_actions(self.state)
            self.state.flags["last_available_actions"] = action_data
            choice_pkg = self._package_choices(narrative, action_data)
            self.state.flags["last_inline_choices"] = choice_pkg.get("inline_choices") or []
        seed_opening_narratives(
            self.state,
            prologue,
            choice_pkg["narrative_with_choices"],
            turn,
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

        slice_extra: dict[str, Any] = {}
        if mode == "demo":
            slice_extra = {"vertical_slice": True, "game_mode": "demo"}

        return {
            "prologue": prologue,
            "narrative": choice_pkg["narrative"],
            "visuals_pending": visuals_pending,
            "chapter": chapter,
            "template_id": tid,
            "ui_theme": ui_theme,
            "world_ontology": world_ontology,
            "seed_id": seed_name or self.state.flags.get("seed_id"),
            "game_mode": mode,
            **slice_extra,
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

    def _action_request_context(
        self,
        *,
        selected_choice_text: str | None = None,
        action_id: str | None = None,
        intent_payload: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        """本回合行动上下文（参数优先，避免并发请求清空实例属性）。"""
        choice_text = selected_choice_text
        if choice_text is None:
            try:
                choice_text = getattr(self, "_selected_choice_text", None)
            except Exception:
                choice_text = None

        aid = action_id
        if aid is None:
            try:
                aid = getattr(self, "_action_id", None)
            except Exception:
                aid = None

        intent = intent_payload
        if intent is None:
            try:
                raw = getattr(self, "_intent_payload", None)
                if isinstance(raw, dict):
                    intent = raw
            except Exception:
                intent = None
        elif not isinstance(intent, dict):
            intent = None

        return choice_text, aid, intent

    async def process_action(
        self,
        player_input: str,
        *,
        selected_choice_text: str | None = None,
        action_id: str | None = None,
        intent_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.state:
            loaded = await self._load()
            if not loaded:
                tid = self.state.flags.get("template_id") if self.state else None
                return await self.start_new_game(tid)

        assert self.state is not None
        choice_text, aid, intent = self._action_request_context(
            selected_choice_text=selected_choice_text,
            action_id=action_id,
            intent_payload=intent_payload,
        )
        if is_scripted_demo_mode(self.state) and not self.state.flags.get("chapter_complete"):
            return await self._process_demo_story_action(
                player_input,
                selected_choice_text=choice_text,
                action_id=aid,
                intent_payload=intent,
            )
        ensure_player_known_facts(self.state)
        ensure_player_knowledge(self.state)
        turn = self.events.next_turn()
        context = {"location": self.state.location, "quests": [q.id for q in self.state.quests]}

        before_memories = copy.deepcopy(sync_memories_to_db(self.state))
        before_flags = copy.deepcopy(self.state.flags)
        before_faction_rep = copy.deepcopy(self.state.faction_reputation)

        # player_input：用于规则与意图解析（可能是内嵌选项的 input）
        # choice_text：用于 UI 回显（更贴近玩家看到的文本）
        player_raw_input = player_input
        player_action_display = (choice_text or player_raw_input).strip()

        from engine.action_pipeline import (
            build_intent_async,
            log_action_pipeline,
            lookup_action_meta,
            run_action_simulation,
        )

        intent, intent_meta = await build_intent_async(
            player_input=player_input,
            choice_text=choice_text,
            action_id=aid,
            intent_payload=intent if isinstance(intent, dict) else None,
            context=context,
        )
        action_source, uses_known_fact = lookup_action_meta(self.state, aid)
        await self.events.record_action(
            player_action_display or player_input,
            {
                **intent.model_dump(),
                "action_id": aid,
                "player_action_display": player_action_display,
            },
        )

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

        changes = run_action_simulation(
            self.state,
            intent,
            dice,
            action_id=aid,
            action_source=action_source,
            uses_known_fact=uses_known_fact,
        )
        # 先构建 scene_graph（供本回合后续 action_generator 做 precondition）
        try:
            self.state.flags["last_scene_graph"] = build_scene_graph(self.state, intent.model_dump(), changes)
        except Exception:
            self.state.flags["last_scene_graph"] = {}
        tick_events = run_world_ticks(self.state, ticks=1)
        # API 返回不包含 hidden_events（内部仍可在 events / snapshot 里追溯）
        if isinstance(tick_events, dict):
            tick_events = {
                "public_events": tick_events.get("public_events") or [],
                "local_events": tick_events.get("local_events") or [],
                "discovered_events": tick_events.get("discovered_events") or [],
            }
        changes["world_tick_events"] = tick_events
        await self.events.record_world_change(changes)

        ar = changes.get("action_result")
        if isinstance(ar, dict):
            apply_action_result(self.state, ar)

        track_slice_turn(
            self.state,
            intent.model_dump(),
            changes,
            player_action_display=player_action_display or "",
            turn=turn,
        )

        # --- 复盘证据：NPC 记忆变化（本回合前后 diff） ---
        after_memories = sync_memories_to_db(self.state)
        mem_diff: dict[str, Any] = {}
        for npc, after_list in after_memories.items():
            before_list = before_memories.get(npc, [])
            if after_list != before_list:
                added = [m for m in after_list if m not in before_list]
                removed = [m for m in before_list if m not in after_list]
                mem_diff[npc] = {
                    "added": added,
                    "removed": removed,
                    "before_count": len(before_list),
                    "after_count": len(after_list),
                }
        if mem_diff:
            await self.events.record("npc_memory_diff", {"diff": mem_diff})

        # --- 复盘证据：派系/危机/经济等关键指标变化（flags + reputation） ---
        def _pick_flags(flags: dict[str, Any]) -> dict[str, Any]:
            keys = [
                "crisis",
                "economy",
                "factions",
                "village_panic",
                "danger_level",
                "war_risk",
                "tension",
                "spiritual_pollution",
                "bandit_raid",
            ]
            out: dict[str, Any] = {}
            for k in keys:
                if k in flags:
                    out[k] = flags.get(k)
            return out

        before_metrics = {"flags": _pick_flags(before_flags), "faction_reputation": before_faction_rep}
        after_metrics = {"flags": _pick_flags(self.state.flags), "faction_reputation": self.state.faction_reputation}
        if before_metrics != after_metrics:
            await self.events.record(
                "sim_metrics_diff",
                {"before": before_metrics, "after": after_metrics},
            )

        dice_dict = dice_roll_to_dict(dice) if dice else None
        # 叙事输入证明（哈希 + payload 预览）
        proof = build_narrative_proof(
            self.state,
            intent.model_dump(),
            dice,
            changes,
            self.events.list_events(),
            player_action_display=player_action_display,
        )
        narrative = await generate_narrative(
            self.state,
            intent.model_dump(),
            dice,
            changes,
            self.events.list_events(),
            player_action_display=player_action_display,
        )
        legacy_facts = ensure_player_known_facts(self.state)
        allowed_locs = set(legacy_facts.get("known_locations") or [])
        allowed_locs.add(str(self.state.location))
        narrative, _narr_ok = validate_narrative(
            narrative,
            self.state,
            intent=intent.model_dump(),
            allowed_locations=allowed_locs,
        )
        narrative = format_narrative_html(
            narrative,
            self.state,
            intent=intent.model_dump(),
            changes=changes,
        )
        proof["narrative_sha256"] = hashlib.sha256(narrative.encode("utf-8")).hexdigest()
        await self.events.record("narrative_proof", proof)
        await self.events.record_narrative_meta({"length": len(narrative)})

        self.state.flags["opening_scene"] = False
        resolved_aid = str(aid).strip() if aid else ""
        # reveals：从上一轮返回的 action 定义中写入 known_facts
        if resolved_aid:
            try:
                last_actions = self.state.flags.get("last_available_actions") or {}
                grouped = last_actions.get("grouped") if isinstance(last_actions, dict) else None
                found = None
                if isinstance(grouped, dict):
                    for arr in grouped.values():
                        if isinstance(arr, list):
                            for a in arr:
                                if isinstance(a, dict) and a.get("id") == resolved_aid:
                                    found = a
                                    break
                        if found:
                            break
                reveals = found.get("reveals") if isinstance(found, dict) else None
                if isinstance(reveals, list) and reveals:
                    facts = ensure_player_known_facts(self.state)
                    known_facts = facts.get("known_facts")
                    if isinstance(known_facts, list):
                        for item in reveals:
                            if not isinstance(item, dict):
                                continue
                            item = dict(item)
                            item.setdefault("discovered_turn", int(turn))
                            item.setdefault("discovered_at", str(self.state.location))
                            if not any(isinstance(x, dict) and x.get("id") == item.get("id") for x in known_facts):
                                known_facts.append(item)
            except Exception:
                pass

        # consumed_actions：一次性行动执行后写入（由 action_id 驱动）
        consumed = self.state.flags.get("consumed_actions")
        if not isinstance(consumed, list):
            consumed = []
        if resolved_aid and resolved_aid not in consumed:
            consumed.append(resolved_aid)
        if resolved_aid == "hear_thomas_order":
            self.state.flags["heard_thomas_order"] = True
        self.state.flags["consumed_actions"] = consumed

        chapter_complete_payload: dict[str, Any] = {}
        ending_id = evaluate_chapter_ending(self.state, turn)
        if ending_id and not self.state.flags.get("chapter_complete"):
            ending_html = apply_chapter_ending(self.state, ending_id)
            narrative = f"{narrative}\n{ending_html}"
            chapter_complete_payload = package_chapter_complete_response(self.state)
            await self.events.record(
                "chapter_complete",
                {"ending_id": ending_id, "turn": turn},
            )

        if self.state.flags.get("chapter_complete"):
            action_data = {
                "grouped": {},
                "category_labels": {},
                "flat_inputs": [],
            }
        else:
            action_data = generate_actions(self.state)
        self.state.flags["last_available_actions"] = action_data
        log_action_pipeline(
            meta=intent_meta,
            intent=intent,
            action_id=aid,
            action_source=action_source,
            uses_known_fact=uses_known_fact,
            changes=changes,
            new_actions_count=sum(
                len(v) for v in (action_data.get("grouped") or {}).values() if isinstance(v, list)
            ),
        )
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
        await self._save_snapshot(turn)

        tid = self.state.flags.get("template_id", DEFAULT_TEMPLATE_ID)
        tpl = get_template(tid)
        location_changed = bool(changes.get("moved_to"))
        image_urls = self._image_urls(
            include_portrait=True,
            include_background=location_changed,
            include_npcs=location_changed or intent.action_type == "talk",
            location_changed=location_changed,
        )

        resp: dict[str, Any] = {
            "narrative": choice_pkg["narrative"],
            "inline_choices": choice_pkg["inline_choices"],
            "choice_transition": choice_pkg["choice_transition"],
            "player_raw_input": player_raw_input,
            "selected_choice_text": choice_text,
            "parsed_intent": intent.model_dump(),
            "intent_confidence": float(getattr(intent, "confidence", 0.5)),
            "chapter": self.state.flags.get("seed_chapter")
            or {
                "number": 1,
                "title": tpl.get("chapter_title", "第一章"),
            },
            "world_state_changes": changes,
            "available_options": action_data.get("flat_inputs", []),
            "available_actions": action_data,
            "dice_roll_info": dice_dict,
            "world_state": self.state.model_dump(by_alias=True),
            "turn": turn,
            "crisis_state": get_crisis_ui(self.state),
            "player_knowledge": get_player_knowledge(self.state),
            **image_urls,
        }
        if chapter_complete_payload:
            resp.update(chapter_complete_payload)
        if is_vertical_slice(self.state):
            resp["vertical_slice"] = True
        return resp

    async def _process_demo_story_action(
        self,
        player_input: str,
        *,
        selected_choice_text: str | None = None,
        action_id: str | None = None,
        intent_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作品集 Demo — 完全脚本化，不调用 action_generator / LLM / 世界模拟。"""
        assert self.state is not None
        turn = self.events.next_turn()

        player_action_display = (selected_choice_text or player_input).strip()
        raw_action_id = str(action_id).strip() if action_id else ""
        if not raw_action_id and isinstance(intent_payload, dict):
            iid = intent_payload.get("action_id")
            if iid:
                raw_action_id = str(iid).strip()

        option_id = resolve_scripted_choice_id(
            state=self.state,
            action_id=raw_action_id or None,
            player_text=player_action_display or player_input,
        )
        if not option_id:
            raise ValueError("请从叙事中的选项选择行动")

        await self.events.record_action(
            player_action_display or player_input,
            {"action_id": option_id, "mode": "scripted_demo"},
        )

        result = process_scripted_demo_choice(
            self.state,
            option_id,
            player_label=player_action_display,
            turn=turn,
        )
        narrative = result["narrative"]
        dice = result.get("dice")
        changes = result.get("changes") or {}
        await self.events.record_world_change(changes)
        if dice:
            await self.events.record_dice(dice_roll_to_dict(dice))

        chapter_complete_payload: dict[str, Any] = {}
        dice_dict = dice_roll_to_dict(dice) if dice else None
        action_data = result.get("available_actions") or {
            "grouped": {},
            "category_labels": {},
            "flat_inputs": [],
        }
        from engine.choice_renderer import format_choices_html

        ch_html = format_choices_html(
            result.get("inline_choices") or [],
            transition=result.get("choice_transition") or "",
        )
        choice_pkg = {
            "narrative": narrative,
            "narrative_with_choices": f"{narrative}\n{ch_html}" if ch_html else narrative,
            "inline_choices": result.get("inline_choices") or [],
            "choice_transition": result.get("choice_transition") or "",
        }

        if self.state.flags.get("chapter_complete"):
            summary = result.get("session_summary")
            if summary:
                chapter_complete_payload = {
                    "chapter_complete": True,
                    "session_summary": summary,
                }
            await self.events.record(
                "chapter_complete",
                {"ending_id": self.state.flags.get("chapter_ending_id"), "turn": turn},
            )

        self.state.flags["last_available_actions"] = action_data
        self.state.flags["last_inline_choices"] = choice_pkg.get("inline_choices") or []
        append_narrative(
            self.state,
            choice_pkg.get("narrative_with_choices") or narrative,
            kind="narrative",
            turn=turn,
        )
        self.state.flags["last_turn"] = turn
        await self._persist()
        await self._save_snapshot(turn)

        tid = self.state.flags.get("template_id", DEFAULT_TEMPLATE_ID)
        tpl = get_template(tid)

        resp: dict[str, Any] = {
            "narrative": choice_pkg["narrative"],
            "inline_choices": choice_pkg.get("inline_choices", []),
            "choice_transition": choice_pkg.get("choice_transition", ""),
            "player_raw_input": player_input,
            "selected_choice_text": selected_choice_text or player_action_display or None,
            "parsed_intent": {"action_id": option_id, "mode": "scripted_demo"},
            "intent_confidence": 1.0,
            "chapter": self.state.flags.get("seed_chapter")
            or {"number": 1, "title": tpl.get("chapter_title", "第一章")},
            "world_state_changes": changes,
            "available_options": action_data.get("flat_inputs", []),
            "available_actions": action_data,
            "dice_roll_info": dice_dict,
            "world_state": self.state.model_dump(by_alias=True),
            "turn": turn,
            "crisis_state": get_crisis_ui(self.state),
            "player_knowledge": get_player_knowledge(self.state),
            "game_mode": "demo",
            "vertical_slice": True,
            **self._image_urls(include_portrait=True, include_background=True, include_npcs=True),
        }
        resp.update(chapter_complete_payload)
        return resp

    async def rewind_to_turn(self, turn: int) -> dict[str, Any]:
        """回退到指定回合（当前分支）。"""
        if not self.state:
            await self._load()
        if not self.state:
            raise ValueError("游戏未初始化")
        branch_id = str(self.state.flags.get("branch_id") or "")
        if not branch_id:
            raise ValueError("缺少 branch_id")

        snap = await db.load_snapshot(branch_id=branch_id, turn=int(turn))
        if not snap:
            raise ValueError(f"未找到回合快照: turn={turn}")

        await db.save_game_state(snap["state"])
        # npc_memories 表会在 _persist 时同步；这里不强行写入，避免结构不匹配导致异常
        await db.clear_events()
        await db.insert_events_bulk(snap.get("events") or [])

        # 重新加载 state + events system
        await self._load()
        self._set_rng_state_b64(snap.get("rng_state_b64"))

        return await self.get_state()

    async def fork_branch(self, *, from_turn: int, label: str | None = None) -> dict[str, Any]:
        """从当前分支的指定回合 fork 出新分支，并切换到新分支。"""
        if not self.state:
            await self._load()
        if not self.state:
            raise ValueError("游戏未初始化")

        current_branch = str(self.state.flags.get("branch_id") or "")
        seed_id = str(self.state.flags.get("seed_id") or "")
        tid = str(self.state.flags.get("template_id") or DEFAULT_TEMPLATE_ID)
        snap = await db.load_snapshot(branch_id=current_branch, turn=int(from_turn))
        if not snap:
            raise ValueError(f"未找到回合快照: turn={from_turn}")

        new_label = label or f"fork@{from_turn}"
        new_branch = await db.create_branch(
            seed_id=seed_id,
            template_id=tid,
            parent_branch_id=current_branch,
            fork_turn=int(from_turn),
            label=new_label,
        )

        # 切换：用快照 state/events 覆盖当前会话，并把 branch_id 写进 flags
        state_dict = snap["state"]
        flags = state_dict.get("flags") or {}
        if isinstance(flags, dict):
            flags["branch_id"] = new_branch
            flags["branch_label"] = new_label
            flags["seed_id"] = seed_id
            flags["template_id"] = tid
            state_dict["flags"] = flags

        await db.save_game_state(state_dict)
        await db.clear_events()
        await db.insert_events_bulk(snap.get("events") or [])
        await self._load()
        self._set_rng_state_b64(snap.get("rng_state_b64"))

        # 把 fork 点以及之后的回合 snapshot 复制为新分支（当前只复制到 from_turn，后续会继续自动保存）
        await db.save_snapshot(
            branch_id=new_branch,
            turn=int(from_turn),
            state_dict=self.state.model_dump(by_alias=True),
            events=await db.get_events_range(),
            rng_state_b64=self._rng_state_b64(),
        )

        return await self.get_state()

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
        if is_scripted_demo_mode(self.state):
            scripted_pkg = get_scripted_state_package(self.state)
            action_data = scripted_pkg["available_actions"]
            choice_pkg = {
                "inline_choices": scripted_pkg.get("inline_choices") or [],
                "choice_transition": scripted_pkg.get("choice_transition") or "",
                "narrative": "",
                "narrative_with_choices": "",
            }
            self.state.flags["last_available_actions"] = action_data
            self.state.flags["last_inline_choices"] = choice_pkg.get("inline_choices") or []
        else:
            action_data = generate_actions(self.state)
            choice_pkg = self._package_choices("", action_data)
            self.state.flags["last_available_actions"] = action_data
            self.state.flags["last_inline_choices"] = choice_pkg.get("inline_choices") or []

        from engine.world_ontology import attach_ontology_to_state, ontology_for_state

        attach_ontology_to_state(self.state)
        await self._persist()
        state_resp: dict[str, Any] = {
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
            "player_knowledge": get_player_knowledge(self.state),
            "available_actions": action_data,
            "inline_choices": choice_pkg["inline_choices"],
            "choice_transition": choice_pkg["choice_transition"],
            **image_urls,
        }
        if self.state.flags.get("chapter_complete"):
            state_resp.update(package_chapter_complete_response(self.state))
        if is_scripted_demo_mode(self.state):
            state_resp["game_mode"] = "demo"
            state_resp["vertical_slice"] = True
            state_resp["available_actions"] = action_data
            state_resp["inline_choices"] = choice_pkg.get("inline_choices", [])
            state_resp["choice_transition"] = choice_pkg.get("choice_transition", "")
        return state_resp

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
        add_rumor(
            self.state,
            rumor_text,
            origin,
            credibility=0.6,
            source_type="overheard_conversation",
            source_id="villagers_whisper",
            source_label="低声交谈的村民",
        )
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

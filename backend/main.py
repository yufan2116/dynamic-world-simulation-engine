"""FastAPI 入口 — Dynamic World Simulation Engine。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine.game_loop import game_loop
from engine.image_assets import (
    ensure_image_dirs,
    ensure_placeholder_file,
    get_image_url,
    get_or_generate,
    is_ai_images_enabled,
    placeholder_url,
    warm_url_cache_from_db,
)
from engine.image_generator import ImageGenerationError
from engine.image_ws import image_ws_hub
from engine.llm_config import get_image_model, get_llm_model, is_image_configured, is_llm_configured
from engine.seed_loader import list_seeds
from engine.world_template_manager import DEFAULT_TEMPLATE_ID, list_templates, resolve_template_id
from storage.db import init_db, list_image_assets
from storage import db
from scripts.template_consistency_checker import scan_all, scan_template

load_dotenv()

STORAGE_ROOT = Path(__file__).resolve().parent / "storage"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_image_dirs()
    ensure_placeholder_file()
    await init_db()
    await warm_url_cache_from_db()
    yield


app = FastAPI(
    title="Dynamic World Simulation Engine",
    description="确定性世界模拟器 + LLM 叙事层",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STORAGE_ROOT)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ActionRequest(BaseModel):
    player_input: str = Field(default="", max_length=500)
    selected_choice_text: str | None = Field(default=None, max_length=200)
    action_id: str | None = Field(default=None, max_length=120)
    intent_payload: dict | None = None


class StartGameRequest(BaseModel):
    template_id: str = Field(default=DEFAULT_TEMPLATE_ID, max_length=80)
    seed_id: str | None = Field(default=None, max_length=120)


class LoadTemplateRequest(BaseModel):
    template: str = Field(..., min_length=1, max_length=80)
    template_id: str | None = Field(default=None, max_length=80)


class GeneratePortraitRequest(BaseModel):
    description: str = Field(..., min_length=3, max_length=800)


@app.get("/game/templates")
async def get_templates():
    return {"templates": list_templates()}


@app.post("/game/start")
async def start_game(body: StartGameRequest | None = None):
    try:
        tid = resolve_template_id(body.template_id if body else DEFAULT_TEMPLATE_ID)
        return await game_loop.start_new_game(
            tid,
            seed_id=(body.seed_id if body else None),
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/game/seeds")
async def get_seeds():
    return {"seeds": list_seeds()}


async def _start_demo_game():
    try:
        return await game_loop.start_new_demo_game("ravenford_demo")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/game/new-demo")
async def start_demo_game():
    """Ravenford 失踪商人 — 稳定演示种子开局。"""
    return await _start_demo_game()


@app.post("/api/game/new-demo")
async def start_demo_game_api_prefix():
    """与 /game/new-demo 相同（兼容 /api 前缀）。"""
    return await _start_demo_game()


async def _load_world_template(body: LoadTemplateRequest):
    tid = resolve_template_id(body.template_id or body.template)
    return await game_loop.start_new_game(tid)


@app.post("/game/load-template")
async def load_world_template_game(body: LoadTemplateRequest):
    """切换世界模板（与 /game/start 相同逻辑，供前端模板按钮调用）。"""
    try:
        return await _load_world_template(body)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/world/load-template")
async def load_world_template_api(body: LoadTemplateRequest):
    """切换世界模板 — /api 前缀兼容。"""
    try:
        return await _load_world_template(body)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


API_BUILD = "demo-action-id-v3"


@app.post("/game/action")
async def game_action(body: ActionRequest):
    # 双通道注入：参数 + 实例属性（兼容 reload 未刷新的旧 worker）
    game_loop._selected_choice_text = body.selected_choice_text
    game_loop._action_id = body.action_id
    game_loop._intent_payload = body.intent_payload
    try:
        if not game_loop.state:
            await game_loop._load()
        inp = (body.player_input or "").strip()
        aid = (body.action_id or "").strip()
        inv_action = aid.startswith("inv_")
        demo_action = bool(
            game_loop.state and game_loop.state.flags.get("demo_story_mode")
        )
        has_intent = bool(body.intent_payload)
        # 点击选项可为空；自由输入必须有文本
        if aid and not has_intent and not inv_action and not demo_action:
            raise HTTPException(
                status_code=400,
                detail="点击选项必须提供 intent_payload（不可仅传 label）",
            )
        if not inp and not has_intent and not aid:
            raise HTTPException(status_code=400, detail="player_input 不能为空（自由输入）")
        return await game_loop.process_action(
            inp,
            selected_choice_text=body.selected_choice_text,
            action_id=body.action_id,
            intent_payload=body.intent_payload,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        game_loop._selected_choice_text = None
        game_loop._action_id = None
        game_loop._intent_payload = None


class RewindRequest(BaseModel):
    turn: int = Field(..., ge=1, le=9999)


class ForkRequest(BaseModel):
    from_turn: int = Field(..., ge=1, le=9999)
    label: str | None = Field(default=None, max_length=80)


@app.post("/game/rewind")
async def rewind(body: RewindRequest):
    try:
        return await game_loop.rewind_to_turn(body.turn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/game/fork")
async def fork(body: ForkRequest):
    try:
        return await game_loop.fork_branch(from_turn=body.from_turn, label=body.label)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/game/branches")
async def branches():
    try:
        return {"branches": await db.list_branches()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/game/state")
async def get_state():
    try:
        return await game_loop.get_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/game/inspector")
async def get_inspector(turn: int | None = None):
    """
    开发者调试/证明面板：按回合聚合 action/dice/tick/scene_graph/event_beats/prompt/narrative。
    """
    try:
        rows = await db.get_events_range()
        if not rows:
            return {"initialized": False, "turns": [], "turn": None}

        turns = sorted({int(r["turn"]) for r in rows})
        use_turn = int(turn) if turn is not None else max(turns)
        if use_turn not in turns:
            use_turn = max(turns)

        per_turn = [r for r in rows if int(r["turn"]) == use_turn]
        by_type: dict[str, list[dict[str, Any]]] = {}
        for r in per_turn:
            by_type.setdefault(str(r["event_type"]), []).append(r)

        # final narrative：来自存档 narrative_log（而非 events meta），可证明“叙事输出”与其回合绑定
        state = await db.load_game_state()
        narrative_html = None
        if state:
            flags = (state.get("flags") or {}) if isinstance(state, dict) else {}
            log = flags.get("narrative_log")
            if isinstance(log, list):
                # 取本回合最后一条 narrative/prologue
                for ent in reversed(log):
                    if not isinstance(ent, dict):
                        continue
                    if int(ent.get("turn") or 0) != use_turn:
                        continue
                    if ent.get("kind") in ("narrative", "prologue"):
                        narrative_html = ent.get("html")
                        break

        action = (by_type.get("action") or [{}])[-1].get("payload") if by_type.get("action") else None
        dice = (by_type.get("dice_roll") or [{}])[-1].get("payload") if by_type.get("dice_roll") else None
        world_change = (by_type.get("world_change") or [{}])[-1].get("payload") if by_type.get("world_change") else None
        npc_memory_diff = (by_type.get("npc_memory_diff") or [{}])[-1].get("payload") if by_type.get("npc_memory_diff") else None
        sim_metrics_diff = (by_type.get("sim_metrics_diff") or [{}])[-1].get("payload") if by_type.get("sim_metrics_diff") else None
        narrative_proof = (by_type.get("narrative_proof") or [{}])[-1].get("payload") if by_type.get("narrative_proof") else None

        return {
            "initialized": True,
            "turns": turns,
            "turn": use_turn,
            "blocks": {
                "intent_parser": action,  # player_input + intent
                "rule_result": dice,
                "world_tick": world_change.get("world_tick_events") if isinstance(world_change, dict) else None,
                "world_change": world_change,
                "npc_memory_diff": npc_memory_diff,
                "sim_metrics_diff": sim_metrics_diff,
                "scene_graph": (
                    (narrative_proof or {}).get("payload_preview", {}).get("scene_graph")
                    if isinstance(narrative_proof, dict)
                    else None
                ),
                "event_beats": (
                    (narrative_proof or {}).get("payload_preview", {}).get("event_beats")
                    if isinstance(narrative_proof, dict)
                    else None
                ),
                "llm_prompt": {
                    "llm": (narrative_proof or {}).get("llm") if isinstance(narrative_proof, dict) else None,
                    "system_prompt_sha256": (narrative_proof or {}).get("system_prompt_sha256")
                    if isinstance(narrative_proof, dict)
                    else None,
                    "user_prompt_sha256": (narrative_proof or {}).get("user_prompt_sha256")
                    if isinstance(narrative_proof, dict)
                    else None,
                    "payload_sha256": (narrative_proof or {}).get("payload_sha256")
                    if isinstance(narrative_proof, dict)
                    else None,
                    "system_prompt": (narrative_proof or {}).get("system_prompt") if isinstance(narrative_proof, dict) else None,
                    "user_prompt": (narrative_proof or {}).get("user_prompt") if isinstance(narrative_proof, dict) else None,
                },
                "final_narrative": narrative_html,
                "narrative_sha256": (narrative_proof or {}).get("narrative_sha256")
                if isinstance(narrative_proof, dict)
                else None,
            },
            "raw_events": per_turn,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.websocket("/ws/images/{template_id}")
async def ws_images(websocket: WebSocket, template_id: str):
    await image_ws_hub.connect(template_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        image_ws_hub.disconnect(template_id, websocket)


@app.post("/game/generate-portrait")
async def generate_portrait_endpoint(body: GeneratePortraitRequest):
    """可选：玩家自定义肖像，走同一 MD5 缓存逻辑。"""
    try:
        if not game_loop.state:
            raise HTTPException(status_code=400, detail="请先开始游戏")

        from engine.world_templates import finalize_image_prompt, get_art_style

        tid = game_loop.state.flags.get("template_id", DEFAULT_TEMPLATE_ID)
        art = get_art_style(tid)
        prompt = finalize_image_prompt(
            f"Portrait of fantasy RPG hero, {body.description}, {art}, square format",
            tid,
        )
        ph, url = await get_or_generate(prompt, "portrait", entity_id="player:portrait")

        if game_loop.state:
            game_loop.state.player.portrait_url = url
            game_loop.state.player.portrait_asset_key = ph
            reg = game_loop.state.flags.get("image_entities", {})
            if isinstance(reg, dict) and "player:portrait" in reg:
                reg["player:portrait"]["prompt_hash"] = ph
                reg["player:portrait"]["prompt"] = prompt
            await game_loop._persist()

        await image_ws_hub.broadcast(
            tid,
            {"entity_id": "player:portrait", "url": url, "prompt_hash": ph},
        )
        return {"url": url, "portrait_asset_key": ph, "cached": url != placeholder_url()}
    except ImageGenerationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
async def health():
    rows = await list_image_assets()
    cached_files = sum(1 for r in rows if get_image_url(r["prompt_hash"]))
    return {
        "status": "ok",
        "api_build": API_BUILD,
        "llm_configured": is_llm_configured(),
        "model": get_llm_model(),
        "image_configured": is_image_configured(),
        "image_model": get_image_model(),
        "image_mode": "template_hash_cache",
        "ai_images_enabled": is_ai_images_enabled(),
        "cached_images": cached_files,
    }


@app.get("/dev/template-check")
async def template_check(template_id: str | None = None):
    """模板质量校验：检查跨题材残留词。"""
    try:
        if template_id:
            tid = resolve_template_id(template_id)
            items = scan_template(tid)
            return {"template_id": tid, "findings": [f.__dict__ for f in items], "count": len(items)}
        results = scan_all()
        packed = {
            tid: {"count": len(items), "findings": [f.__dict__ for f in items]}
            for tid, items in results.items()
        }
        return {"results": packed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

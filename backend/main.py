"""FastAPI 入口 — Dynamic World Simulation Engine。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

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
    player_input: str = Field(..., min_length=1, max_length=500)


class StartGameRequest(BaseModel):
    template_id: str = Field(default=DEFAULT_TEMPLATE_ID, max_length=80)


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
        return await game_loop.start_new_game(tid)
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


@app.post("/game/action")
async def game_action(body: ActionRequest):
    try:
        return await game_loop.process_action(body.player_input.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/game/state")
async def get_state():
    try:
        return await game_loop.get_state()
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
        "llm_configured": is_llm_configured(),
        "model": get_llm_model(),
        "image_configured": is_image_configured(),
        "image_model": get_image_model(),
        "image_mode": "template_hash_cache",
        "ai_images_enabled": is_ai_images_enabled(),
        "cached_images": cached_files,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

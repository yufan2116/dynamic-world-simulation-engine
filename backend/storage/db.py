"""SQLite 持久化 — MVP 单会话。"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "save_game.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS game_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    seed_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    parent_branch_id TEXT,
    fork_turn INTEGER,
    label TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS snapshots (
    branch_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    events_json TEXT NOT NULL,
    rng_state_b64 TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (branch_id, turn)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS npc_memories (
    npc_name TEXT PRIMARY KEY,
    memories_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    cache_key TEXT PRIMARY KEY,
    image_type TEXT NOT NULL,
    url TEXT NOT NULL,
    prompt TEXT,
    style TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS image_assets (
    prompt_hash TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


async def _migrate_image_assets_table(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(image_assets)") as cur:
        cols = [row[1] async for row in cur]
    if cols and "prompt_hash" not in cols:
        await db.execute("DROP TABLE image_assets")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await _migrate_image_assets_table(db)
        await db.executescript(SCHEMA)
        await db.commit()


async def save_image_asset(
    prompt_hash: str,
    prompt: str,
    asset_type: str,
    file_path: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO image_assets (prompt_hash, prompt, type, file_path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(prompt_hash) DO UPDATE SET
                prompt = excluded.prompt,
                type = excluded.type,
                file_path = excluded.file_path,
                created_at = CURRENT_TIMESTAMP
            """,
            (prompt_hash, prompt, asset_type, file_path),
        )
        await db.commit()


async def get_image_asset(prompt_hash: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT prompt_hash, prompt, type, file_path, created_at FROM image_assets WHERE prompt_hash = ?",
            (prompt_hash,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)


async def list_image_assets() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT prompt_hash, prompt, type, file_path, created_at FROM image_assets"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def save_game_state(state_dict: dict[str, Any]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO game_state (id, state_json) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json,
            updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(state_dict, ensure_ascii=False),),
        )
        await db.commit()


async def load_game_state() -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT state_json FROM game_state WHERE id = 1") as cur:
            row = await cur.fetchone()
            if row:
                return json.loads(row["state_json"])
    return None


async def clear_game() -> None:
    """清空存档；优先删表数据，避免 Windows 下文件被占用时删除失败。"""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM game_state")
        await db.execute("DELETE FROM branches")
        await db.execute("DELETE FROM snapshots")
        await db.execute("DELETE FROM events")
        await db.execute("DELETE FROM npc_memories")
        await db.execute("DELETE FROM images")
        await db.commit()


async def insert_event(turn: int, event_type: str, payload: dict[str, Any]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events (turn, event_type, payload_json) VALUES (?, ?, ?)",
            (turn, event_type, json.dumps(payload, ensure_ascii=False)),
        )
        await db.commit()


async def clear_events() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM events")
        await db.commit()


async def insert_events_bulk(rows: list[dict[str, Any]]) -> None:
    """按顺序批量写回 events（用于 rewind/fork 恢复）。"""
    if not rows:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        for r in rows:
            await db.execute(
                "INSERT INTO events (turn, event_type, payload_json, created_at) VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
                (
                    int(r.get("turn", 0)),
                    str(r.get("event_type", "")),
                    json.dumps(r.get("payload", {}), ensure_ascii=False),
                    r.get("created_at"),
                ),
            )
        await db.commit()


async def get_events(limit: int = 100) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT turn, event_type, payload_json, created_at FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for row in reversed(rows):
        result.append(
            {
                "turn": row["turn"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )
    return result


async def get_events_range(*, from_turn: int | None = None, to_turn: int | None = None) -> list[dict[str, Any]]:
    """按回合区间读取 events（正序）。"""
    q = "SELECT turn, event_type, payload_json, created_at FROM events"
    params: list[Any] = []
    where: list[str] = []
    if from_turn is not None:
        where.append("turn >= ?")
        params.append(int(from_turn))
    if to_turn is not None:
        where.append("turn <= ?")
        params.append(int(to_turn))
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id ASC"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(q, params) as cur:
            rows = await cur.fetchall()

    return [
        {
            "turn": r["turn"],
            "event_type": r["event_type"],
            "payload": json.loads(r["payload_json"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def create_branch(
    *,
    seed_id: str,
    template_id: str,
    parent_branch_id: str | None = None,
    fork_turn: int | None = None,
    label: str | None = None,
) -> str:
    branch_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO branches (branch_id, seed_id, template_id, parent_branch_id, fork_turn, label)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (branch_id, seed_id, template_id, parent_branch_id, fork_turn, label),
        )
        await db.commit()
    return branch_id


async def list_branches() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT branch_id, seed_id, template_id, parent_branch_id, fork_turn, label, created_at
            FROM branches ORDER BY created_at ASC
            """
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def save_snapshot(
    *,
    branch_id: str,
    turn: int,
    state_dict: dict[str, Any],
    events: list[dict[str, Any]],
    rng_state_b64: str | None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO snapshots (branch_id, turn, state_json, events_json, rng_state_b64)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(branch_id, turn) DO UPDATE SET
                state_json = excluded.state_json,
                events_json = excluded.events_json,
                rng_state_b64 = excluded.rng_state_b64,
                created_at = CURRENT_TIMESTAMP
            """,
            (
                branch_id,
                int(turn),
                json.dumps(state_dict, ensure_ascii=False),
                json.dumps(events, ensure_ascii=False),
                rng_state_b64,
            ),
        )
        await db.commit()


async def load_snapshot(*, branch_id: str, turn: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT branch_id, turn, state_json, events_json, rng_state_b64, created_at FROM snapshots WHERE branch_id = ? AND turn = ?",
            (branch_id, int(turn)),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "branch_id": row["branch_id"],
                "turn": row["turn"],
                "state": json.loads(row["state_json"]),
                "events": json.loads(row["events_json"]),
                "rng_state_b64": row["rng_state_b64"],
                "created_at": row["created_at"],
            }


async def list_snapshots(branch_id: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT turn FROM snapshots WHERE branch_id = ? ORDER BY turn ASC",
            (branch_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [int(r[0]) for r in rows]


async def save_npc_memories(npcs: dict[str, list[str]]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        for name, memories in npcs.items():
            await db.execute(
                """
                INSERT INTO npc_memories (npc_name, memories_json) VALUES (?, ?)
                ON CONFLICT(npc_name) DO UPDATE SET memories_json = excluded.memories_json
                """,
                (name, json.dumps(memories, ensure_ascii=False)),
            )
        await db.commit()


async def load_npc_memories() -> dict[str, list[str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT npc_name, memories_json FROM npc_memories") as cur:
            rows = await cur.fetchall()
    return {row["npc_name"]: json.loads(row["memories_json"]) for row in rows}


async def get_cached_image(cache_key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT url FROM images WHERE cache_key = ?", (cache_key,)
        ) as cur:
            row = await cur.fetchone()
            return row["url"] if row else None


async def save_cached_image(
    cache_key: str,
    image_type: str,
    url: str,
    prompt: str = "",
    style: str = "",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO images (cache_key, image_type, url, prompt, style)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                url = excluded.url,
                prompt = excluded.prompt,
                style = excluded.style,
                created_at = CURRENT_TIMESTAMP
            """,
            (cache_key, image_type, url, prompt, style),
        )
        await db.commit()


async def list_images_by_type(image_type: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT cache_key, url, style, created_at FROM images WHERE image_type = ?",
            (image_type,),
        ) as cur:
            rows = await cur.fetchall()
    return [
        {
            "cache_key": r["cache_key"],
            "url": r["url"],
            "style": r["style"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]

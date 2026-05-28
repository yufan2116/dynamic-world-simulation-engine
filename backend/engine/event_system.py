"""事件记录系统。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from storage import db


class GameEvent(BaseModel):
    turn: int
    event_type: str  # action | dice_roll | world_change | narrative
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventSystem:
    def __init__(self) -> None:
        self._events: list[GameEvent] = []
        self._turn: int = 0

    @property
    def turn(self) -> int:
        return self._turn

    def next_turn(self) -> int:
        self._turn += 1
        return self._turn

    def reset(self) -> None:
        self._events.clear()
        self._turn = 0

    async def record(self, event_type: str, payload: dict[str, Any]) -> GameEvent:
        turn = self._turn if event_type == "action" else self._turn
        event = GameEvent(turn=turn, event_type=event_type, payload=payload)
        self._events.append(event)
        await db.insert_event(turn, event_type, payload)
        return event

    async def record_action(self, player_input: str, intent: dict[str, Any]) -> GameEvent:
        return await self.record("action", {"player_input": player_input, "intent": intent})

    async def record_dice(self, dice_info: dict[str, Any]) -> GameEvent:
        return await self.record("dice_roll", dice_info)

    async def record_world_change(self, changes: dict[str, Any]) -> GameEvent:
        return await self.record("world_change", changes)

    async def record_narrative_meta(self, meta: dict[str, Any]) -> GameEvent:
        return await self.record("narrative", meta)

    def list_events(self) -> list[dict[str, Any]]:
        return [e.model_dump() for e in self._events]

    async def load_from_db(self) -> None:
        rows = await db.get_events(limit=500)
        self._events = [
            GameEvent(
                turn=r["turn"],
                event_type=r["event_type"],
                payload=r["payload"],
            )
            for r in rows
        ]
        if self._events:
            self._turn = max(e.turn for e in self._events)

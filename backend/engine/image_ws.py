"""图像生成完成 WebSocket 广播。"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ImageWsHub:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, template_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._rooms.setdefault(template_id, set()).add(websocket)

    def disconnect(self, template_id: str, websocket: WebSocket) -> None:
        room = self._rooms.get(template_id)
        if room:
            room.discard(websocket)
            if not room:
                del self._rooms[template_id]

    async def broadcast(self, template_id: str, message: dict[str, Any]) -> None:
        room = self._rooms.get(template_id)
        if not room:
            return
        payload = json.dumps(message, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(template_id, ws)


image_ws_hub = ImageWsHub()

"""WebSocket broadcaster: fan-out LangGraph state events to connected FE clients."""

import asyncio
import json
from collections import defaultdict
from pydantic import BaseModel

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class _PydanticEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        return super().default(obj)


def _dumps(obj: object) -> str:
    return json.dumps(obj, cls=_PydanticEncoder)


# project_id -> set of active WebSocket connections
_connections: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


async def broadcast(project_id: str, message: dict) -> None:
    payload = _dumps(message)
    async with _lock:
        dead = set()
        for ws in _connections.get(project_id, set()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        _connections[project_id] -= dead


@router.websocket("/ws/project/{project_id}")
async def ws_endpoint(websocket: WebSocket, project_id: str):
    await websocket.accept()
    async with _lock:
        _connections[project_id].add(websocket)
    try:
        while True:
            # Keep alive; client can send pings or we rely on TCP
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            _connections[project_id].discard(websocket)

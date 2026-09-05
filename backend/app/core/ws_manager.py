import asyncio
import json

from fastapi import WebSocket


class ConnectionManager:
    """Per-user WebSocket fan-out for sync-completion / recommendation-refresh notifications."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(ws)

    async def disconnect(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns and ws in conns:
                conns.discard(ws)
                if not conns:
                    self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict) -> int:
        conns = list(self._connections.get(user_id, set()))
        sent = 0
        payload = json.dumps(message)
        for ws in conns:
            try:
                await ws.send_text(payload)
                sent += 1
            except Exception:
                await self.disconnect(user_id, ws)
        return sent


manager = ConnectionManager()

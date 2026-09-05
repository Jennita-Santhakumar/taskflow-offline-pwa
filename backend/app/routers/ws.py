from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.core.ws_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket, token: str) -> None:
    try:
        payload = decode_token(token, expected_type="access")
    except Exception:
        await websocket.close(code=4401)
        return
    user_id = payload["sub"]
    await manager.connect(user_id, websocket)
    try:
        while True:
            # Client doesn't need to send anything; keep the connection alive and just listen for
            # disconnects. Echo pings for basic liveness debugging.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)

"""WebSocket endpoint for real-time dashboard updates."""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
import structlog

from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that streams real-time flaky test events.
    Subscribes to Redis pub/sub channel and forwards to connected clients.
    """
    await manager.connect(websocket)

    redis_client = aioredis.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("flaky_events")

    # Send welcome message
    await websocket.send_text(json.dumps({
        "type": "connected",
        "message": "Connected to Flaky Test Detector real-time stream",
    }))

    try:
        async def listen_redis():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await manager.broadcast(data)

        async def listen_ws():
            while True:
                try:
                    msg = await websocket.receive_text()
                    # Handle ping
                    if msg == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        await asyncio.gather(listen_redis(), listen_ws())

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected")
    except Exception as e:
        logger.error("ws_error", error=str(e))
    finally:
        manager.disconnect(websocket)
        await pubsub.unsubscribe("flaky_events")
        await redis_client.aclose()
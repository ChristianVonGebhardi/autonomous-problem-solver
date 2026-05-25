import json
from typing import Dict, List, Set
from fastapi import WebSocket
import structlog

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        # Map of user_id -> set of active WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info("ws_connected", user_id=user_id, connections=len(self.active_connections[user_id]))

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info("ws_disconnected", user_id=user_id)

    async def send_to_user(self, user_id: str, message: dict):
        """Send a JSON message to all connections for a user."""
        if user_id not in self.active_connections:
            return
        
        dead_connections = set()
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.warning("ws_send_error", error=str(e))
                dead_connections.add(connection)
        
        # Clean up dead connections
        self.active_connections[user_id] -= dead_connections

    async def broadcast(self, message: dict):
        """Broadcast to all connected users."""
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, message)


# Global connection manager instance
manager = ConnectionManager()
"""WebSocket endpoints for real-time data streaming."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging

from app.core.gateway_manager import gateway_manager

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to websocket: {e}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        for connection in dead_connections:
            if connection in self.active_connections:
                self.active_connections.remove(connection)


manager = ConnectionManager()


@router.websocket("/aggregate")
async def websocket_aggregate(websocket: WebSocket):
    """Stream aggregated data to client."""
    await manager.connect(websocket)
    try:
        while True:
            # Send aggregate data every second
            data = gateway_manager.get_aggregate_data()
            await websocket.send_json(data.model_dump())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/gateway/{gateway_id}")
async def websocket_gateway(websocket: WebSocket, gateway_id: str):
    """Stream data for a specific gateway."""
    await websocket.accept()
    try:
        while True:
            status = gateway_manager.get_gateway(gateway_id)
            if status:
                await websocket.send_json(status.model_dump())
            else:
                await websocket.send_json({"error": "Gateway not found"})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        # Normal client disconnect - no action needed
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

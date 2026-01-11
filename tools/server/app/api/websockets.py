"""
WebSocket Endpoints for Real-Time Data Streaming

Provides WebSocket connections for live updates of Powerwall data without polling.
All routes are prefixed with /ws (configured in main.py).

Routes:
    - WS /ws/aggregate            -> Real-time aggregated data from all gateways
    - WS /ws/gateway/{gateway_id} -> Real-time data for specific gateway
    
Connection Flow:
    1. Client connects to WebSocket endpoint
    2. Server accepts connection and adds to active connections
    3. Server pushes JSON data every 1 second
    4. Connection remains open until client disconnects or error occurs
    5. Dead connections are automatically cleaned up

Data Format:
    - Aggregate endpoint: AggregateData model (all gateways combined)
    - Gateway endpoint: GatewayStatus model (single gateway data)
    
Usage Example:
    JavaScript:
        const ws = new WebSocket('ws://localhost:8580/ws/aggregate');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Battery:', data.total_battery_percent);
        };
    
    Python:
        import websockets
        async with websockets.connect('ws://localhost:8580/ws/gateway/default') as ws:
            while True:
                data = await ws.recv()
                print(json.loads(data))

Design Notes:
    - Updates push every 1 second (no client polling needed)
    - Graceful handling of client disconnects (no errors logged)
    - Automatic cleanup of broken connections
    - ConnectionManager broadcasts to all clients efficiently
    - Empty except blocks are intentional (normal disconnect flow)
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging

from app.core.gateway_manager import gateway_manager

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for broadcasting data.
    
    Maintains a list of active WebSocket connections and provides methods
    for connecting, disconnecting, and broadcasting messages to all clients.
    
    Automatically cleans up dead connections during broadcast to prevent
    memory leaks from clients that disconnect without proper close handshake.
    """
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection from active list."""
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients.
        
        Automatically detects and removes dead connections that fail to
        receive data. This handles cases where clients disconnect without
        sending a proper WebSocket close frame.
        """
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
    """
    Stream aggregated data from all gateways to client.
    
    WebSocket endpoint: /ws/aggregate
    
    Pushes combined battery, power, and energy data from all configured
    gateways every second. Useful for dashboard displays showing total
    system capacity and performance.
    
    Data includes:
        - total_battery_percent: Combined battery level
        - total_battery_capacity: Total kWh capacity
        - total_site_power: Combined grid power
        - total_battery_power: Combined battery charge/discharge
        - total_load_power: Combined load consumption
    """
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
        logger.error(f"WebSocket error (aggregate): {type(e).__name__}: {e}")
        manager.disconnect(websocket)


@router.websocket("/gateway/{gateway_id}")
async def websocket_gateway(websocket: WebSocket, gateway_id: str):
    """
    Stream data for a specific gateway to client.
    
    WebSocket endpoint: /ws/gateway/{gateway_id}
    
    Pushes complete gateway status including vitals, aggregates, battery
    level, and online status every second. Use this for monitoring a
    specific Powerwall system in detail.
    
    Args:
        gateway_id: Gateway identifier (e.g., "default", "home", "cabin")
        
    Returns error message if gateway_id is not found or goes offline.
    """
    await manager.connect(websocket)
    try:
        while True:
            status = gateway_manager.get_gateway(gateway_id)
            if status:
                await websocket.send_json(status.model_dump())
            else:
                await websocket.send_json({"error": "Gateway not found"})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error (gateway={gateway_id}): {type(e).__name__}: {e}")
        manager.disconnect(websocket)

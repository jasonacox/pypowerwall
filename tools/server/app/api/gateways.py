"""
Multi-Gateway Management API

REST API for managing multiple Powerwall gateways and querying per-gateway data.
All routes are prefixed with /api/gateways (configured in main.py).

Routes:
    - GET  /api/gateways/              -> List all configured gateways
    - GET  /api/gateways/{id}          -> Get specific gateway status
    - POST /api/gateways/{id}/control  -> Control operations for specific gateway
    
Design Notes:
    - Router prefix prevents conflicts with legacy routes
    - The @router.get("/") here becomes /api/gateways/ (NOT root /)
    - Each gateway can be queried independently
    - Control operations support per-gateway targeting
"""
from fastapi import APIRouter, HTTPException
from typing import Dict

from app.core.gateway_manager import gateway_manager
from app.models.gateway import GatewayStatus

router = APIRouter()


@router.get("/", response_model=Dict[str, GatewayStatus])
async def list_gateways():
    """List all configured gateways and their status."""
    return gateway_manager.get_all_gateways()


@router.get("/{gateway_id}", response_model=GatewayStatus)
async def get_gateway(gateway_id: str):
    """Get status for a specific gateway."""
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    return status


@router.get("/{gateway_id}/vitals")
async def get_gateway_vitals(gateway_id: str):
    """Get vitals for a specific gateway.
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    if not status.data:
        return {}
    
    return status.data.vitals or {}


@router.get("/{gateway_id}/strings")
async def get_gateway_strings(gateway_id: str):
    """Get strings for a specific gateway.
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    if not status.data:
        return {}
    
    return status.data.strings or {}


@router.get("/{gateway_id}/aggregates")
async def get_gateway_aggregates(gateway_id: str):
    """Get aggregates for a specific gateway.
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    if not status.data:
        return {}
    
    return status.data.aggregates or {}


@router.get("/{gateway_id}/api/{path:path}")
async def proxy_gateway_api(gateway_id: str, path: str):
    """Proxy API calls to a specific gateway.
    
    Args:
        gateway_id: Gateway identifier
        path: API path to proxy (e.g., "meters/aggregates")
        
    Returns:
        JSON response from the gateway API
        
    Raises:
        HTTPException 404: Gateway not found
        HTTPException 503: API call failed or gateway offline
    """
    if gateway_id not in gateway_manager.gateways:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    result = await gateway_manager.call_api(gateway_id, 'poll', f"/api/{path}", timeout=10.0)
    if result is None:
        raise HTTPException(status_code=503, detail="API call failed or gateway offline")
    return result


@router.post("/{gateway_id}/api/{path:path}")
async def proxy_gateway_api_post(gateway_id: str, path: str, data: dict):
    """Proxy POST requests to a specific gateway.
    
    Args:
        gateway_id: Gateway identifier
        path: API path to proxy
        data: JSON payload to send
        
    Returns:
        JSON response from the gateway API
        
    Raises:
        HTTPException 404: Gateway not found
        HTTPException 503: API call failed or gateway offline
    """
    if gateway_id not in gateway_manager.gateways:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    result = await gateway_manager.call_api(gateway_id, 'post', f"/api/{path}", data, timeout=10.0)
    if result is None:
        raise HTTPException(status_code=503, detail="API call failed or gateway offline")
    return result

"""Multi-gateway API endpoints."""
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
    """Get vitals for a specific gateway."""
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    if not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    return status.data.vitals or {}


@router.get("/{gateway_id}/strings")
async def get_gateway_strings(gateway_id: str):
    """Get strings for a specific gateway."""
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    if not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    return status.data.strings or {}


@router.get("/{gateway_id}/aggregates")
async def get_gateway_aggregates(gateway_id: str):
    """Get aggregates for a specific gateway."""
    status = gateway_manager.get_gateway(gateway_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    if not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    return status.data.aggregates or {}


@router.get("/{gateway_id}/api/{path:path}")
async def proxy_gateway_api(gateway_id: str, path: str):
    """Proxy API calls to a specific gateway."""
    pw = gateway_manager.get_connection(gateway_id)
    if not pw:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    try:
        result = pw.poll(f"/api/{path}")
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"API call failed: {str(e)}")


@router.post("/{gateway_id}/api/{path:path}")
async def proxy_gateway_api_post(gateway_id: str, path: str, data: dict):
    """Proxy POST requests to a specific gateway."""
    pw = gateway_manager.get_connection(gateway_id)
    if not pw:
        raise HTTPException(status_code=404, detail=f"Gateway {gateway_id} not found")
    
    try:
        result = pw.post(f"/api/{path}", data)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"API call failed: {str(e)}")

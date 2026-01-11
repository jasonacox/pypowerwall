"""Aggregate data API endpoints."""
from fastapi import APIRouter

from app.core.gateway_manager import gateway_manager
from app.models.gateway import AggregateData

router = APIRouter()


@router.get("/", response_model=AggregateData)
async def get_aggregate():
    """Get aggregated data from all gateways."""
    return gateway_manager.get_aggregate_data()


@router.get("/power")
async def get_aggregate_power():
    """Get aggregated power flows."""
    data = gateway_manager.get_aggregate_data()
    return {
        "site": data.total_site_power,
        "battery": data.total_battery_power,
        "load": data.total_load_power,
        "solar": data.total_solar_power,
        "grid": data.total_grid_power,
        "timestamp": data.timestamp
    }


@router.get("/soe")
async def get_aggregate_soe():
    """Get average state of energy across all gateways."""
    data = gateway_manager.get_aggregate_data()
    return {
        "percentage": data.total_battery_percent,
        "num_gateways": data.num_online,
        "timestamp": data.timestamp
    }

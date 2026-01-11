"""
Aggregate Data API Endpoints

REST API for querying combined data from multiple Powerwall gateways.
All routes are prefixed with /api/aggregate (configured in main.py).

Routes:
    - GET /api/aggregate/        -> Complete aggregated data (all metrics)
    - GET /api/aggregate/power   -> Power flows only (site, battery, load, solar, grid)
    - GET /api/aggregate/soe     -> Average battery level across all gateways
    - GET /api/aggregate/battery -> Battery capacity and charge information

Use Cases:
    - Dashboard displaying total system capacity
    - Monitoring multiple Powerwall installations as single system
    - Historical data collection for combined systems
    - Load balancing across multiple sites

Data Aggregation:
    - Battery percentages are averaged across online gateways
    - Power values (W) are summed across all gateways
    - Capacity values (Wh) are summed across all gateways
    - Only online gateways contribute to aggregates
    - Timestamps reflect most recent update across all gateways

Design Notes:
    - All data comes from cached gateway states (no blocking calls)
    - Returns immediately even if gateways are offline
    - Offline gateways are excluded from calculations
    - num_online field indicates how many gateways contributed
"""
from fastapi import APIRouter

from app.core.gateway_manager import gateway_manager
from app.models.gateway import AggregateData

router = APIRouter()


@router.get("/", response_model=AggregateData)
async def get_aggregate():
    """
    Get complete aggregated data from all gateways.
    
    Returns all combined metrics including battery levels, power flows,
    and capacity information from all online gateways.
    
    Response includes:
        - total_battery_percent: Average battery level (%)
        - total_battery_capacity: Combined capacity (Wh)
        - total_site_power: Combined site power (W)
        - total_battery_power: Combined battery charge/discharge (W)
        - total_load_power: Combined load consumption (W)
        - total_solar_power: Combined solar generation (W)
        - total_grid_power: Combined grid import/export (W)
        - num_online: Number of contributing gateways
        - timestamp: Most recent data timestamp
    """
    return gateway_manager.get_aggregate_data()


@router.get("/power")
async def get_aggregate_power():
    """
    Get aggregated power flows from all gateways.
    
    Returns simplified power flow data suitable for real-time monitoring
    and graphing. All values in watts (W).
    
    Response includes:
        - site: Total site power (grid interaction)
        - battery: Total battery power (+ charging, - discharging)
        - load: Total home/facility load consumption
        - solar: Total solar generation
        - grid: Total grid import/export
        - timestamp: Data timestamp
    """
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
    """
    Get average state of energy (battery level) across all gateways.
    
    Returns simplified battery status useful for quick status checks
    and alerting systems.
    
    Response includes:
        - percentage: Average battery level across all online gateways (0-100%)
        - num_gateways: Number of online gateways contributing to average
        - timestamp: Data timestamp
    
    Note: Offline gateways are excluded from the percentage calculation.
    """
    data = gateway_manager.get_aggregate_data()
    return {
        "percentage": data.total_battery_percent,
        "num_gateways": data.num_online,
        "timestamp": data.timestamp
    }


@router.get("/battery")
async def get_aggregate_battery():
    """
    Get aggregated battery capacity and charge information.
    
    Returns battery-specific metrics useful for capacity planning
    and charge state monitoring.
    
    Response includes:
        - total_capacity: Combined battery capacity in Wh
        - battery_percent: Average state of charge (0-100%)
        - battery_power: Combined charge/discharge power in watts (+ discharge, - charge)
        - num_gateways: Total configured gateways
        - num_online: Currently connected gateways
        - timestamp: Data timestamp
    """
    data = gateway_manager.get_aggregate_data()
    return {
        "total_capacity": data.total_battery_capacity,
        "battery_percent": data.total_battery_percent,
        "battery_power": data.total_battery_power,
        "num_gateways": data.num_gateways,
        "num_online": data.num_online,
        "timestamp": data.timestamp
    }

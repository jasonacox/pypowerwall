"""Pydantic models for gateway configuration and data."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Gateway(BaseModel):
    """Represents a Powerwall gateway configuration."""
    id: str
    name: str
    host: Optional[str] = None
    gw_pwd: Optional[str] = None  # Gateway Wi-Fi password for TEDAPI
    email: Optional[str] = None
    timezone: str = "America/Los_Angeles"
    cloud_mode: bool = False
    fleetapi: bool = False
    online: bool = False
    last_error: Optional[str] = None


class PowerwallData(BaseModel):
    """Powerwall metrics data."""
    vitals: Optional[Dict[str, Any]] = None
    strings: Optional[Dict[str, Any]] = None
    aggregates: Optional[Dict[str, Any]] = None
    soe: Optional[float] = None  # State of Energy
    freq: Optional[float] = None
    din: Optional[str] = None
    uptime: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None  # Status string like "Running"
    device_type: Optional[str] = None
    timestamp: Optional[float] = None


class GatewayStatus(BaseModel):
    """Status information for a gateway."""
    gateway: Gateway
    data: Optional[PowerwallData] = None
    online: bool
    last_updated: Optional[float] = None
    error: Optional[str] = None


class AggregateData(BaseModel):
    """Aggregated data from multiple gateways."""
    total_battery_percent: float = 0.0
    total_battery_capacity: float = 0.0
    total_site_power: float = 0.0
    total_battery_power: float = 0.0
    total_load_power: float = 0.0
    total_solar_power: float = 0.0
    total_grid_power: float = 0.0
    num_gateways: int = 0
    num_online: int = 0
    gateways: Dict[str, GatewayStatus] = Field(default_factory=dict)
    timestamp: float = 0.0

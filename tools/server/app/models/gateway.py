"""Pydantic models for gateway configuration and data."""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class Gateway(BaseModel):
    """Represents a Powerwall gateway configuration.
    
    This model defines connection parameters for a single Powerwall gateway.
    It supports multiple authentication modes:
    
    TEDAPI Mode (Local):
        - Requires: host, gw_pwd
        - Fastest, most reliable
        - Example: Gateway(id="home", host="192.168.91.1", gw_pwd="password")
    
    Cloud Mode:
        - Requires: email, cloud_mode=True
        - Remote access from anywhere
        - Example: Gateway(id="remote", email="user@example.com", cloud_mode=True)
    
    FleetAPI Mode:
        - Requires: email, fleetapi=True
        - Official Tesla API
        - Example: Gateway(id="fleet", email="user@example.com", fleetapi=True)
    
    Attributes:
        id: Unique identifier for the gateway (used in URLs)
        name: Human-readable display name
        host: IP address or hostname (TEDAPI mode only)
        gw_pwd: Gateway WiFi password for local access (TEDAPI mode only)
        email: Tesla account email (Cloud/FleetAPI modes)
        timezone: Local timezone for timestamp conversion
        cloud_mode: Enable Tesla Cloud API access
        fleetapi: Enable Tesla FleetAPI access
        online: Current connection status (updated by gateway_manager)
        last_error: Most recent error message if connection failed
    """
    id: str
    name: str
    host: Optional[str] = None
    gw_pwd: Optional[str] = None  # Gateway Wi-Fi password for TEDAPI
    email: Optional[str] = None
    site_id: Optional[str] = None  # Tesla Site ID (populated after connection)
    timezone: str = "America/Los_Angeles"
    cloud_mode: bool = False
    fleetapi: bool = False
    online: bool = False
    last_error: Optional[str] = None


class PowerwallData(BaseModel):
    """Powerwall metrics and telemetry data.
    
    Contains all data collected from a Powerwall gateway during a polling cycle.
    Fields are Optional to handle cases where specific data is unavailable.
    
    Data Categories:
    
        Energy Flow (aggregates):
            - site: Grid connection power (positive = importing)
            - battery: Battery power (positive = discharging)
            - solar: Solar production power
            - load: Home consumption power
            All values in watts (W)
        
        Battery State:
            - soe: State of Energy (0-100%)
            - Battery capacity and reserve settings
        
        Device Vitals:
            - Temperatures (°C)
            - Voltages (V)
            - Currents (A)
            - Component status
        
        Solar Strings:
            - Individual string voltages
            - String currents
            - MPPT status
        
        System Info:
            - Software version
            - Uptime duration
            - Operating status
            - Device type
    
    Attributes:
        vitals: Device-level telemetry (temps, voltages, currents)
        strings: Solar string data (voltages, currents per string)
        aggregates: Energy flow data (site, battery, solar, load, grid)
        soe: State of Energy as percentage (0.0-100.0)
        freq: Grid frequency in Hz (typically 50 or 60)
        din: Device Identification Number
        uptime: System uptime string (e.g., "5d 3h 42m")
        version: Powerwall firmware version
        status: Operating status string (e.g., "Running", "Standby")
        device_type: Device model (e.g., "Gateway", "Powerwall 2")
        timestamp: Unix timestamp when data was collected
    
    Usage:
        data = PowerwallData(
            soe=85.5,
            aggregates={"site": 1500, "battery": -800, "solar": 2300},
            status="Running"
        )
    """
    vitals: Optional[Dict[str, Any]] = None
    strings: Optional[Dict[str, Any]] = None
    aggregates: Optional[Dict[str, Any]] = None
    alerts: Optional[List[str]] = None  # Active alert codes
    temps: Optional[Dict[str, Any]] = None  # Temperature readings
    grid_status: Optional[str] = None  # "UP", "DOWN", etc.
    reserve: Optional[float] = None  # Backup reserve percentage
    time_remaining: Optional[float] = None  # Hours of backup remaining
    system_status: Optional[Dict[str, Any]] = None  # Full system status for /pod
    fan_speeds: Optional[Dict[str, Any]] = None  # Fan speed data from TEDAPI
    networks: Optional[List[Any]] = None  # Network configuration
    powerwalls: Optional[Dict[str, Any]] = None  # Powerwalls list
    soe: Optional[float] = None  # State of Energy
    freq: Optional[float] = None
    din: Optional[str] = None
    uptime: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None  # Status string like "Running"
    device_type: Optional[str] = None
    timestamp: Optional[float] = None


class GatewayStatus(BaseModel):
    """Complete status snapshot for a single gateway.
    
    Combines gateway configuration, current data, and connection status into
    a single object. This is the primary response model for gateway endpoints.
    
    Lifecycle:
        1. Gateway created from configuration (GatewayConfig)
        2. Background polling attempts connection
        3. On success: online=True, data populated, last_updated set
        4. On failure: online=False, data=None, error message set
        5. Status returned by API endpoints and WebSocket streams
    
    Attributes:
        gateway: Gateway configuration and settings
        data: Latest metrics from the gateway (None if offline/failed)
        online: Whether gateway is currently reachable
        last_updated: Unix timestamp of last successful data collection
        error: Error message from last connection attempt (None if successful)
    
    Usage:
        # Check if data is available before accessing
        status = gateway_manager.get_gateway("home")
        if status.online and status.data:
            battery_level = status.data.soe
            print(f"Battery at {battery_level}%")
        else:
            print(f"Gateway offline: {status.error}")
    
    Thread Safety:
        This is an immutable snapshot. Gateway manager creates new instances
        on each update. Safe to pass between threads.
    """
    gateway: Gateway
    data: Optional[PowerwallData] = None
    online: bool
    last_updated: Optional[float] = None
    error: Optional[str] = None


class AggregateData(BaseModel):
    """Aggregated metrics from all configured gateways.
    
    Provides a unified view across multiple Powerwall systems, useful for:
    - Total energy production/consumption across properties
    - Combined battery capacity and state of charge
    - System-wide monitoring dashboards
    - Fleet management and analytics
    
    Aggregation Logic:
        - Only online gateways with valid data are included
        - Power values are summed (watts)
        - Battery percentage is averaged across all systems
        - Each gateway's individual status is preserved in gateways dict
    
    Power Values:
        - Positive battery_power = discharging (powering home)
        - Negative battery_power = charging (storing energy)
        - Positive site_power = importing from grid
        - Negative site_power = exporting to grid
    
    Attributes:
        total_battery_percent: Average state of charge across all batteries (0-100%)
        total_battery_capacity: Combined battery capacity in Wh
        total_site_power: Total grid power in watts (+ import, - export)
        total_battery_power: Total battery power in watts (+ discharge, - charge)
        total_load_power: Total home consumption in watts
        total_solar_power: Total solar production in watts
        total_grid_power: Total grid power (same as site_power, for compatibility)
        num_gateways: Total number of configured gateways
        num_online: Number of currently connected gateways
        gateways: Individual status for each gateway by ID
        timestamp: Unix timestamp when aggregation was performed
    
    Usage:
        aggregate = gateway_manager.get_aggregate_data()
        print(f"Total solar: {aggregate.total_solar_power}W")
        print(f"{aggregate.num_online}/{aggregate.num_gateways} systems online")
        
        # Access individual gateway data
        for gw_id, status in aggregate.gateways.items():
            if status.online:
                print(f"{status.gateway.name}: {status.data.soe}%")
    
    API Endpoints:
        GET /api/aggregate/       - Complete aggregate data
        GET /api/aggregate/power  - Power flows only
        GET /api/aggregate/soe    - Battery levels only
        WS  /ws/aggregate         - Real-time streaming
    """
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

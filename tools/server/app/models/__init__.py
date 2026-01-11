"""
Data Models for PyPowerwall Server

This module provides Pydantic models for type-safe data representation throughout
the application. These models serve as data transfer objects (DTOs) for:
- API responses (JSON serialization)
- Internal data structures (type validation)
- WebSocket messages (real-time streaming)
- Gateway configuration and status

Model Hierarchy:

    Gateway (Configuration)
        └── Represents a single Powerwall gateway connection
            - Connection settings (host, credentials)
            - Connection mode (TEDAPI/Cloud/FleetAPI)
            - Status (online, last_error)
    
    PowerwallData (Metrics)
        └── Contains all data collected from a gateway
            - vitals: Device-level metrics (temperatures, voltages)
            - strings: Solar string data
            - aggregates: Energy flow data (site, battery, solar, grid)
            - soe: State of Energy (battery percentage)
            - system info: version, uptime, status
    
    GatewayStatus (Combined)
        └── Gateway configuration + current data + status
            - gateway: Gateway object
            - data: PowerwallData object (None if offline)
            - online: Connection status
            - last_updated: Timestamp of last successful poll
            - error: Error message if failed
    
    AggregateData (Multi-Gateway)
        └── Combined metrics from all gateways
            - total_*: Sum of all online gateways
            - num_gateways: Total configured
            - num_online: Currently connected
            - gateways: Dict of individual GatewayStatus

Usage Patterns:

    1. API Endpoints:
        @app.get("/api/gateways/{id}", response_model=GatewayStatus)
        async def get_gateway(id: str):
            return gateway_manager.get_gateway(id)
    
    2. WebSocket Streaming:
        status: GatewayStatus = gateway_manager.get_gateway(gateway_id)
        await websocket.send_json(status.model_dump())
    
    3. Aggregation:
        aggregate = AggregateData()
        for status in gateway_manager.get_all_gateways():
            if status.online and status.data:
                aggregate.total_battery_percent += status.data.soe or 0
    
    4. Validation:
        try:
            gateway = Gateway(**config_dict)
        except ValidationError as e:
            logger.error(f"Invalid gateway config: {e}")

Pydantic Features:

    - Automatic JSON serialization: .model_dump(), .model_dump_json()
    - Type validation: Ensures data integrity at runtime
    - Optional fields: Use None for missing/unavailable data
    - Default values: Field(default_factory=dict) for mutable defaults
    - Schema generation: For OpenAPI/Swagger documentation

Thread Safety:

    These models are immutable and thread-safe. Create new instances rather
    than modifying existing ones. The gateway_manager handles synchronization.

Extending Models:

    1. Add new field to model class:
        new_field: Optional[float] = None
    
    2. Update data collection in gateway_manager:
        data.new_field = pw.get_new_metric()
    
    3. Models automatically appear in API docs
    4. Backward compatible - old clients ignore new fields
"""
from .gateway import Gateway, PowerwallData, GatewayStatus, AggregateData

__all__ = ["Gateway", "PowerwallData", "GatewayStatus", "AggregateData"]

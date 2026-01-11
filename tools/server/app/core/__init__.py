"""
Core Business Logic Module

This package contains the core components that handle Powerwall connections,
data collection, and state management. These are the "brains" of the server
that sit between the API layer and the pypowerwall library.

Module Organization:
    
    gateway_manager.py - Central connection and polling manager
        • Purpose: Manages multiple Powerwall gateway connections
        • Responsibilities:
          - Initialize pypowerwall connections (TEDAPI, Cloud, FleetAPI)
          - Background polling of all gateways every 5 seconds
          - Cache latest data for fast API responses
          - Handle connection failures and reconnection
          - Aggregate data across multiple gateways
        • Thread Safety: Asyncio-safe, all operations non-blocking
        • Singleton: Single instance (gateway_manager) used throughout app

Architecture:
    
    The gateway_manager is the central hub of the application:
    
    1. Startup (main.py lifespan):
       - Reads configuration from environment or config.json
       - Creates pypowerwall connections for each gateway
       - Starts background polling task
    
    2. Background Polling (every 5 seconds):
       - Queries each gateway concurrently
       - Updates cached GatewayStatus for each gateway
       - Marks gateways online/offline based on response
       - Calculates aggregate data across all gateways
    
    3. API Requests:
       - Read from cached GatewayStatus (no blocking calls)
       - Fast response even if gateways are offline
       - Optional: Make live pypowerwall calls with short timeouts
    
    4. Shutdown:
       - Cancels polling task gracefully
       - Cleans up resources

Data Flow:
    
    Config → gateway_manager.initialize() → pypowerwall connections
                                          ↓
                        Background polling task (async loop)
                                          ↓
                        gateway_manager.cache (Dict[id, GatewayStatus])
                                          ↓
                        API endpoints read from cache
                                          ↓
                        JSON responses to clients

Connection Modes:
    
    TEDAPI (Local Gateway):
        • Requires: host (192.168.91.1), gw_pwd (gateway WiFi password)
        • Best for: Direct local access, fastest response times
        • Example: Most home installations connected to gateway WiFi
    
    Cloud Mode:
        • Requires: email, authpath (auth token files from pypowerwall setup)
        • Best for: Remote monitoring, multiple sites
        • Setup: Run `python3 -m pypowerwall setup` first
    
    FleetAPI:
        • Requires: email, authpath, fleetapi=True
        • Best for: Official Tesla API access
        • Setup: Register app with Tesla Fleet API

Error Handling:
    
    • Connection failures are logged but don't crash the server
    • Failed polls update gateway status to offline
    • Automatic reconnection on next poll cycle (every 5 seconds)
    • API endpoints check online status before making live calls
    • Cached data remains available even when gateway offline

Adding New Core Modules:
    
    1. Create new file in app/core/ for new business logic:
        ```python
        \"\"\"Clear description of module purpose.\"\"\"
        class NewManager:
            def __init__(self):
                # Initialize state
                pass
        
        # Create singleton instance
        new_manager = NewManager()
        ```
    
    2. Import in this __init__.py:
        ```python
        from .gateway_manager import gateway_manager
        from .new_manager import new_manager
        __all__ = ["gateway_manager", "new_manager"]
        ```
    
    3. Initialize in main.py lifespan if needed:
        ```python
        async def lifespan(app: FastAPI):
            await gateway_manager.initialize(configs)
            await new_manager.initialize()
            yield
            await new_manager.shutdown()
            await gateway_manager.shutdown()
        ```

Performance Considerations:
    
    • Background polling prevents blocking API requests
    • Concurrent gateway polling (asyncio.gather) for speed
    • Short timeouts (3s) on pypowerwall calls
    • Cached data for instant API responses
    • Graceful degradation when gateways offline

Thread Safety:
    
    • All core modules use asyncio (not threads)
    • No locks needed - single event loop
    • Background tasks coordinated via asyncio.create_task()
    • Shutdown uses task cancellation, not signals
"""
from .gateway_manager import gateway_manager

__all__ = ["gateway_manager"]

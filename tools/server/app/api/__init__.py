"""
API Routers Module

This package contains all FastAPI routers that define the server's HTTP and WebSocket endpoints.
Each router module is organized by functionality and registered in main.py with specific prefixes.

Module Organization:
    
    legacy.py - Backward compatibility with original pypowerwall proxy
        • No prefix (registered at root level)
        • Routes: /aggregates, /soe, /csv, /vitals, /version, /stats, /control/*, etc.
        • Purpose: Drop-in replacement for existing proxy deployments
        • Design: Fast-fail on errors, short timeouts, returns safe defaults
    
    gateways.py - Multi-gateway management API
        • Prefix: /api/gateways
        • Routes: / (list), /{id} (status), /{id}/control (operations)
        • Purpose: Manage multiple Powerwall systems independently
        • Design: Per-gateway targeting, independent status tracking
    
    aggregates.py - Combined data from multiple gateways
        • Prefix: /api/aggregate
        • Routes: / (all), /power (flows), /soe (battery), /battery (capacity)
        • Purpose: Treat multiple installations as unified system
        • Design: Cached data only, excludes offline gateways
    
    websockets.py - Real-time streaming endpoints
        • Prefix: /ws
        • Routes: /aggregate (all), /gateway/{id} (single)
        • Purpose: Push updates every second without polling
        • Design: Auto-cleanup dead connections, graceful disconnect handling

Adding New Routers:
    
    1. Create new file in app/api/ following naming convention (lowercase, descriptive)
    
    2. Define router with clear module docstring:
        ```python
        \"\"\"Purpose and routing structure explanation.\"\"\"
        from fastapi import APIRouter
        router = APIRouter()
        ```
    
    3. Add comprehensive function docstrings documenting:
        - Purpose and use case
        - Request parameters and validation
        - Response format and fields
        - Error conditions and status codes
        - Design decisions (timeouts, caching, etc.)
    
    4. Import in this __init__.py:
        ```python
        from . import legacy, gateways, aggregates, websockets, newmodule
        __all__ = ["legacy", "gateways", "aggregates", "websockets", "newmodule"]
        ```
    
    5. Register in main.py with appropriate prefix:
        ```python
        app.include_router(newmodule.router, prefix="/api/newpath", tags=["NewFeature"])
        ```

Routing Best Practices:
    
    • Avoid route conflicts - use prefixes to organize namespaces
    • Document prefix in module docstring (e.g., "Routes prefixed with /api/xyz")
    • Use short timeouts (2-5s) for non-critical operations
    • Fast-fail when gateways offline (check status.online before connecting)
    • Return safe defaults on errors (empty arrays, nulls) to keep UI responsive
    • Use cached gateway manager data when possible (avoid blocking pypowerwall calls)
    • Handle asyncio.TimeoutError explicitly to prevent hanging
    • Log errors but don't expose internal details to clients

Route Conflict Detection:
    
    FastAPI automatically detects route conflicts at startup. If you see:
        RuntimeError: Duplicate route for path '/some/path'
    
    Check that:
        1. No two routers define the same path without prefixes
        2. Routers with prefixes don't overlap (e.g., /api/x and /api/x/y is OK)
        3. Direct @app routes in main.py don't conflict with router paths
"""
from . import legacy, gateways, aggregates, websockets

__all__ = ["legacy", "gateways", "aggregates", "websockets"]

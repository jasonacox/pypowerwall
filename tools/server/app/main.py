"""
PyPowerwall Server - Main FastAPI Application

A modern, high-performance server for monitoring Tesla Powerwall systems
with support for multiple gateways and real-time data streaming.

Standard Configuration (TEDAPI):
    Most users will connect to their Powerwall gateway using TEDAPI at the
    standard IP address 192.168.91.1 with their gateway Wi-Fi password.
    
    Environment variables:
        PW_HOST=192.168.91.1
        PW_GW_PWD=your_gateway_wifi_password
        
    For control operations, authenticate with Tesla Cloud:
        python3 -m pypowerwall setup
        PW_EMAIL=tesla@email.com
        PW_AUTHPATH=/path/to/auth/files

Routing Structure:
    Routes are organized to avoid conflicts:
    
    1. Direct app routes (registered on main app):
       - GET  /              -> Tesla Power Flow animation UI
       - GET  /console       -> Management console UI
       - GET  /example       -> iFrame demo page
       - GET  /example.html  -> Same as /example
       - GET  /favicon-*.png -> Favicon files
    
    2. Legacy proxy compatibility (no prefix):
       - GET  /aggregates, /soe, /csv, /vitals, /strings, etc.
       - GET  /version, /stats, /api/*, etc.
       - POST /control/*     -> Control operations
       
    3. Multi-gateway API (prefix: /api/gateways):
       - GET  /api/gateways/              -> List all gateways
       - GET  /api/gateways/{id}          -> Get gateway status
       - POST /api/gateways/{id}/control  -> Control operations
       
    4. Aggregate data API (prefix: /api/aggregate):
       - GET  /api/aggregate/battery      -> Aggregated battery data
       - GET  /api/aggregate/power        -> Aggregated power data
       
    5. WebSocket streaming (prefix: /ws):
       - WS   /ws/gateway/{id}            -> Real-time gateway data
       - WS   /ws/aggregate               -> Real-time aggregate data
    
    6. Static files:
       - /static/*                        -> Static assets (CSS, JS, images)
    
    Note: FastAPI will raise an error at startup if routes conflict.
    The @app.get("/") route does NOT conflict with router.get("/") 
    because routers use prefixes or have no "/" route defined.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, SERVER_VERSION
from app.api import legacy, gateways, aggregates, websockets
from app.core.gateway_manager import gateway_manager
from app.utils.transform import get_static, inject_js

# Configure logging based on PW_DEBUG setting
log_level = logging.DEBUG if settings.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(f"Starting PyPowerwall Server v{SERVER_VERSION}...")
    logger.info(f"Configured for {len(settings.gateways)} gateway(s)")
    logger.info(f"Polling interval (PW_CACHE_EXPIRE): {settings.cache_expire}s")
    logger.info(f"Timeout (PW_TIMEOUT): {settings.timeout}s")
    logger.info(f"Server listening on {settings.server_host}:{settings.server_port}")
    
    # Initialize gateway manager
    await gateway_manager.initialize(settings.gateways, poll_interval=settings.cache_expire)
    logger.info(f"Initialized {len(gateway_manager.gateways)} gateway(s)")
    
    for gateway_id, gateway in gateway_manager.gateways.items():
        # Show appropriate connection info based on mode
        if gateway.fleetapi:
            mode_info = f"FleetAPI: {gateway.site_id or gateway.email}"
        elif gateway.cloud_mode:
            mode_info = f"Cloud Mode: {gateway.site_id or gateway.email}"
        else:
            mode_info = gateway.host or "TEDAPI"
        logger.info(f"  - {gateway_id}: {gateway.name} ({mode_info})")
    
    yield
    
    # Shutdown
    logger.info("Shutting down PyPowerwall Server...")
    await gateway_manager.shutdown()


# Create FastAPI application
app = FastAPI(
    title="PyPowerwall Server",
    description="Modern FastAPI server for Tesla Powerwall monitoring with multi-gateway support",
    version=SERVER_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
# NOTE: Order matters! More specific routers (gateways, aggregates) must be 
# included BEFORE legacy router to prevent the legacy catch-all /api/{path:path}
# from intercepting requests meant for other routers.
app.include_router(gateways.router, prefix="/api/gateways", tags=["Gateways"])
app.include_router(aggregates.router, prefix="/api/aggregate", tags=["Aggregates"])
app.include_router(websockets.router, prefix="/ws", tags=["WebSockets"])
app.include_router(legacy.router, tags=["Legacy Proxy Compatibility"])

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon.ico from static files."""
    favicon_path = static_path / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    # Fall back to 32x32 PNG if .ico doesn't exist
    png_path = static_path / "favicon-32x32.png"
    if png_path.exists():
        return FileResponse(png_path, media_type="image/png")
    return Response(status_code=404)


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def root(request: Request):
    """Serve the Power Flow animation (Tesla Powerwall interface)."""
    # Use the proxy web directory
    web_root = str(Path(__file__).parent.parent.parent.parent / "proxy" / "web")
    # Use clear.js for UI customization (jQuery loaded from local static files)
    style = "clear.js"
    
    # Get the index.html using get_static
    request_path = "/index.html"
    fcontent, ftype = get_static(web_root, request_path)
    
    if fcontent:
        # Get gateway status for variable replacement
        gateway_id = None
        if gateway_manager.gateways:
            gateway_id = list(gateway_manager.gateways.keys())[0]
        
        status_data = {"version": "", "git_hash": ""}
        if gateway_id:
            status = gateway_manager.get_gateway(gateway_id)
            if status and status.data:
                status_data = {
                    "version": status.data.version or "",
                    "git_hash": "",
                }
        
        # Convert fcontent to string for replacements
        content = fcontent.decode("utf-8")
        
        # Replace template variables
        content = content.replace("{VERSION}", status_data.get("version", ""))
        content = content.replace("{HASH}", status_data.get("git_hash", ""))
        content = content.replace("{EMAIL}", "")
        
        # Build absolute API base URL from request
        api_base_url = f"{request.url.scheme}://{request.url.netloc}/api"
        
        # Set up asset prefix for static files
        static_asset_prefix = "/static/viz-static/"
        content = content.replace("{STYLE}", static_asset_prefix + style)
        content = content.replace("{ASSET_PREFIX}", static_asset_prefix)
        content = content.replace("{API_BASE_URL}", api_base_url)
        
        # Inject JS transformation if style file exists
        style_path = os.path.join(static_path, "viz-static", style)
        if os.path.exists(style_path):
            content = inject_js(content, static_asset_prefix + style)
        
        return HTMLResponse(content=content)
    
    # Fallback if proxy web files not found
    return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>PyPowerwall Server</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                }
                h1 { color: #e31937; }
                a { color: #0066cc; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>PyPowerwall Server</h1>
            <p>Power Flow animation not available. Install pypowerwall proxy web files.</p>
            <h2>Quick Links</h2>
            <ul>
                <li><a href="/console">Management Console</a></li>
                <li><a href="/docs">API Documentation (Swagger UI)</a></li>
                <li><a href="/redoc">API Documentation (ReDoc)</a></li>
            </ul>
        </body>
        </html>
    """)


@app.get("/console", response_class=HTMLResponse, tags=["UI"])
async def console():
    """Serve the management console UI."""
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>PyPowerwall Server</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                }
                h1 { color: #e31937; }
                a { color: #0066cc; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>PyPowerwall Server</h1>
            <p>Welcome to PyPowerwall Server - A modern FastAPI-based monitoring solution for Tesla Powerwall.</p>
            <h2>Quick Links</h2>
            <ul>
                <li><a href="/docs">API Documentation (Swagger UI)</a></li>
                <li><a href="/redoc">API Documentation (ReDoc)</a></li>
                <li><a href="/api/gateways">List Gateways</a></li>
                <li><a href="/vitals">Vitals (Legacy)</a></li>
                <li><a href="/aggregates">Aggregates (Legacy)</a></li>
            </ul>
            <p><a href="/">← Back to Power Flow</a></p>
        </body>
        </html>
    """)


@app.get("/example", response_class=HTMLResponse, tags=["UI"])
@app.get("/example.html", response_class=HTMLResponse, tags=["UI"])
async def example():
    """Serve the Power Flow iFrame example page."""
    example_path = Path(__file__).parent / "static" / "example.html"
    if example_path.exists():
        return HTMLResponse(content=example_path.read_text())
    return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>Example Not Found</title></head>
        <body>
            <h1>Example page not found</h1>
            <p><a href="/">← Back to Power Flow</a></p>
        </body>
        </html>
    """)


@app.get("/favicon-32x32.png", tags=["Static"])
@app.get("/favicon-16x16.png", tags=["Static"])
async def favicon(request: Request):
    """Serve favicon files."""
    filename = request.url.path.lstrip("/")
    favicon_path = Path(__file__).parent / "static" / filename
    if favicon_path.exists():
        return FileResponse(favicon_path)
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint with actual gateway status.
    
    Returns:
        - healthy: All gateways online
        - degraded: Some gateways online, some offline
        - unhealthy: All gateways offline
    """
    total = len(gateway_manager.gateways)
    
    if total == 0:
        return {
            "status": "no_gateways",
            "version": SERVER_VERSION,
            "gateways": 0,
            "gateway_ids": []
        }
    
    # Count online gateways
    online_count = 0
    gateway_details = []
    
    for gateway_id in gateway_manager.gateways.keys():
        status = gateway_manager.get_gateway(gateway_id)
        is_online = status.online if status else False
        if is_online:
            online_count += 1
        
        gateway_details.append({
            "id": gateway_id,
            "online": is_online,
            "error": status.error if status and status.error else None
        })
    
    # Determine overall health
    if online_count == total:
        health_status = "healthy"
    elif online_count > 0:
        health_status = "degraded"
    else:
        health_status = "unhealthy"
    
    return {
        "status": health_status,
        "version": SERVER_VERSION,
        "gateways": total,
        "gateways_online": online_count,
        "gateways_offline": total - online_count,
        "gateway_ids": list(gateway_manager.gateways.keys()),
        "gateway_details": gateway_details
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True
    )

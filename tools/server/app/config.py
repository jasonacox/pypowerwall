"""
Configuration Management for PyPowerwall Server

This module handles all server configuration through environment variables and provides
100% backward compatibility with the original pypowerwall proxy server settings.

Configuration Methods:

    1. Multi-Gateway Configuration (recommended for multiple Powerwalls):
        export PW_GATEWAYS='[
          {
            "id": "home",
            "name": "Home Powerwall",
            "host": "192.168.91.1",
            "gw_pwd": "gateway_wifi_password",
            "timezone": "America/Los_Angeles"
          },
          {
            "id": "cabin",
            "name": "Cabin Powerwall",
            "host": "192.168.92.1",
            "gw_pwd": "different_password",
            "timezone": "America/Denver"
          }
        ]'
    
    2. Single Gateway Configuration (legacy compatibility):
        export PW_HOST=192.168.91.1
        export PW_GW_PWD=gateway_wifi_password
        export PW_TIMEZONE=America/Los_Angeles

Environment Variables (Proxy Compatible):

    Core Connection Settings:
        PW_HOST              - Powerwall IP address (default: none, e.g., 192.168.91.1)
        PW_GW_PWD            - Gateway WiFi password for TEDAPI (default: none)
        PW_PASSWORD          - Legacy PW2 local password (default: none)
        PW_EMAIL             - Tesla account email for cloud mode (default: none)
        PW_TIMEZONE          - Local timezone (default: "America/Los_Angeles")
        PW_AUTH_PATH         - Path to auth token files (default: none)
    
    Server Settings:
        PW_BIND_ADDRESS      - Server bind address (default: "0.0.0.0")
        PW_PORT              - Server port (default: 8675)
        PW_DEBUG             - Enable debug logging "yes"/"no" (default: "no")
        PW_HTTPS             - Enable HTTPS mode (default: "no")
    
    Performance Settings:
        PW_CACHE_EXPIRE      - Polling frequency in seconds (default: 5)
        PW_BROWSER_CACHE     - Browser cache time in seconds (default: 0)
        PW_TIMEOUT           - Pypowerwall timeout in seconds (default: 10)
        PW_POOL_MAXSIZE      - Connection pool size (default: 15)
    
    Network Robustness:
        PW_SUPPRESS_NETWORK_ERRORS  - Suppress error logs (default: "no")
        PW_NETWORK_ERROR_RATE_LIMIT - Errors per minute limit (default: 5)
        PW_FAIL_FAST                - Return immediately on degraded connection (default: "no")
        PW_GRACEFUL_DEGRADATION     - Use cached data when unavailable (default: "yes")
        PW_HEALTH_CHECK             - Enable health monitoring (default: "yes")
        PW_CACHE_TTL                - Max cached data age in seconds (default: 30)
    
    UI and Advanced:
        PW_STYLE             - UI style: clear/black/white/grafana/grafana-dark (default: "clear")
        PW_AUTH_MODE         - Auth mode: cookie/token (default: "cookie")
        PW_CACHE_FILE        - Cache file path (default: ".powerwall")
        PW_SITEID            - Tesla site ID for multi-site accounts (default: none)
        PW_CONTROL_SECRET    - Enable control commands (default: none/disabled)
        PROXY_BASE_URL       - Base URL for reverse proxy (default: "/")

Connection Modes:

    TEDAPI (Local Gateway Access):
        • Fastest, most reliable
        • Requires direct connection to gateway WiFi or local network
        • Configuration: PW_HOST + PW_GW_PWD
        • Example: 192.168.91.1 with gateway password
    
    Cloud Mode:
        • Remote access from anywhere
        • Requires Tesla account authentication
        • Configuration: PW_EMAIL + PW_AUTH_PATH
        • Setup: Run `python3 -m pypowerwall setup` first
    
    FleetAPI Mode:
        • Official Tesla API
        • Requires app registration with Tesla
        • Configuration: PW_EMAIL + PW_AUTH_PATH + fleetapi=true

Gateway Configuration Priority:

    1. PW_GATEWAYS JSON (highest priority)
       - Supports multiple gateways with independent settings
       - Each gateway can have different connection modes
       
    2. Legacy environment variables (fallback)
       - Single gateway using PW_HOST, PW_GW_PWD, etc.
       - Automatically creates "default" gateway
       - 100% compatible with proxy server

Examples:

    # Single gateway (TEDAPI local access)
    PW_HOST=192.168.91.1
    PW_GW_PWD=MyGatewayPassword
    PW_CACHE_EXPIRE=10
    PW_DEBUG=yes
    
    # Single gateway (Cloud mode)
    PW_EMAIL=user@example.com
    PW_AUTH_PATH=/home/user/.pypowerwall
    PW_CACHE_EXPIRE=30
    
    # Multiple gateways (mixed modes)
    PW_GATEWAYS='[
      {"id": "home", "host": "192.168.91.1", "gw_pwd": "pass1"},
      {"id": "remote", "email": "user@example.com", "authpath": "/path", "cloud_mode": true}
    ]'
    PW_CACHE_EXPIRE=15

Architecture:

    Settings Class (Pydantic BaseSettings):
        • Automatically loads from environment variables
        • Type validation and conversion
        • Default values for all settings
        • Computed properties (e.g., control_enabled)
    
    GatewayConfig Class:
        • Defines single gateway configuration
        • Supports TEDAPI, Cloud, and FleetAPI modes
        • Used in both PW_GATEWAYS and legacy modes
    
    Initialization Flow:
        1. Settings() loads all environment variables
        2. _initialize_gateways() called automatically
        3. Try PW_GATEWAYS first (multi-gateway JSON)
        4. Fall back to legacy PW_HOST/PW_EMAIL (single gateway)
        5. Gateway list stored in settings.gateways

Adding New Settings:

    1. Add field to Settings class with Field() and alias:
        new_setting: int = Field(default=42, alias="PW_NEW_SETTING")
    
    2. Document in this module docstring
    
    3. Use in code via settings.new_setting
    
    4. Update README with new variable

Accessing Configuration:

    from app.config import settings
    
    # Access settings
    port = settings.server_port
    gateways = settings.gateways
    debug_enabled = settings.debug
    
    # Check features
    if settings.control_enabled:
        # Control commands available
        pass
"""
import json
import logging
import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Server version
SERVER_VERSION = "0.1.0"


class GatewayConfig(BaseSettings):
    """Configuration for a single Powerwall gateway.
    
    Auth modes:
    - TEDAPI: host + gw_pwd (local gateway access via 192.168.91.1)
    - Cloud: email + authpath (uses .pypowerwall.auth and .pypowerwall.site files)
    """
    id: str
    name: str
    host: Optional[str] = None
    gw_pwd: Optional[str] = None  # Gateway Wi-Fi password for TEDAPI mode
    email: Optional[str] = None
    authpath: Optional[str] = None  # Path to .pypowerwall.auth and .pypowerwall.site files
    timezone: str = "America/Los_Angeles"
    cloud_mode: bool = False
    fleetapi: bool = False
    
    model_config = {"env_prefix": ""}


class Settings(BaseSettings):
    """Application settings - Compatible with pypowerwall proxy environment variables."""
    
    # Server configuration (maps to proxy settings)
    server_host: str = Field(default="0.0.0.0", alias="PW_BIND_ADDRESS")
    server_port: int = Field(default=8675, alias="PW_PORT")
    debug: bool = Field(default=False, alias="PW_DEBUG")
    
    # Powerwall connection settings
    pw_host: Optional[str] = Field(default=None, alias="PW_HOST")
    pw_gw_pwd: Optional[str] = Field(default=None, alias="PW_GW_PWD")
    pw_password: Optional[str] = Field(default=None, alias="PW_PASSWORD")  # Legacy PW2 local access
    pw_email: Optional[str] = Field(default=None, alias="PW_EMAIL")
    pw_timezone: str = Field(default="America/Los_Angeles", alias="PW_TIMEZONE")
    
    # Proxy settings
    cache_expire: int = Field(default=5, alias="PW_CACHE_EXPIRE")  # Polling frequency in seconds
    browser_cache: int = Field(default=0, alias="PW_BROWSER_CACHE")  # Browser cache time in seconds
    timeout: int = Field(default=10, alias="PW_TIMEOUT")  # Pypowerwall timeout in seconds
    pool_maxsize: int = Field(default=15, alias="PW_POOL_MAXSIZE")  # Connection pool size
    https_mode: bool = Field(default=False, alias="PW_HTTPS")
    
    # Network robustness settings
    suppress_network_errors: bool = Field(default=False, alias="PW_SUPPRESS_NETWORK_ERRORS")
    network_error_rate_limit: int = Field(default=5, alias="PW_NETWORK_ERROR_RATE_LIMIT")
    fail_fast: bool = Field(default=False, alias="PW_FAIL_FAST")
    graceful_degradation: bool = Field(default=True, alias="PW_GRACEFUL_DEGRADATION")
    health_check: bool = Field(default=True, alias="PW_HEALTH_CHECK")
    cache_ttl: int = Field(default=30, alias="PW_CACHE_TTL")  # Max age for cached data
    
    # UI and advanced settings
    style: str = Field(default="clear", alias="PW_STYLE")
    pw_authpath: Optional[str] = Field(default=None, alias="PW_AUTH_PATH")
    auth_mode: str = Field(default="cookie", alias="PW_AUTH_MODE")
    cache_file: str = Field(default=".powerwall", alias="PW_CACHE_FILE")
    siteid: Optional[str] = Field(default=None, alias="PW_SITEID")
    control_secret: Optional[str] = Field(default=None, alias="PW_CONTROL_SECRET")
    proxy_base_url: str = Field(default="/", alias="PROXY_BASE_URL")
    
    # CORS configuration
    cors_origins: List[str] = Field(default=["*"], alias="CORS_ORIGINS")
    
    # Gateway configuration
    gateways: List[GatewayConfig] = Field(default_factory=list)
    
    # Computed properties
    @property
    def control_enabled(self) -> bool:
        """Control features enabled if PW_CONTROL_SECRET is set."""
        return bool(self.control_secret)
    
    model_config = {
        "env_prefix": "",
        "case_sensitive": False
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._initialize_gateways()
    
    def _initialize_gateways(self):
        """Initialize gateway configurations from environment variables."""
        # Try to load from PW_GATEWAYS JSON
        gateways_json = os.getenv("PW_GATEWAYS")
        if gateways_json:
            try:
                gateways_data = json.loads(gateways_json)
                self.gateways = [GatewayConfig(**gw) for gw in gateways_data]
                return
            except Exception as e:
                logger.error(f"Error parsing PW_GATEWAYS: {e}")
        
        # Fall back to single gateway mode (legacy compatibility)
        if self.pw_host or self.pw_email:
            self.gateways = [
                GatewayConfig(
                    id="default",
                    name="Default Gateway",
                    host=self.pw_host,
                    gw_pwd=self.pw_gw_pwd,
                    email=self.pw_email,
                    authpath=self.pw_authpath,
                    timezone=self.pw_timezone,
                    cloud_mode=bool(self.pw_email and not self.pw_host)
                )
            ]


# Global settings instance
settings = Settings()

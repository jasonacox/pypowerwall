"""Configuration management for PyPowerwall Server."""
import json
import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


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
    """Application settings."""
    
    # Server configuration
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8080, alias="SERVER_PORT")
    
    # CORS configuration
    cors_origins: List[str] = Field(
        default=["*"],
        alias="CORS_ORIGINS"
    )
    
    # Control features (optional)
    control_token: Optional[str] = Field(default=None, alias="CONTROL_TOKEN")
    control_enabled: bool = Field(default=False, alias="CONTROL_ENABLED")
    
    # Gateway configuration
    gateways: List[GatewayConfig] = Field(default_factory=list)
    
    # Legacy single gateway support
    pw_host: Optional[str] = Field(default=None, alias="PW_HOST")
    pw_gw_pwd: Optional[str] = Field(default=None, alias="PW_GW_PWD")  # Gateway Wi-Fi password
    pw_email: Optional[str] = Field(default=None, alias="PW_EMAIL")
    pw_authpath: Optional[str] = Field(default=None, alias="PW_AUTHPATH")
    pw_timezone: str = Field(default="America/Los_Angeles", alias="PW_TIMEZONE")
    
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
                print(f"Error parsing PW_GATEWAYS: {e}")
        
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

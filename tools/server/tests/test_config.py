"""Tests for configuration."""
from app.config import Settings, GatewayConfig


def test_settings_defaults():
    """Test default settings values."""
    settings = Settings()
    assert settings.server_host == "0.0.0.0"
    assert settings.server_port == 8675  # Matches pypowerwall proxy default


def test_settings_from_env(monkeypatch):
    """Test loading settings from environment variables."""
    # Use PW_* aliases which are the primary env var names
    monkeypatch.setenv("PW_BIND_ADDRESS", "127.0.0.1")
    monkeypatch.setenv("PW_PORT", "9000")
    
    # Create new Settings instance to pick up env vars
    settings = Settings()
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 9000


def test_gateway_config_validation():
    """Test gateway config validation."""
    config = GatewayConfig(
        id="test",
        name="Test Gateway",
        host="192.168.1.100",
        gw_pwd="password"
    )
    
    assert config.id == "test"
    assert config.name == "Test Gateway"
    assert config.host == "192.168.1.100"
    assert config.gw_pwd == "password"


def test_gateway_config_cloud_mode():
    """Test gateway config for cloud mode."""
    config = GatewayConfig(
        id="cloud-test",
        name="Cloud Gateway",
        email="test@example.com",
        authpath="/path/to/auth",
        cloud_mode=True
    )
    
    assert config.cloud_mode is True
    assert config.email == "test@example.com"
    assert config.authpath == "/path/to/auth"

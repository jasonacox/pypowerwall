"""Pytest configuration and fixtures."""
import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import app
from app.core.gateway_manager import gateway_manager


@pytest.fixture(autouse=True)
def reset_gateway_manager():
    """Reset gateway manager before each test."""
    gateway_manager.gateways.clear()
    gateway_manager.connections.clear()
    gateway_manager.cache.clear()
    yield
    gateway_manager.gateways.clear()
    gateway_manager.connections.clear()
    gateway_manager.cache.clear()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_pypowerwall():
    """Mock pypowerwall.Powerwall instance."""
    mock = Mock()
    mock.poll.return_value = {
        "site": {"instant_power": 100, "instant_reactive_power": 0},
        "solar": {"instant_power": 5000, "instant_reactive_power": 0},
        "battery": {"instant_power": -2000, "instant_reactive_power": 0},
        "load": {"instant_power": 3100, "instant_reactive_power": 0}
    }
    mock.level.return_value = 85.5
    mock.freq.return_value = 60.0
    mock.status.return_value = "Running"
    mock.version.return_value = "23.44.0"
    mock.vitals.return_value = {
        "TEPOD--1234": {
            "POD_ActiveHeating": False,
            "POD_ChargeComplete": False,
            "POD_ChargeRequest": True,
            "POD_DischargeComplete": False,
            "POD_PermanentlyFaulted": False,
            "POD_PersistentlyFaulted": False,
            "POD_enable_line": True,
            "POD_available_charge_power": 5000,
            "POD_available_dischg_power": 5000,
            "POD_nom_energy_remaining": 12000,
            "POD_nom_energy_to_be_charged": 1500,
            "POD_nom_full_pack_energy": 13500
        }
    }
    mock.strings.return_value = {
        "A": {"Connected": True, "Current": 5.2, "Power": 2500, "Voltage": 480}
    }
    mock.temps.return_value = {
        "TEPOD--1234": 25.5
    }
    mock.alerts.return_value = []
    mock.get_reserve.return_value = 20
    mock.get_time_remaining.return_value = 8.5
    mock.grid_status.return_value = "UP"
    mock.system_status.return_value = {
        "nominal_full_pack_energy": 13500,
        "nominal_energy_remaining": 11547,
        "battery_blocks": [
            {
                "Type": "ACPW",
                "PackagePartNumber": "1234567-00-A",
                "PackageSerialNumber": "TG1234567890AB",
                "nominal_energy_remaining": 11547,
                "nominal_full_pack_energy": 13500,
                "pinv_state": "PINV_Active",
                "pinv_grid_state": "Grid_Compliant",
                "p_out": -2000,
                "q_out": 0,
                "v_out": 240,
                "f_out": 60.0,
                "i_out": 8.3,
                "energy_charged": 50000,
                "energy_discharged": 45000,
                "off_grid": False,
                "vf_mode": False,
                "wobble_detected": False,
                "charge_power_clamped": False,
                "backup_ready": True,
                "OpSeqState": "Active",
                "version": "23.44.0"
            }
        ]
    }
    
    # TEDAPI mock
    mock.tedapi = Mock()
    mock.tedapi.get_config.return_value = {"vin": "12345", "din": "1234567-00-A"}
    mock.tedapi.get_status.return_value = {"state": "ready"}
    mock.tedapi.get_components.return_value = {"components": []}
    mock.tedapi.get_battery_blocks.return_value = {"blocks": []}
    mock.tedapi.get_device_controller.return_value = {"controller": "active"}
    
    return mock


@pytest.fixture
def mock_gateway_manager(monkeypatch, mock_pypowerwall):
    """Mock gateway manager with a test gateway."""
    # Clear existing gateways
    gateway_manager.gateways.clear()
    gateway_manager.connections.clear()
    gateway_manager.cache.clear()
    
    # Mock the Powerwall constructor
    def mock_powerwall_init(*args, **kwargs):
        return mock_pypowerwall
    
    import pypowerwall
    monkeypatch.setattr(pypowerwall, "Powerwall", mock_powerwall_init)
    
    return gateway_manager


@pytest.fixture
def connected_gateway(mock_gateway_manager, mock_pypowerwall):
    """Add a connected gateway to the manager."""
    from app.models.gateway import Gateway, GatewayStatus, PowerwallData
    
    # Create gateway and add to manager
    gateway = Gateway(
        id="test-gateway",
        name="Test Gateway",
        host="192.168.91.1",
        gw_pwd="TEST_PASSWORD",
        online=True
    )
    
    # Create data
    data = PowerwallData(
        aggregates=mock_pypowerwall.poll.return_value,
        soe=mock_pypowerwall.level.return_value,
        freq=mock_pypowerwall.freq.return_value,
        status=mock_pypowerwall.status.return_value,
        version=mock_pypowerwall.version.return_value,
        vitals=mock_pypowerwall.vitals.return_value,
        strings=mock_pypowerwall.strings.return_value,
        timestamp=1234567890.0
    )
    
    status = GatewayStatus(
        gateway=gateway,
        data=data,
        online=True,
        last_updated=1234567890.0
    )
    
    mock_gateway_manager.gateways["test-gateway"] = gateway
    mock_gateway_manager.connections["test-gateway"] = mock_pypowerwall
    mock_gateway_manager.cache["test-gateway"] = status
    
    return status

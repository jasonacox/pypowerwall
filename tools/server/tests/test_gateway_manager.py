"""Tests for gateway manager."""
import pytest
from app.core.gateway_manager import gateway_manager


def test_get_gateway(connected_gateway):
    """Test getting a gateway by ID."""
    status = gateway_manager.get_gateway("test-gateway")
    assert status is not None
    assert status.gateway.id == "test-gateway"
    assert status.gateway.name == "Test Gateway"
    assert status.online is True


def test_get_nonexistent_gateway(mock_gateway_manager):
    """Test getting a gateway that doesn't exist."""
    status = mock_gateway_manager.get_gateway("nonexistent")
    assert status is None


def test_get_all_gateways(connected_gateway):
    """Test getting all gateways."""
    gateways = gateway_manager.get_all_gateways()
    assert len(gateways) >= 1
    assert "test-gateway" in gateways
    assert gateways["test-gateway"].online is True


def test_get_connection(connected_gateway):
    """Test getting a pypowerwall connection."""
    pw = gateway_manager.get_connection("test-gateway")
    assert pw is not None
    assert hasattr(pw, "poll")
    assert hasattr(pw, "level")


def test_get_nonexistent_connection(mock_gateway_manager):
    """Test getting a connection that doesn't exist."""
    pw = mock_gateway_manager.get_connection("nonexistent")
    assert pw is None


@pytest.mark.asyncio
async def test_polling_updates_gateway_data(mock_gateway_manager, mock_pypowerwall):
    """Test that polling updates gateway data."""
    from app.models.gateway import Gateway, GatewayStatus
    
    # Set up a gateway
    gateway = Gateway(
        id="poll-test",
        name="Poll Test",
        host="192.168.1.100",
        gw_pwd="password123"
    )
    
    mock_gateway_manager.gateways["poll-test"] = gateway
    mock_gateway_manager.connections["poll-test"] = mock_pypowerwall
    mock_gateway_manager.cache["poll-test"] = GatewayStatus(gateway=gateway, online=False)
    
    # Manually trigger poll
    await mock_gateway_manager._poll_gateway("poll-test")
    
    # Check that data was updated
    status = mock_gateway_manager.get_gateway("poll-test")
    assert status.online is True
    assert status.data.aggregates is not None
    assert status.data.soe == 85.5


@pytest.mark.asyncio
async def test_polling_handles_timeout(mock_gateway_manager, mock_pypowerwall):
    """Test that polling handles timeouts gracefully."""
    from app.models.gateway import Gateway, GatewayStatus
    
    gateway = Gateway(
        id="timeout-test",
        name="Timeout Test",
        host="192.168.1.100",
        gw_pwd="password123"
    )
    
    mock_gateway_manager.gateways["timeout-test"] = gateway
    mock_gateway_manager.connections["timeout-test"] = mock_pypowerwall
    mock_gateway_manager.cache["timeout-test"] = GatewayStatus(gateway=gateway, online=False)
    
    # Mock poll to raise exception
    mock_pypowerwall.poll.side_effect = Exception("Connection timeout")
    
    # Should not raise exception
    await mock_gateway_manager._poll_gateway("timeout-test")
    
    # Gateway should be marked offline
    status = mock_gateway_manager.get_gateway("timeout-test")
    assert status.online is False


@pytest.mark.asyncio
async def test_polling_with_missing_optional_data(mock_gateway_manager, mock_pypowerwall):
    """Test polling when vitals/strings are unavailable."""
    from app.models.gateway import Gateway, GatewayStatus
    
    gateway = Gateway(
        id="partial-test",
        name="Partial Test",
        host="192.168.1.100",
        gw_pwd="password123"
    )
    
    mock_gateway_manager.gateways["partial-test"] = gateway
    mock_gateway_manager.connections["partial-test"] = mock_pypowerwall
    mock_gateway_manager.cache["partial-test"] = GatewayStatus(gateway=gateway, online=False)
    
    # Make vitals and strings raise exceptions
    mock_pypowerwall.vitals.side_effect = Exception("Not available")
    mock_pypowerwall.strings.side_effect = Exception("Not available")
    
    await mock_gateway_manager._poll_gateway("partial-test")
    
    # Should still be online with aggregates data
    status = mock_gateway_manager.get_gateway("partial-test")
    assert status.online is True
    assert status.data.aggregates is not None
    assert status.data.vitals is None
    assert status.data.strings is None

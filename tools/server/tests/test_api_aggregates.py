"""Tests for aggregates API endpoint."""


def test_get_aggregates_success(client, connected_gateway):
    """Test getting aggregates data successfully."""
    response = client.get("/api/aggregates")
    assert response.status_code == 200
    data = response.json()
    
    assert "site" in data
    assert "solar" in data
    assert "battery" in data
    assert "load" in data
    
    # Check structure
    assert "instant_power" in data["site"]
    assert data["site"]["instant_power"] == 100


def test_get_aggregates_with_gateway_id(client, connected_gateway):
    """Test getting aggregates for specific gateway."""
    response = client.get("/api/aggregates?gateway_id=test-gateway")
    assert response.status_code == 200
    data = response.json()
    assert "site" in data


def test_get_aggregates_no_gateway(client, mock_gateway_manager):
    """Test getting aggregates when no gateway configured."""
    response = client.get("/api/aggregates")
    assert response.status_code == 503
    assert "No gateways" in response.json()["detail"]


def test_get_aggregates_invalid_gateway_id(client, connected_gateway):
    """Test getting aggregates with invalid gateway ID."""
    response = client.get("/api/aggregates?gateway_id=invalid")
    # Returns aggregated data from all gateways when specific gateway not found
    assert response.status_code == 200

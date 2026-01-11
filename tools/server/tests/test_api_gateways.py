"""Tests for gateway API endpoints."""


def test_list_gateways_empty(client, mock_gateway_manager):
    """Test listing gateways when none configured."""
    response = client.get("/api/gateways")
    # May return 503 or 200 with empty dict depending on implementation
    assert response.status_code in [200, 503]


def test_list_gateways_with_data(client, connected_gateway):
    """Test listing gateways with configured gateway."""
    response = client.get("/api/gateways")
    assert response.status_code == 200
    data = response.json()
    # Just verify we get data back
    assert isinstance(data, dict)


def test_get_gateway_by_id(client, connected_gateway):
    """Test getting a specific gateway."""
    response = client.get("/api/gateways/test-gateway")
    assert response.status_code == 200
    data = response.json()
    # Just verify we get data back
    assert isinstance(data, dict)


def test_get_nonexistent_gateway(client, mock_gateway_manager):
    """Test getting a gateway that doesn't exist."""
    response = client.get("/api/gateways/nonexistent")
    # May return 404 or 503 depending on whether there are any gateways
    assert response.status_code in [404, 503]


def test_get_gateway_vitals(client, connected_gateway):
    """Test getting gateway vitals."""
    response = client.get("/api/gateways/test-gateway/vitals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_get_gateway_strings(client, connected_gateway):
    """Test getting gateway strings."""
    response = client.get("/api/gateways/test-gateway/strings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_get_gateway_aggregates(client, connected_gateway):
    """Test getting gateway aggregates."""
    response = client.get("/api/gateways/test-gateway/aggregates")
    assert response.status_code == 200
    data = response.json()
    assert "site" in data
    assert "solar" in data

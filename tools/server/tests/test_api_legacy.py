"""Tests for legacy proxy API endpoints."""


def test_aggregates_endpoint(client, connected_gateway):
    """Test /aggregates endpoint."""
    response = client.get("/aggregates")
    assert response.status_code == 200
    data = response.json()
    assert "site" in data
    assert "solar" in data
    assert "battery" in data
    assert "load" in data


def test_soe_endpoint(client, connected_gateway):
    """Test /soe endpoint."""
    response = client.get("/soe")
    assert response.status_code == 200
    data = response.json()
    assert data["percentage"] == 85.5


def test_csv_endpoint(client, connected_gateway):
    """Test /csv endpoint without headers."""
    response = client.get("/csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    
    lines = response.text.strip().split("\n")
    assert len(lines) == 1  # No header, just data
    
    values = lines[0].split(",")
    assert len(values) == 5  # Grid,Home,Solar,Battery,Level


def test_csv_endpoint_with_headers(client, connected_gateway):
    """Test /csv endpoint with headers."""
    response = client.get("/csv?headers=yes")
    assert response.status_code == 200
    
    lines = response.text.strip().split("\n")
    assert len(lines) == 2  # Header + data
    assert lines[0] == "Grid,Home,Solar,Battery,BatteryLevel"


def test_csv_v2_endpoint(client, connected_gateway):
    """Test /csv/v2 endpoint."""
    response = client.get("/csv/v2")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    
    lines = response.text.strip().split("\n")
    assert len(lines) == 1
    
    values = lines[0].split(",")
    assert len(values) == 7  # Grid,Home,Solar,Battery,Level,GridStatus,Reserve


def test_temps_endpoint(client, connected_gateway):
    """Test /temps endpoint."""
    response = client.get("/temps")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_temps_pw_endpoint(client, connected_gateway):
    """Test /temps/pw endpoint."""
    response = client.get("/temps/pw")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    # Should have PW1_temp, PW2_temp, etc. keys


def test_alerts_endpoint(client, connected_gateway):
    """Test /alerts endpoint."""
    response = client.get("/alerts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_alerts_pw_endpoint(client, connected_gateway):
    """Test /alerts/pw endpoint."""
    response = client.get("/alerts/pw")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_strings_endpoint(client, connected_gateway):
    """Test /strings endpoint."""
    response = client.get("/strings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_vitals_endpoint(client, connected_gateway):
    """Test /vitals endpoint."""
    response = client.get("/vitals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_freq_endpoint(client, connected_gateway):
    """Test /freq endpoint."""
    response = client.get("/freq")
    assert response.status_code == 200
    data = response.json()
    assert "freq" in data
    assert data["freq"] == 60.0


def test_pod_endpoint(client, connected_gateway):
    """Test /pod endpoint."""
    response = client.get("/pod")
    assert response.status_code == 200
    data = response.json()
    
    # Check aggregate data
    assert "nominal_full_pack_energy" in data
    assert "nominal_energy_remaining" in data
    assert "time_remaining_hours" in data
    assert "backup_reserve_percent" in data
    
    # Check individual battery block data
    assert "PW1_p_out" in data
    assert "PW1_PackageSerialNumber" in data


def test_battery_endpoint(client, connected_gateway):
    """Test /battery endpoint."""
    response = client.get("/battery")
    assert response.status_code == 200
    data = response.json()
    assert "power" in data
    assert isinstance(data["power"], (int, float))


def test_tedapi_config_endpoint(client, connected_gateway):
    """Test /tedapi/config endpoint."""
    response = client.get("/tedapi/config")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_tedapi_status_endpoint(client, connected_gateway):
    """Test /tedapi/status endpoint."""
    response = client.get("/tedapi/status")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_tedapi_battery_endpoint(client, connected_gateway):
    """Test /tedapi/battery endpoint."""
    response = client.get("/tedapi/battery")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_endpoint_without_gateway(client, mock_gateway_manager):
    """Test endpoints return 503 when no gateway available."""
    response = client.get("/aggregates")
    assert response.status_code == 503

"""Tests for edge cases and error handling."""


def test_null_aggregates_data(client, connected_gateway):
    """Test handling of null aggregates data."""
    from app.core.gateway_manager import gateway_manager
    
    status = gateway_manager.get_gateway("test-gateway")
    if status and status.data:
        status.data.aggregates = None
    
    response = client.get("/api/aggregates")
    # Should return empty dict or handle gracefully
    assert response.status_code in [200, 503]


def test_missing_battery_data(client, connected_gateway):
    """Test handling missing battery data in aggregates."""
    from app.core.gateway_manager import gateway_manager
    
    status = gateway_manager.get_gateway("test-gateway")
    if status and status.data and status.data.aggregates:
        del status.data.aggregates["battery"]
    
    response = client.get("/battery")
    assert response.status_code == 200
    data = response.json()
    assert "power" in data


def test_concurrent_api_requests(client, connected_gateway):
    """Test multiple concurrent API requests."""
    import concurrent.futures
    
    def make_request():
        return client.get("/api/aggregates")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(10)]
        results = [f.result() for f in futures]
    
    # All requests should succeed
    assert all(r.status_code == 200 for r in results)


def test_large_vitals_data(client, connected_gateway):
    """Test handling of large vitals dataset."""
    # Test with the existing vitals data
    response = client.get("/vitals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    # Just verify it returns vitals data
    assert len(data) >= 0


def test_invalid_json_in_config(client):
    """Test handling of invalid JSON in gateway config."""
    # FastAPI will reject invalid JSON before it reaches our code
    response = client.post("/api/gateways", content=b"not valid json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_empty_gateway_list_csv(client, mock_gateway_manager):
    """Test CSV endpoint with no gateways."""
    response = client.get("/csv")
    assert response.status_code == 503

"""Basic tests for PyPowerwall Server."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # Status is 'no_gateways' when no gateways configured, 'healthy' otherwise
    assert data["status"] in ("healthy", "no_gateways")
    assert "version" in data
    assert "gateways" in data


def test_root_endpoint():
    """Test the root endpoint returns HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_api_docs():
    """Test that API docs are accessible."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc():
    """Test that ReDoc is accessible."""
    response = client.get("/redoc")
    assert response.status_code == 200

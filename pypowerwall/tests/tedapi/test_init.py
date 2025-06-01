import time
from unittest.mock import patch

from pypowerwall.tedapi import TEDAPI
import pytest

@pytest.fixture
def mock_tedapi():
    """Create a TEDAPI instance with mocked connection"""
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="TEST_DIN"):
        api = TEDAPI("test_password", pwcacheexpire=50)
        api.pwcache = {
            "status": {
                "control": {
                    "meterAggregates": [
                        {"location": "LOAD", "realPowerW": 1500},
                        {"location": "SOLAR", "realPowerW": 3000},
                        {"location": "BATTERY", "realPowerW": -500}
                    ]
                }
            }
        }
    return api

class TestTEDAPIPowerMethods:
    def test_current_power_single_location(self, mock_tedapi):
        """Test current power for single location"""
        mock_tedapi.pwcachetime = {"status": time.time()}

        assert mock_tedapi.current_power("LOAD") == 1500
        assert mock_tedapi.current_power("SOLAR") == 3000
        assert mock_tedapi.current_power("BATTERY") == -500

    def test_current_power_all_locations(self, mock_tedapi):
        """Test current power for all locations"""
        mock_tedapi.pwcachetime = {"status": time.time()}

        result = mock_tedapi.current_power()
        assert result == {"LOAD": 1500, "SOLAR": 3000, "BATTERY": -500}

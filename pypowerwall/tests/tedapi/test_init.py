import time
from unittest.mock import patch
import math

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import compute_LL_voltage
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

class TestComputeLLVoltage:
    """Test compute_LL_voltage function for handling None values and voltage calculations"""
    
    def test_all_none_values(self):
        """Test grid down scenario where all voltages are None"""
        result = compute_LL_voltage(None, None, None)
        assert result == 0, "All None values should return 0"
    
    def test_all_zero_values(self):
        """Test scenario where all voltages are zero"""
        result = compute_LL_voltage(0, 0, 0)
        assert result == 0, "All zero values should return 0"
    
    def test_mixed_none_and_zero_values(self):
        """Test mixed None and zero values"""
        result = compute_LL_voltage(None, 0, None)
        assert result == 0, "Mixed None and zero should return 0"
    
    def test_single_phase_one_voltage(self):
        """Test single-phase system with one active voltage (UK style)"""
        result = compute_LL_voltage(230, None, None)
        assert result == 230, "Single voltage should be returned as-is"
        
        result = compute_LL_voltage(None, 240, None)
        assert result == 240, "Single voltage should be returned as-is"
        
        result = compute_LL_voltage(None, None, 230)
        assert result == 230, "Single voltage should be returned as-is"
    
    def test_single_phase_with_residual_voltage(self):
        """Test single-phase with residual voltage on inactive legs (below threshold)"""
        result = compute_LL_voltage(120, 50, None)
        # Only 120V is significant (>100V threshold), so it should return 120
        assert result == 120, "Should return only significant voltage"
        
        result = compute_LL_voltage(120, None, 80)
        assert result == 120, "Should ignore residual voltages below threshold"
    
    def test_split_phase_two_voltages(self):
        """Test split-phase system (North American 240V)"""
        result = compute_LL_voltage(120, 120, None)
        assert result == 240, "Split-phase should sum two voltages"
        
        result = compute_LL_voltage(110, 115, None)
        assert result == 225, "Split-phase should sum two voltages"
    
    def test_three_phase_voltages(self):
        """Test three-phase system calculations"""
        # Standard three-phase 208V system (120V phase-to-neutral)
        v1n = v2n = v3n = 120
        result = compute_LL_voltage(v1n, v2n, v3n)
        
        # For three-phase, line-to-line voltage = sqrt(3) * phase voltage
        # With 120V phase-to-neutral, we expect approximately 208V line-to-line
        expected = math.sqrt(v1n**2 + v2n**2 + v1n * v2n)
        assert abs(result - expected) < 0.1, f"Three-phase calculation incorrect: {result} vs {expected}"
        assert abs(result - 207.85) < 0.1, "Three-phase 120V should yield ~208V line-to-line"
    
    def test_three_phase_with_none_values(self):
        """Test three-phase calculation when None values are passed (regression test for bug)"""
        # This should not raise TypeError anymore
        result = compute_LL_voltage(None, 120, 120)
        # With one None converted to 0, we have effectively two voltages
        # sqrt(0^2 + 120^2 + 0*120) + sqrt(120^2 + 120^2 + 120*120) + sqrt(120^2 + 0^2 + 120*0)
        # = sqrt(14400) + sqrt(43200) + sqrt(14400) = 120 + 207.85 + 120 = 447.85 / 3 = 149.28
        assert isinstance(result, (int, float)), "Should return numeric value, not raise TypeError"
        assert result > 0, "Should calculate a positive voltage"
    
    def test_three_phase_european_400v(self):
        """Test three-phase European 400V system (230V phase-to-neutral)"""
        v1n = v2n = v3n = 230
        result = compute_LL_voltage(v1n, v2n, v3n)
        
        # European system: 230V phase-to-neutral, ~400V line-to-line
        expected = math.sqrt(v1n**2 + v2n**2 + v1n * v2n)
        assert abs(result - expected) < 0.1, "Three-phase 230V should yield ~400V"
        assert abs(result - 398.37) < 0.1, "European three-phase should be ~400V"
    
    def test_preserves_existing_numeric_behavior(self):
        """Test that existing numeric behavior is preserved"""
        # Single phase
        assert compute_LL_voltage(240, 0, 0) == 240
        
        # Split phase
        assert compute_LL_voltage(120, 120, 0) == 240
        
        # Three phase - verify calculation formula
        v1 = 120
        v2 = 120
        v3 = 120
        result = compute_LL_voltage(v1, v2, v3)
        v12 = math.sqrt(v1**2 + v2**2 + v1 * v2)
        v23 = math.sqrt(v2**2 + v3**2 + v2 * v3)
        v31 = math.sqrt(v3**2 + v1**2 + v3 * v1)
        expected = (v12 + v23 + v31) / 3
        assert abs(result - expected) < 0.001, "Existing three-phase formula should be preserved"
    
    def test_low_voltage_scenario(self):
        """Test low voltage scenario (all below threshold)"""
        result = compute_LL_voltage(50, 60, 40)
        # All below 100V threshold, should return sum
        assert result == 150, "Low voltages should be summed"
    
    def test_mixed_none_and_valid_values(self):
        """Test various combinations of None and valid values"""
        # One valid, two None
        assert compute_LL_voltage(240, None, None) == 240
        assert compute_LL_voltage(None, 240, None) == 240
        assert compute_LL_voltage(None, None, 240) == 240
        
        # Two valid, one None - should trigger split-phase logic
        assert compute_LL_voltage(120, 120, None) == 240
        assert compute_LL_voltage(120, None, 120) == 240
        assert compute_LL_voltage(None, 120, 120) == 240
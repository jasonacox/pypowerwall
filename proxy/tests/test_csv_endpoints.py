import json
import unittest
from contextlib import contextmanager
from http import HTTPStatus
from io import BytesIO
from unittest.mock import Mock, patch

import proxy
from proxy.server import Handler


class MockPowerwall:
    """Mock Powerwall object for testing"""
    def __init__(self):
        self.level_value = 50.0
        self.grid_value = 100.0
        self.solar_value = 500.0
        self.battery_value = -200.0
        self.home_value = 400.0
        self.grid_status_value = "UP"
        self.reserve_value = 20.0
        self.cloudmode = False
        self.fleetapi = False
        self.authmode = "cookie"
        self.timeout = 5
        self.auth = {}
        self.client = None

    def level(self):
        return self.level_value

    def grid(self):
        return self.grid_value

    def solar(self):
        return self.solar_value

    def battery(self):
        return self.battery_value

    def home(self):
        return self.home_value

    def grid_status(self):
        return self.grid_status_value

    def get_reserve(self):
        return self.reserve_value


class UnittestHandler(Handler):
    """A testable version of Handler that doesn't auto-handle requests"""

    def __init__(self):
        # Skip the parent __init__ to avoid automatic handling
        # Instead, set up the minimal attributes needed for testing
        self.path = ""
        self.send_response = Mock()
        self.send_header = Mock()
        self.end_headers = Mock()
        self.wfile = BytesIO()
        self.rfile = BytesIO()
        self.headers = {}
        self.client_address = ('127.0.0.1', 12345)
        self.server = Mock()
        self.request_version = 'HTTP/1.1'
        self.command = 'GET'


def common_patches(func):
    """Decorator to apply common patches to test methods"""
    @patch('proxy.server.api_base_url', '')
    @patch('proxy.server.proxystats', {
        'gets': 0, 'posts': 0, 'errors': 0, 'timeout': 0,
        'uri': {}, 'start': 1000, 'clear': 0
    })
    @patch('proxy.server.proxystats_lock')
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@contextmanager
def standard_test_patches():
    """Context manager for standard test patches"""
    with patch('proxy.server.proxystats_lock'), \
         patch('proxy.server.proxystats', {
             'gets': 0, 'posts': 0, 'errors': 0, 'timeout': 0,
             'uri': {}, 'start': 1000, 'clear': 0
         }), \
         patch('proxy.server.api_base_url', ''):
        yield

class BaseDoGetTest(unittest.TestCase):
    """Base test class with common setup and helper methods"""

    def setUp(self):
        """Common setup for all test cases"""
        # Use our testable handler
        self.handler = UnittestHandler()

        # Mock wfile.write for easier testing
        self.handler.wfile = Mock()
        self.handler.wfile.write = Mock()

    def get_written_json(self):
        """Helper to extract and parse JSON from written response"""
        written_data = self.handler.wfile.write.call_args[0][0]
        return json.loads(written_data.decode('utf8'))

    def get_written_text(self):
        """Helper to extract text from written response"""
        written_data = self.handler.wfile.write.call_args[0][0]
        return written_data.decode('utf8')

    def assert_json_response(self, expected_key, expected_value):
        """Helper to assert JSON response contains expected key-value"""
        result = self.get_written_json()
        self.assertIn(expected_key, result)
        self.assertEqual(result[expected_key], expected_value)
        
    def do_get(self, path: str) -> str:
        """
        Run Handler.do_GET for a given path under the standard patches
        and return the response body as text.
        """
        self.handler.path = path
        self.handler.command = "GET"
        with standard_test_patches():
            self.handler.do_GET()
        return self.get_written_text()


class TestDoGetAggregatesEndpoints(BaseDoGetTest):
    """Test cases for aggregates-related endpoints"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.get_performance_cached', return_value=None)  # Force cache miss
    @patch('proxy.server.cache_performance_response')  # Mock cache write
    def test_aggregates_endpoint(self, proxystats_lock, mock_cache_write, mock_cache_get, mock_safe_call, mock_pw):
        """Test /aggregates endpoint"""
        self.handler.path = "/aggregates"
        mock_pw.poll = Mock()
        mock_safe_call.return_value = {
            "solar": {"instant_power": 1000}
        }

        self.handler.do_GET()

        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        mock_safe_call.assert_called_once_with(
            "/aggregates", mock_pw.poll, "/api/meters/aggregates"
        )
        self.assertEqual(proxy.server.proxystats["gets"], 1)
        proxystats_lock.__enter__.assert_called_once()
        proxystats_lock.__exit__.assert_called_once()

        result = self.get_written_json()
        self.assertEqual(result["solar"]["instant_power"], 1000)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.get_performance_cached', return_value=None)  # Force cache miss
    @patch('proxy.server.cache_performance_response')  # Mock cache write
    def test_aggregates_with_negative_solar_adjustment(self, proxystats_lock, mock_cache_write, mock_cache_get, mock_safe_call, mock_pw):
        """Test aggregates with negative solar power adjustment"""
        self.handler.path = "/aggregates"
        mock_pw.poll = Mock()
        mock_safe_call.return_value = {
            "solar": {"instant_power": -500},
            "load": {"instant_power": 2000}
        }

        self.handler.do_GET()

        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        self.assertEqual(proxy.server.proxystats["gets"], 1)
        proxystats_lock.__enter__.assert_called_once()
        proxystats_lock.__exit__.assert_called_once()

        result = self.get_written_json()
        self.assertEqual(result["solar"]["instant_power"], 0)
        # Assert: load has been increased by the magnitude of negative solar
        # 2000 - (-500) = 2500
        self.assertIn("load", result)
        self.assertEqual(result["load"]["instant_power"], 2500)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.cache_performance_response')
    def test_cache_stores_processed_data(self, proxystats_lock, mock_cache_write, mock_safe_call, mock_pw):
        """Test that cache stores data AFTER negative solar processing"""
        with patch('proxy.server.get_performance_cached', return_value=None):  # Force fresh data generation
            self.handler.path = "/aggregates"
            mock_pw.poll = Mock()
            mock_safe_call.return_value = {
                "solar": {"instant_power": -300},
                "load": {"instant_power": 1500}
            }

            self.handler.do_GET()

            # Verify the cache was written with the PROCESSED data (solar=0, load=1800)
            mock_cache_write.assert_called_once()
            cache_key, cached_json = mock_cache_write.call_args[0]
            self.assertEqual(cache_key, "/aggregates")
            
            cached_data = json.loads(cached_json)
            self.assertEqual(cached_data["solar"]["instant_power"], 0)  # Should be clamped to 0
            self.assertEqual(cached_data["load"]["instant_power"], 1800)  # Should be 1500 - (-300) = 1800

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.cache_performance_response')
    def test_cache_hit_returns_processed_data(self, proxystats_lock, mock_cache_write, mock_safe_call, mock_pw):
        """Test that cache hits return already-processed data correctly"""
        # Simulate cached data that already has negative solar adjustment applied
        cached_processed_data = json.dumps({
            "solar": {"instant_power": 0},
            "load": {"instant_power": 1800}
        })
        
        with patch('proxy.server.get_performance_cached', return_value=cached_processed_data):
            self.handler.path = "/aggregates"
            mock_pw.poll = Mock()

            self.handler.do_GET()

            # safe_endpoint_call should NOT be called when cache hits
            mock_safe_call.assert_not_called()
            # cache_performance_response should NOT be called when cache hits
            mock_cache_write.assert_not_called()

            # Verify the cached processed data is returned correctly
            result = self.get_written_json()
            self.assertEqual(result["solar"]["instant_power"], 0)
            self.assertEqual(result["load"]["instant_power"], 1800)

    @common_patches
    @patch('proxy.server.pw') 
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.cache_performance_response')
    def test_cache_preserves_multiple_adjustments(self, proxystats_lock, mock_cache_write, mock_safe_call, mock_pw):
        """Test cache behavior with multiple different negative solar scenarios"""
        test_scenarios = [
            {
                "input": {"solar": {"instant_power": -100}, "load": {"instant_power": 800}},
                "expected": {"solar": {"instant_power": 0}, "load": {"instant_power": 900}}
            },
            {
                "input": {"solar": {"instant_power": -750}, "load": {"instant_power": 2000}}, 
                "expected": {"solar": {"instant_power": 0}, "load": {"instant_power": 2750}}
            }
        ]

        for i, scenario in enumerate(test_scenarios):
            with self.subTest(scenario=i):
                mock_cache_write.reset_mock()
                mock_safe_call.reset_mock()
                
                with patch('proxy.server.get_performance_cached', return_value=None):
                    self.handler.path = "/aggregates"
                    mock_safe_call.return_value = scenario["input"]

                    self.handler.do_GET()

                    # Verify correct processing and caching
                    mock_cache_write.assert_called_once()
                    cache_key, cached_json = mock_cache_write.call_args[0]
                    cached_data = json.loads(cached_json)
                    
                    self.assertEqual(cached_data["solar"]["instant_power"], 
                                   scenario["expected"]["solar"]["instant_power"])
                    self.assertEqual(cached_data["load"]["instant_power"], 
                                   scenario["expected"]["load"]["instant_power"])

    @common_patches  
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', True)  # Test with neg_solar ENABLED
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.get_performance_cached', return_value=None)
    @patch('proxy.server.cache_performance_response')
    def test_cache_respects_neg_solar_setting(self, proxystats_lock, mock_cache_write, mock_cache_get, mock_safe_call, mock_pw):
        """Test that cache respects neg_solar configuration setting"""
        self.handler.path = "/aggregates"
        mock_pw.poll = Mock()
        mock_safe_call.return_value = {
            "solar": {"instant_power": -200},
            "load": {"instant_power": 1000}
        }

        self.handler.do_GET()

        # When neg_solar=True, negative solar should be preserved (no adjustment)
        mock_cache_write.assert_called_once()
        cache_key, cached_json = mock_cache_write.call_args[0]
        cached_data = json.loads(cached_json)
        
        self.assertEqual(cached_data["solar"]["instant_power"], -200)  # Should preserve negative
        self.assertEqual(cached_data["load"]["instant_power"], 1000)   # Should remain unchanged


class TestDoGetStatsEndpoints(BaseDoGetTest):
    """Test cases for stats-related endpoints"""

    def test_stats_endpoint(self):
        """Test /stats endpoint - using context manager approach"""
        with standard_test_patches(), \
             patch('proxy.server.safe_pw_call') as mock_safe_call, \
             patch('proxy.server.resource') as mock_resource, \
             patch('proxy.server.time') as mock_time, \
             patch('proxy.server.pw') as mock_pw, \
             patch('proxy.server.health_check_enabled', False):

            self.handler.path = "/stats"
            mock_time.time.return_value = 2000
            mock_resource.getrusage.return_value = Mock(ru_maxrss=1024)
            mock_safe_call.return_value = "Test Site"
            mock_pw.cloudmode = False
            mock_pw.fleetapi = False

            self.handler.do_GET()

            result = self.get_written_json()
            self.assertEqual(result["ts"], 2000)
            self.assertEqual(result["mem"], 1024)

    def test_stats_clear_endpoint(self):
        """Test /stats/clear endpoint - using context manager with custom proxystats"""
        with patch('proxy.server.proxystats_lock'), \
             patch('proxy.server.proxystats', {'gets': 10, 'errors': 2, 'uri': {'/test': 5}, 'clear': 0}) as mock_stats, \
             patch('proxy.server.api_base_url', ''), \
             patch('proxy.server.time') as mock_time:

            self.handler.path = "/stats/clear"
            mock_time.time.return_value = 3000

            self.handler.do_GET()

            # Check that stats were cleared
            self.assertEqual(mock_stats["gets"], 1)
            self.assertEqual(mock_stats["errors"], 0)
            self.assertEqual(mock_stats["uri"], {'/stats/clear': 1})
            self.assertEqual(mock_stats["clear"], 3000)


class TestCSVEndpoints(BaseDoGetTest):
    """Test cases for CSV endpoints"""

    def setUp(self):
        """Clear performance cache before each test"""
        super().setUp()
        # Clear the performance cache to prevent test interference
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            pass

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_basic_output(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint basic output"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv"
            mock_pw.poll = Mock()
            
            # Mock the aggregates call
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100.5},
                'solar': {'instant_power': 200.25},
                'battery': {'instant_power': -50.75},
                'load': {'instant_power': 250.0}
            }
            
            # Mock the level call
            mock_safe_pw_call.return_value = 45.5
            
            self.handler.do_GET()
            
            self.handler.send_response.assert_called_with(HTTPStatus.OK)
            result = self.get_written_text()
            self.assertEqual(result, "100.50,250.00,200.25,-50.75,45.50\n")

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_with_headers(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint with headers"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv?headers"
            mock_pw.poll = Mock()
            
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100},
                'solar': {'instant_power': 200},
                'battery': {'instant_power': -50},
                'load': {'instant_power': 250}
            }
            
            mock_safe_pw_call.return_value = 45.5
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            self.assertIn("Grid,Home,Solar,Battery,BatteryLevel\n", result)
            self.assertIn("100.00,250.00,200.00,-50.00,45.50\n", result)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_fractional_values(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint with fractional values"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv"
            mock_pw.poll = Mock()
            
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 123.456},
                'solar': {'instant_power': 234.567},
                'battery': {'instant_power': -345.678},
                'load': {'instant_power': 456.789}
            }
            
            mock_safe_pw_call.return_value = 67.89
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            self.assertEqual(result, "123.46,456.79,234.57,-345.68,67.89\n")

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', True)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_negative_solar_enabled(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint with negative solar enabled"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv"
            mock_pw.poll = Mock()
            
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100},
                'solar': {'instant_power': -50},
                'battery': {'instant_power': 200},
                'load': {'instant_power': 250}
            }
            
            mock_safe_pw_call.return_value = 50.0
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            self.assertEqual(result, "100.00,250.00,-50.00,200.00,50.00\n")

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_negative_solar_disabled(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint with negative solar disabled (clamped to 0)"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv"
            mock_pw.poll = Mock()
            
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100},
                'solar': {'instant_power': -50},
                'battery': {'instant_power': 200},
                'load': {'instant_power': 250}
            }
            
            mock_safe_pw_call.return_value = 50.0
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            # Solar should be clamped to 0, and load adjusted: 250 - (-50) = 300
            self.assertEqual(result, "100.00,300.00,0.00,200.00,50.00\n")

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_with_null_values(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint with null aggregates"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv"
            mock_pw.poll = Mock()
            
            # Return None for aggregates (timeout/error case)
            mock_safe_endpoint_call.return_value = None
            mock_safe_pw_call.return_value = 0
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            self.assertEqual(result, "0.00,0.00,0.00,0.00,0.00\n")

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_zero_values(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint with zero values"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/csv"
            mock_pw.poll = Mock()
            
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 0},
                'solar': {'instant_power': 0},
                'battery': {'instant_power': 0},
                'load': {'instant_power': 0}
            }
            
            mock_safe_pw_call.return_value = 0
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            self.assertEqual(result, "0.00,0.00,0.00,0.00,0.00\n")


import json
import unittest
from contextlib import contextmanager
from http import HTTPStatus
from io import BytesIO
from unittest.mock import Mock, patch

import proxy
from proxy.server import Handler


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


class TestDoGetAggregatesEndpoints(BaseDoGetTest):
    """Test cases for aggregates-related endpoints"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    def test_aggregates_endpoint(self, proxystats_lock, mock_safe_call, mock_pw):
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
    def test_aggregates_with_negative_solar_adjustment(self, proxystats_lock, mock_safe_call, mock_pw):
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

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_csv_basic_output(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /csv endpoint basic output"""
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

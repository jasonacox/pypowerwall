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
    """Test cases for /csv endpoint"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_pw = MockPowerwall()

        # Patch the global Powerwall instance and safe_pw_call
        self.pw_patcher = patch("proxy.server.pw", self.mock_pw)
        self.safe_patcher = patch(
            "proxy.server.safe_pw_call",
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
        )

        self.pw_patcher.start()
        self.safe_patcher.start()

        super().setUp()

    def tearDown(self):
        self.pw_patcher.stop()
        self.safe_patcher.stop()

    def test_csv_basic_output(self):
        """Test basic /csv endpoint without headers"""
        body = self.do_get("/csv")
        expected = "100.00,400.00,500.00,-200.00,50.00\n"
        self.assertEqual(body, expected)

    def test_csv_with_headers(self):
        """Test /csv endpoint with headers parameter"""
        body = self.do_get("/csv?headers")
        expected = (
            "Grid,Home,Solar,Battery,BatteryLevel\n"
            "100.00,400.00,500.00,-200.00,50.00\n"
        )
        self.assertEqual(body, expected)

    def test_csv_with_null_values(self):
        """Test /csv endpoint when powerwall returns None values"""
        self.mock_pw.level_value = None
        self.mock_pw.grid_value = None
        self.mock_pw.solar_value = None
        self.mock_pw.battery_value = None
        self.mock_pw.home_value = None

        body = self.do_get("/csv")
        expected = "0.00,0.00,0.00,0.00,0.00\n"
        self.assertEqual(body, expected)

    def test_csv_negative_solar_disabled(self):
        """
        Test /csv with negative solar value when neg_solar=False.

        When neg_solar is False and solar is negative, we should:
        - add the magnitude of the solar value to home
        - clamp solar to 0
        """
        self.mock_pw.solar_value = -100.0
        self.mock_pw.home_value = 400.0

        with patch("proxy.server.neg_solar", False):
            body = self.do_get("/csv")

        # home goes from 400 → 500, solar clamped to 0
        expected = "100.00,500.00,0.00,-200.00,50.00\n"
        self.assertEqual(body, expected)

    def test_csv_negative_solar_enabled(self):
        """
        Test /csv with negative solar value when neg_solar=True.

        When neg_solar is True, we preserve the negative solar
        and do NOT shift it into home.
        """
        self.mock_pw.solar_value = -100.0

        with patch("proxy.server.neg_solar", True):
            body = self.do_get("/csv")

        expected = "100.00,400.00,-100.00,-200.00,50.00\n"
        self.assertEqual(body, expected)

    def test_csv_zero_values(self):
        """Test /csv with all zero values"""
        self.mock_pw.level_value = 0.0
        self.mock_pw.grid_value = 0.0
        self.mock_pw.solar_value = 0.0
        self.mock_pw.battery_value = 0.0
        self.mock_pw.home_value = 0.0

        body = self.do_get("/csv")
        expected = "0.00,0.00,0.00,0.00,0.00\n"
        self.assertEqual(body, expected)

    def test_csv_fractional_values(self):
        """Test /csv with fractional values for precision"""
        self.mock_pw.level_value = 75.555
        self.mock_pw.grid_value = 123.456
        self.mock_pw.solar_value = 789.123
        self.mock_pw.battery_value = -456.789
        self.mock_pw.home_value = 654.321

        body = self.do_get("/csv")
        expected = "123.46,654.32,789.12,-456.79,75.56\n"
        self.assertEqual(body, expected)

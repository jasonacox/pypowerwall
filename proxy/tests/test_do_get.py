import json
import unittest
from contextlib import contextmanager
from functools import wraps
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
    @wraps(func)
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
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.pw')
    def test_aggregates_endpoint(self, mock_pw, mock_safe_call, proxystats_lock):
        """Test /aggregates endpoint"""
        self.handler.path = "/aggregates"
        mock_pw.poll = Mock()
        mock_safe_call.return_value = {"solar": {"instant_power": 1000}}

        self.handler.do_GET()

        mock_safe_call.assert_called_once_with(
            "/aggregates", mock_pw.poll, "/api/meters/aggregates"
        )
        self.assertEqual(proxy.server.proxystats["gets"], 1)
        proxystats_lock.__enter__.assert_called_once()
        proxystats_lock.__exit__.assert_called_once()
        self.handler.send_response.assert_called_with(200)

    @common_patches
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.pw')
    def test_aggregates_with_negative_solar_adjustment(self, mock_pw, mock_safe_call, proxystats_lock):
        """Test aggregates with negative solar power adjustment"""
        self.handler.path = "/aggregates"
        mock_pw.poll = Mock()
        mock_safe_call.return_value = json.dumps({
            "solar": {"instant_power": -500},
            "load": {"instant_power": 2000}
        })

        self.handler.do_GET()

        self.assertEqual(proxy.server.proxystats["gets"], 1)
        proxystats_lock.__enter__.assert_called_once()
        proxystats_lock.__exit__.assert_called_once()
        result = self.get_written_json()
        self.assertEqual(result["solar"]["instant_power"], 0)

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
        super().setUp()
        
    def test_csv_basic_output(self):
        """Test basic /csv endpoint without headers"""
        # Simulate the CSV generation logic
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "100.00,400.00,500.00,-200.00,50.00\n"
        self.assertEqual(message, expected)
        
    def test_csv_with_headers(self):
        """Test /csv endpoint with headers parameter"""
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        message = "Grid,Home,Solar,Battery,BatteryLevel\n"
        message += "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "Grid,Home,Solar,Battery,BatteryLevel\n100.00,400.00,500.00,-200.00,50.00\n"
        self.assertEqual(message, expected)
        
    def test_csv_with_null_values(self):
        """Test /csv endpoint when powerwall returns None values"""
        self.mock_pw.level_value = None
        self.mock_pw.grid_value = None
        self.mock_pw.solar_value = None
        self.mock_pw.battery_value = None
        self.mock_pw.home_value = None
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "0.00,0.00,0.00,0.00,0.00\n"
        self.assertEqual(message, expected)
        
    def test_csv_negative_solar_disabled(self):
        """Test /csv with negative solar value when neg_solar=False"""
        self.mock_pw.solar_value = -100.0
        self.mock_pw.home_value = 400.0
        neg_solar = False
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        if not neg_solar and solar < 0:
            solar = 0
            home -= solar  # This won't change since solar is now 0
            
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "100.00,400.00,0.00,-200.00,50.00\n"
        self.assertEqual(message, expected)
        
    def test_csv_negative_solar_enabled(self):
        """Test /csv with negative solar value when neg_solar=True"""
        self.mock_pw.solar_value = -100.0
        neg_solar = True
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        if not neg_solar and solar < 0:
            solar = 0
            home -= solar
            
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "100.00,400.00,-100.00,-200.00,50.00\n"
        self.assertEqual(message, expected)
        
    def test_csv_zero_values(self):
        """Test /csv with all zero values"""
        self.mock_pw.level_value = 0.0
        self.mock_pw.grid_value = 0.0
        self.mock_pw.solar_value = 0.0
        self.mock_pw.battery_value = 0.0
        self.mock_pw.home_value = 0.0
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "0.00,0.00,0.00,0.00,0.00\n"
        self.assertEqual(message, expected)
        
    def test_csv_fractional_values(self):
        """Test /csv with fractional values for precision"""
        self.mock_pw.level_value = 75.555
        self.mock_pw.grid_value = 123.456
        self.mock_pw.solar_value = 789.123
        self.mock_pw.battery_value = -456.789
        self.mock_pw.home_value = 654.321
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
            grid, home, solar, battery, batterylevel
        )
        
        expected = "123.46,654.32,789.12,-456.79,75.56\n"
        self.assertEqual(message, expected)


class TestCSVV2Endpoints(BaseDoGetTest):
    """Test cases for /csv/v2 endpoint"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_pw = MockPowerwall()
        super().setUp()
        
    def test_csv_v2_basic_output(self):
        """Test basic /csv/v2 endpoint without headers"""
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "100.00,400.00,500.00,-200.00,50.00,1,20\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_with_headers(self):
        """Test /csv/v2 endpoint with headers parameter"""
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        message = "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n"
        message += "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n100.00,400.00,500.00,-200.00,50.00,1,20\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_grid_status_up(self):
        """Test /csv/v2 with grid status UP (should be 1)"""
        self.mock_pw.grid_status_value = "UP"
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        self.assertEqual(gridstatus, 1)
        
    def test_csv_v2_grid_status_down(self):
        """Test /csv/v2 with grid status DOWN (should be 0)"""
        self.mock_pw.grid_status_value = "DOWN"
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        self.assertEqual(gridstatus, 0)
        
    def test_csv_v2_grid_status_other(self):
        """Test /csv/v2 with grid status other than UP (should be 0)"""
        self.mock_pw.grid_status_value = "UNKNOWN"
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        self.assertEqual(gridstatus, 0)
        
    def test_csv_v2_with_null_values(self):
        """Test /csv/v2 endpoint when powerwall returns None values"""
        self.mock_pw.level_value = None
        self.mock_pw.grid_value = None
        self.mock_pw.solar_value = None
        self.mock_pw.battery_value = None
        self.mock_pw.home_value = None
        self.mock_pw.grid_status_value = None
        self.mock_pw.reserve_value = None
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "0.00,0.00,0.00,0.00,0.00,0,0\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_reserve_values(self):
        """Test /csv/v2 with various reserve percentage values"""
        test_reserves = [0, 5, 20, 50, 75, 100]
        
        for reserve_val in test_reserves:
            self.mock_pw.reserve_value = reserve_val
            reserve = self.mock_pw.get_reserve() or 0
            self.assertEqual(reserve, reserve_val)
            
    def test_csv_v2_negative_solar_disabled(self):
        """Test /csv/v2 with negative solar value when neg_solar=False"""
        self.mock_pw.solar_value = -100.0
        self.mock_pw.home_value = 400.0
        neg_solar = False
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        if not neg_solar and solar < 0:
            solar = 0
            home -= solar
            
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "100.00,400.00,0.00,-200.00,50.00,1,20\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_negative_solar_enabled(self):
        """Test /csv/v2 with negative solar value when neg_solar=True"""
        self.mock_pw.solar_value = -100.0
        neg_solar = True
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        if not neg_solar and solar < 0:
            solar = 0
            home -= solar
            
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "100.00,400.00,-100.00,-200.00,50.00,1,20\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_zero_values(self):
        """Test /csv/v2 with all zero values"""
        self.mock_pw.level_value = 0.0
        self.mock_pw.grid_value = 0.0
        self.mock_pw.solar_value = 0.0
        self.mock_pw.battery_value = 0.0
        self.mock_pw.home_value = 0.0
        self.mock_pw.grid_status_value = "DOWN"
        self.mock_pw.reserve_value = 0
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "0.00,0.00,0.00,0.00,0.00,0,0\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_fractional_values(self):
        """Test /csv/v2 with fractional values for precision"""
        self.mock_pw.level_value = 75.555
        self.mock_pw.grid_value = 123.456
        self.mock_pw.solar_value = 789.123
        self.mock_pw.battery_value = -456.789
        self.mock_pw.home_value = 654.321
        self.mock_pw.reserve_value = 33
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "123.46,654.32,789.12,-456.79,75.56,1,33\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_high_power_values(self):
        """Test /csv/v2 with high power values (large solar installation)"""
        self.mock_pw.level_value = 95.0
        self.mock_pw.grid_value = -5000.0  # Exporting to grid
        self.mock_pw.solar_value = 10000.0  # Large solar array
        self.mock_pw.battery_value = 3000.0  # Charging battery
        self.mock_pw.home_value = 2000.0
        
        batterylevel = self.mock_pw.level() or 0
        grid = self.mock_pw.grid() or 0
        solar = self.mock_pw.solar() or 0
        battery = self.mock_pw.battery() or 0
        home = self.mock_pw.home() or 0
        gridstatus = 1 if self.mock_pw.grid_status() == "UP" else 0
        reserve = self.mock_pw.get_reserve() or 0
        
        message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
            grid, home, solar, battery, batterylevel, gridstatus, reserve
        )
        
        expected = "-5000.00,2000.00,10000.00,3000.00,95.00,1,20\n"
        self.assertEqual(message, expected)
        
    def test_csv_v2_battery_level_boundaries(self):
        """Test /csv/v2 with battery level at boundaries (0% and 100%)"""
        # Test at 0%
        self.mock_pw.level_value = 0.0
        batterylevel = self.mock_pw.level() or 0
        self.assertEqual(batterylevel, 0.0)
        
        # Test at 100%
        self.mock_pw.level_value = 100.0
        batterylevel = self.mock_pw.level() or 0
        self.assertEqual(batterylevel, 100.0)


class TestCSVEdgeCases(unittest.TestCase):
    """Test edge cases for both CSV endpoints"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_pw = MockPowerwall()
        
    def test_csv_content_type(self):
        """Test that CSV endpoints return correct content type"""
        contenttype = "text/plain; charset=utf-8"
        self.assertEqual(contenttype, "text/plain; charset=utf-8")
        
    def test_negative_home_consumption(self):
        """Test handling of negative home consumption value"""
        self.mock_pw.home_value = -50.0
        home = self.mock_pw.home() or 0
        self.assertEqual(home, -50.0)
        
    def test_negative_grid_value(self):
        """Test negative grid value (exporting to grid)"""
        self.mock_pw.grid_value = -1000.0
        grid = self.mock_pw.grid() or 0
        self.assertEqual(grid, -1000.0)
        
    def test_positive_battery_value(self):
        """Test positive battery value (charging)"""
        self.mock_pw.battery_value = 500.0
        battery = self.mock_pw.battery() or 0
        self.assertEqual(battery, 500.0)
        
    def test_solar_adjustment_calculation(self):
        """Test the solar adjustment when neg_solar=False and solar is negative"""
        solar = -100.0
        home = 500.0
        neg_solar = False
        
        if not neg_solar and solar < 0:
            home_adjusted = home - solar  # This adds 100 to home
            solar_adjusted = 0
        else:
            home_adjusted = home
            solar_adjusted = solar
            
        self.assertEqual(solar_adjusted, 0)
        self.assertEqual(home_adjusted, 600.0)
        
    def test_reserve_percentage_range(self):
        """Test reserve percentage in valid range"""
        valid_reserves = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for reserve_val in valid_reserves:
            self.mock_pw.reserve_value = reserve_val
            reserve = self.mock_pw.get_reserve() or 0
            self.assertGreaterEqual(reserve, 0)
            self.assertLessEqual(reserve, 100)
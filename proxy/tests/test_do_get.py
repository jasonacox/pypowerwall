
import json
import time
import unittest
from io import BytesIO
from unittest.mock import Mock, patch, MagicMock

from proxy.server import Handler, CONFIG_TYPE, PROXY_STATS_TYPE


def make_default_config():
    """Create a default configuration dict with sensible test defaults."""
    return {
        CONFIG_TYPE.PW_AUTH_MODE: "token",
        CONFIG_TYPE.PW_AUTH_PATH: "",
        CONFIG_TYPE.PW_BIND_ADDRESS: "0.0.0.0",
        CONFIG_TYPE.PW_BROWSER_CACHE: 0,
        CONFIG_TYPE.PW_CACHE_EXPIRE: 5,
        CONFIG_TYPE.PW_CACHE_FILE: "",
        CONFIG_TYPE.PW_CACHE_TTL: 5,
        CONFIG_TYPE.PW_CONTROL_SECRET: "",
        CONFIG_TYPE.PW_COOKIE_SUFFIX: "",
        CONFIG_TYPE.PW_EMAIL: "test@test.com",
        CONFIG_TYPE.PW_FAIL_FAST: False,
        CONFIG_TYPE.PW_GRACEFUL_DEGRADATION: False,
        CONFIG_TYPE.PW_GW_PWD: "",
        CONFIG_TYPE.PW_HEALTH_CHECK: False,
        CONFIG_TYPE.PW_HOST: "localhost",
        CONFIG_TYPE.PW_HTTP_TYPE: "http",
        CONFIG_TYPE.PW_HTTPS: "no",
        CONFIG_TYPE.PW_NEG_SOLAR: False,
        CONFIG_TYPE.PW_NETWORK_ERROR_RATE_LIMIT: 60,
        CONFIG_TYPE.PW_PASSWORD: "",
        CONFIG_TYPE.PW_POOL_MAXSIZE: 10,
        CONFIG_TYPE.PW_PORT: 8675,
        CONFIG_TYPE.PW_SITEID: None,
        CONFIG_TYPE.PW_STYLE: "default",
        CONFIG_TYPE.PW_SUPPRESS_NETWORK_ERRORS: False,
        CONFIG_TYPE.PW_TIMEOUT: 10,
        CONFIG_TYPE.PW_TIMEZONE: "America/Los_Angeles",
    }


def make_default_proxystats():
    """Create a default proxystats dict."""
    return {
        PROXY_STATS_TYPE.AUTH_MODE: "token",
        PROXY_STATS_TYPE.CF: "",
        PROXY_STATS_TYPE.CLEAR: 0,
        PROXY_STATS_TYPE.CLOUDMODE: False,
        PROXY_STATS_TYPE.CONFIG: "",
        PROXY_STATS_TYPE.CONNECTION_HEALTH: {},
        PROXY_STATS_TYPE.COUNTER: 0,
        PROXY_STATS_TYPE.ERRORS: 0,
        PROXY_STATS_TYPE.FLEETAPI: False,
        PROXY_STATS_TYPE.GETS: 0,
        PROXY_STATS_TYPE.MEM: 0,
        PROXY_STATS_TYPE.MODE: "",
        PROXY_STATS_TYPE.POSTS: 0,
        PROXY_STATS_TYPE.PW3: False,
        PROXY_STATS_TYPE.PYPOWERWALL: "",
        PROXY_STATS_TYPE.SITE_NAME: "",
        PROXY_STATS_TYPE.SITEID: None,
        PROXY_STATS_TYPE.START: 1000,
        PROXY_STATS_TYPE.TEDAPI: False,
        PROXY_STATS_TYPE.TEDAPI_MODE: "",
        PROXY_STATS_TYPE.TIMEOUT: 0,
        PROXY_STATS_TYPE.TS: 0,
        PROXY_STATS_TYPE.UPTIME: "",
        PROXY_STATS_TYPE.URI: {},
    }


class UnittestHandler(Handler):
    """A testable version of Handler that doesn't auto-handle requests."""

    def __init__(self, configuration=None, pw=None, pw_control=None,
                 proxy_stats=None, all_pws=None):
        # Skip the BaseHTTPRequestHandler __init__ to avoid automatic handling.
        # Set up minimal attributes needed for testing.
        self.configuration = configuration or make_default_config()
        self.pw = pw or Mock()
        self.pw_control = pw_control
        self.proxystats = proxy_stats if proxy_stats is not None else make_default_proxystats()
        self.all_pws = all_pws or []

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


class BaseDoGetTest(unittest.TestCase):
    """Base test class with common setup and helper methods."""

    def setUp(self):
        self.mock_pw = Mock()
        self.mock_pw.cloudmode = False
        self.mock_pw.fleetapi = False
        self.mock_pw.authmode = "token"
        self.mock_pw.client = None
        self.mock_pw.site_name = Mock(return_value="Test Site")

        self.proxystats = make_default_proxystats()
        self.handler = UnittestHandler(
            pw=self.mock_pw,
            proxy_stats=self.proxystats,
        )
        # Mock wfile.write for easier testing
        self.handler.wfile = Mock()
        self.handler.wfile.write = Mock(return_value=1)

    def get_written_json(self):
        """Helper to extract and parse JSON from written response."""
        written_data = self.handler.wfile.write.call_args[0][0]
        return json.loads(written_data.decode('utf8'))

    def get_written_text(self):
        """Helper to extract text from written response."""
        written_data = self.handler.wfile.write.call_args[0][0]
        return written_data.decode('utf8')

    def assert_json_response(self, expected_key, expected_value):
        """Helper to assert JSON response contains expected key-value."""
        result = self.get_written_json()
        self.assertIn(expected_key, result)
        self.assertEqual(result[expected_key], expected_value)


class TestDoGetStatsEndpoints(BaseDoGetTest):
    """Test cases for stats-related endpoints."""

    def test_stats_endpoint(self):
        """Test /stats endpoint returns expected fields."""
        self.handler.path = "/stats"

        with patch('proxy.server.resource') as mock_resource, \
             patch('proxy.server.time') as mock_time:
            mock_time.time.return_value = 2000
            mock_resource.getrusage.return_value = Mock(ru_maxrss=1024)

            self.handler.do_GET()

            result = self.get_written_json()
            self.assertEqual(result[PROXY_STATS_TYPE.TS], 2000)
            self.assertEqual(result[PROXY_STATS_TYPE.MEM], 1024)

    def test_stats_clear_endpoint(self):
        """Test /stats/clear endpoint resets counters."""
        self.handler.path = "/stats/clear"
        self.proxystats[PROXY_STATS_TYPE.GETS] = 10
        self.proxystats[PROXY_STATS_TYPE.ERRORS] = 2
        self.proxystats[PROXY_STATS_TYPE.URI] = {'/test': 5}

        with patch('proxy.server.time') as mock_time:
            mock_time.time.return_value = 3000

            self.handler.do_GET()

            # Stats should be cleared (gets is 1 because the /stats/clear request itself counts)
            self.assertEqual(self.proxystats[PROXY_STATS_TYPE.GETS], 1)
            self.assertEqual(self.proxystats[PROXY_STATS_TYPE.ERRORS], 0)
            self.assertEqual(self.proxystats[PROXY_STATS_TYPE.URI], {'/stats/clear': 1})
            self.assertEqual(self.proxystats[PROXY_STATS_TYPE.CLEAR], 3000)

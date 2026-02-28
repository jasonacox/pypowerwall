#!/usr/bin/env python
# pyPowerWall Module - Proxy Server Tool
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Proxy Server Tool
    This tool will proxy API calls to /api/meters/aggregates and
    /api/system_status/soe - You can containerize it and run it as
    an endpoint for tools like telegraf to pull metrics.

 Local Powerwall Mode
    The default mode for this proxy is to connect to a local Powerwall
    to pull data. This works with the Tesla Energy Gateway (TEG) for
    Powerwall 1, 2 and +.  It will also support pulling /vitals and /strings
    data if available.
    Set: PW_HOST to Powerwall Address and PW_PASSWORD to use this mode.

 Cloud Mode
    An optional mode is to connect to the Tesla Cloud to pull data. This
    requires that you have a Tesla Account and have registered your
    Tesla Solar System or Powerwall with the Tesla App. It requires that
    you run the setup 'python -m pypowerwall setup' process to create the
    required API keys and tokens.  This mode doesn't support /vitals or
    /strings data.
    Set: PW_EMAIL and leave PW_HOST blank to use this mode.

 Control Mode
    An optional mode is to enable control commands to set backup reserve
    percentage and mode of the Powerwall.  This requires that you set
    and use the PW_CONTROL_SECRET environmental variable.  This mode
    is disabled by default and should be used with caution.
    Set: PW_CONTROL_SECRET to enable this mode.

"""
import copy
import datetime
import json
import logging
import os
import resource
import signal
import socket
import ssl
import sys
import threading
import time
from enum import StrEnum, auto
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
from typing import Any, Dict, Final, List, Set, Tuple
from urllib.parse import parse_qs, urlparse

import psutil
import requests
import urllib3
from pyroute2 import IPRoute
from transform import get_static, inject_js

import pypowerwall
from pypowerwall import parse_version
from pypowerwall.cloud.exceptions import (
    PyPowerwallCloudInvalidPayload,
    PyPowerwallCloudNoTeslaAuthFile,
    PyPowerwallCloudNotImplemented,
    PyPowerwallCloudTeslaNotConnected,
)
from pypowerwall.exceptions import (
    InvalidBatteryReserveLevelException,
    PyPowerwallInvalidConfigurationParameter,
)
from pypowerwall.fleetapi.exceptions import (
    PyPowerwallFleetAPIInvalidPayload,
    PyPowerwallFleetAPINoTeslaAuthFile,
    PyPowerwallFleetAPINotImplemented,
    PyPowerwallFleetAPITeslaNotConnected,
)
from pypowerwall.local.exceptions import (
    LoginError,
    PowerwallConnectionError,
)
from pypowerwall.tedapi.exceptions import (
    PyPowerwallTEDAPIInvalidPayload,
    PyPowerwallTEDAPINoTeslaAuthFile,
    PyPowerwallTEDAPINotImplemented,
    PyPowerwallTEDAPITeslaNotConnected,
)

BUILD: Final[str] = "t67"
# Build from here
# Fix cache expiration bug and update version to 0.12.2 #122
#https://github.com/jasonacox/pypowerwall/commit/365ad94a817da5dbe6b583fae038512bdfff12cc
UTF_8: Final[str] = "utf-8"

ALLOWLIST: Final[Set[str]] = {
    '/api/auth/toggle/supported',
    '/api/customer',
    '/api/customer/registration',
    '/api/installer',
    '/api/meters',
    '/api/meters/readings',
    '/api/meters/site',
    '/api/meters/solar',
    '/api/networks',
    '/api/operation',
    '/api/powerwalls',
    '/api/site_info',
    '/api/site_info/grid_codes',
    '/api/site_info/site_name',
    '/api/sitemaster',
    '/api/solar_powerwall',
    '/api/solars',
    '/api/solars/brands',
    '/api/status',
    '/api/synchrometer/ct_voltage_references',
    '/api/system_status',
    '/api/system_status/grid_faults',
    '/api/system_status/grid_status',
    '/api/system/networks',
    '/api/system/update/status',
    '/api/troubleshooting/problems',
}

DISABLED: Final[Set[str]] = set([
    '/api/customer/registration',
    '/networks'
])
WEB_ROOT: Final[str] = os.path.join(os.path.dirname(__file__), "web")
SERVER_DEBUG: Final[bool] = bool(os.getenv("PW_DEBUG", "no").lower() == "yes")

# Logging configuration
log = logging.getLogger("proxy")
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
log.setLevel(logging.DEBUG if SERVER_DEBUG else logging.INFO)

# Signal handler - Exit on SIGTERM
# noinspection PyUnusedLocal
def sig_term_handle(signum, frame):
    raise SystemExit

signal.signal(signal.SIGTERM, sig_term_handle)

if SERVER_DEBUG:
    pypowerwall.set_debug(True)


class CONFIG_TYPE(StrEnum):
    """_summary_

    Args:
        StrEnum (_type_): _description_
    """
    PW_AUTH_MODE = auto()
    PW_AUTH_PATH = auto()
    PW_BIND_ADDRESS = auto()
    PW_BROWSER_CACHE = auto()
    PW_CACHE_EXPIRE = auto()
    PW_CACHE_FILE = auto()
    PW_CACHE_TTL = auto()
    PW_CONTROL_SECRET = auto()
    PW_COOKIE_SUFFIX = auto()
    PW_EMAIL = auto()
    PW_FAIL_FAST = auto()
    PW_GRACEFUL_DEGRADATION = auto()
    PW_GW_PWD = auto()
    PW_HEALTH_CHECK = auto()
    PW_HOST = auto()
    PW_HTTP_TYPE = auto()
    PW_HTTPS = auto()
    PW_NEG_SOLAR = auto()
    PW_NETWORK_ERROR_RATE_LIMIT = auto()
    PW_PASSWORD = auto()
    PW_POOL_MAXSIZE = auto()
    PW_PORT = auto()
    PW_SITEID = auto()
    PW_STYLE = auto()
    PW_SUPPRESS_NETWORK_ERRORS = auto()
    PW_TIMEOUT = auto()
    PW_TIMEZONE = auto()


class PROXY_STATS_TYPE(StrEnum):
    """_summary_

    Args:
        StrEnum (_type_): _description_
    """
    AUTH_MODE = auto()
    CF = auto()
    CLEAR = auto()
    CLOUDMODE = auto()
    CONFIG = auto()
    CONNECTION_HEALTH = auto()
    COUNTER = auto()
    ERRORS = auto()
    FLEETAPI = auto()
    GETS = auto()
    MEM = auto()
    MODE = auto()
    POSTS = auto()
    PW3 = auto()
    PYPOWERWALL = auto()
    SITE_NAME = auto()
    SITEID = auto()
    START = auto()
    TEDAPI = auto()
    TEDAPI_MODE = auto()
    TIMEOUT = auto()
    TS = auto()
    UPTIME = auto()
    URI = auto()

# Configuration for Proxy - Check for environmental variables
#    and always use those if available (required for Docker)
# Configuration - Environment variables
type PROXY_CONFIG = Dict[CONFIG_TYPE, str | int | bool | None]
type PROXY_STATS = Dict[PROXY_STATS_TYPE, str | int | bool | None | PROXY_CONFIG | Dict[str, int]]


def get_local_ip() -> IPv4Address:
    """
    Retrieve the local IPv4 address associated with the system's default network interface.

    This function determines the default network interface by inspecting the system's routing
    table for a route with a destination length of 0 (i.e., the default route). It then retrieves
    the interface name corresponding to that route and uses the `psutil` library to obtain the
    associated IPv4 address. The resulting IP address is returned as an `ipaddress.IPv4Address`
    object, ensuring a strongly typed representation.

    Returns:
        ipaddress.IPv4Address: The IPv4 address of the default network interface.

    Raises:
        RuntimeError: If the default network interface, the interface name, or the IPv4 address
                      cannot be found.
        Exception: Propagates any unexpected exceptions raised by the underlying libraries.
    """

    with IPRoute() as ip:
        iface_index = next(
            (
                iface_index
                for route in ip.get_routes(family=socket.AF_INET)
                if route.get('dst_len', 0) == 0
                for key, iface_index in route.get('attrs', [])
                if key == 'RTA_OIF'
            ),
            None
        )
        if iface_index is None:
            raise RuntimeError("Default network interface not found.")

        iface_name = next(
            (
                name for key, name in ip.link('get', index=iface_index)[0].get('attrs', [])
                if key == 'IFLA_IFNAME'
            ),
            None
        )
        if iface_name is None:
            raise RuntimeError("Interface name not found.")

    addrs = psutil.net_if_addrs().get(iface_name, [])
    ip_addr_str = next(
        (addr.address for addr in addrs if addr.family == socket.AF_INET),
        None
    )
    if ip_addr_str is None:
        raise RuntimeError(f"No IPv4 address found for interface '{iface_name}'.")

    return IPv4Address(ip_addr_str)


# Get Value Function - Key to Value or Return Null
def get_value(a, key):
    value = a.get(key)
    if value is None:
        log.debug(f"Missing key in payload [{key}]")
    return value


# Rate limiter for network error logging to prevent spam
_error_counts: Dict[str, int] = {}
_error_counts_lock = threading.RLock()
_network_error_summary: Dict[str, Dict[str, int]] = {}
_last_summary_time = time.time()


def should_log_network_error(func_name: str, max_per_minute: int = 5) -> bool:
    """
    Rate limit network error logging to prevent log spam.
    Allow max_per_minute errors per function per minute.
    """
    current_time = time.time()
    minute_bucket = int(current_time // 60)
    key = f"{func_name}_{minute_bucket}"

    with _error_counts_lock:
        _error_counts[key] = _error_counts.get(key, 0) + 1

        # Clean up old entries (keep only current and previous minute)
        current_keys = {f"{func_name}_{minute_bucket}", f"{func_name}_{minute_bucket - 1}"}
        keys_to_remove = [k for k in _error_counts if k not in current_keys and k.startswith(f"{func_name}_")]
        for k in keys_to_remove:
            del _error_counts[k]

        return _error_counts[key] <= max_per_minute


def track_network_error(func_name: str, error_type: str) -> None:
    """Track network errors for summary reporting."""
    global _network_error_summary, _last_summary_time

    with _error_counts_lock:
        _network_error_summary.setdefault(func_name, {})
        _network_error_summary[func_name][error_type] = _network_error_summary[func_name].get(error_type, 0) + 1

        # Log summary every 5 minutes if there are errors
        current_time = time.time()
        if current_time - _last_summary_time > 300:
            if _network_error_summary:
                log.warning("Network Error Summary (last 5 minutes):")
                for func, errors in _network_error_summary.items():
                    for etype, count in errors.items():
                        log.warning(f"  {func}: {count} {etype} errors")
                _network_error_summary.clear()
            _last_summary_time = current_time


# Connection health tracking
_connection_health = {
    'consecutive_failures': 0,
    'last_success_time': time.time(),
    'total_failures': 0,
    'total_successes': 0,
    'is_degraded': False,
}
_connection_health_lock = threading.RLock()

# Cache for last known good responses (graceful degradation)
_last_good_responses: Dict[str, tuple] = {}
_last_good_responses_lock = threading.RLock()

# Health thresholds
HEALTH_FAILURE_THRESHOLD: Final[int] = 5   # consecutive failures before degraded mode
HEALTH_RECOVERY_THRESHOLD: Final[int] = 3  # consecutive successes to exit degraded mode


def update_connection_health(success: bool = True) -> None:
    """Update connection health metrics and degraded mode status."""
    with _connection_health_lock:
        if success:
            _connection_health['consecutive_failures'] = 0
            _connection_health['last_success_time'] = time.time()
            _connection_health['total_successes'] += 1
            if _connection_health['is_degraded']:
                if _connection_health['total_successes'] % HEALTH_RECOVERY_THRESHOLD == 0:
                    _connection_health['is_degraded'] = False
                    log.info("Connection health recovered - exiting degraded mode")
        else:
            _connection_health['consecutive_failures'] += 1
            _connection_health['total_failures'] += 1
            if not _connection_health['is_degraded']:
                if _connection_health['consecutive_failures'] >= HEALTH_FAILURE_THRESHOLD:
                    _connection_health['is_degraded'] = True
                    log.warning(f"Connection health degraded after {HEALTH_FAILURE_THRESHOLD} consecutive failures")


def get_cached_response(endpoint: str, cache_ttl: int) -> Any:
    """Get cached response for graceful degradation."""
    with _last_good_responses_lock:
        if endpoint in _last_good_responses:
            cached_data, timestamp = _last_good_responses[endpoint]
            age = time.time() - timestamp
            if age < cache_ttl:
                log.debug(f"Using cached response for {endpoint} (age: {age:.1f}s)")
                return cached_data
            else:
                log.debug(f"Cache expired for {endpoint} (age: {age:.1f}s > {cache_ttl}s)")
                del _last_good_responses[endpoint]
    return None


def cache_response(endpoint: str, response: Any) -> None:
    """Cache successful response for graceful degradation."""
    if response is None:
        return
    with _last_good_responses_lock:
        _last_good_responses[endpoint] = (response, time.time())
        # Limit cache size to prevent memory growth
        if len(_last_good_responses) > 50:
            oldest_key = min(_last_good_responses, key=lambda k: _last_good_responses[k][1])
            del _last_good_responses[oldest_key]


def configure_pw_control(pw: pypowerwall.Powerwall, configuration: PROXY_CONFIG) -> pypowerwall.Powerwall:
    if not configuration[CONFIG_TYPE.PW_CONTROL_SECRET]:
        return None

    log.info("Control Commands Activating - WARNING: Use with caution!")
    try:
        if pw.cloudmode or pw.fleetapi:
            pw_control = pw
        else:
            pw_control = pypowerwall.Powerwall(
                "",
                configuration[CONFIG_TYPE.PW_PASSWORD],
                configuration[CONFIG_TYPE.PW_EMAIL],
                siteid=configuration[CONFIG_TYPE.PW_SITEID],
                authpath=configuration[CONFIG_TYPE.PW_AUTH_PATH],
                authmode=configuration[CONFIG_TYPE.PW_AUTH_MODE],
                cachefile=configuration[CONFIG_TYPE.PW_CACHE_FILE],
                auto_select=True
            )
    except Exception as e:
        log.error(f"Control Mode Failed {e}: Unable to connect to cloud - Run Setup")
        configuration[CONFIG_TYPE.PW_CONTROL_SECRET] = None
        return None

    if pw_control:
        log.info(f"Control Mode Enabled: Cloud Mode ({pw_control.mode}) Connected")
    else:
        log.error("Control Mode Failed: Unable to connect to cloud - Run Setup")
        configuration[CONFIG_TYPE.PW_CONTROL_SECRET] = None
        return None

    return pw_control


class Handler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server,
                 configuration: PROXY_CONFIG, pw: pypowerwall.Powerwall, pw_control: pypowerwall.Powerwall, proxy_stats: PROXY_STATS,
                 all_pws: List[Tuple[pypowerwall.Powerwall, pypowerwall.Powerwall, PROXY_CONFIG]]):
        self.configuration = configuration
        self.pw = pw
        self.pw_control = pw_control
        self.proxystats = proxy_stats
        self.all_pws = all_pws
        super().__init__(request, client_address, server)

    def log_message(self, log_format, *args):
        if SERVER_DEBUG:
            log.debug(f"{self.address_string()} {log_format % args}")

    def address_string(self):
        # replace function to avoid lookup delays
        hostaddr, hostport = self.client_address[:2]
        return hostaddr

    def send_json_response(self, data, status_code=HTTPStatus.OK, content_type='application/json') -> str:
        response = json.dumps(data)
        try:
            self.send_response(status_code)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(response)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.wfile.write(response.encode(UTF_8)) > 0:
                return response
        except Exception as exc:
            log.debug(f"Error sending response: {exc}")
            self.proxystats[PROXY_STATS_TYPE.ERRORS] = int(self.proxystats[PROXY_STATS_TYPE.ERRORS]) + 1
        return response


    def safe_pw_call(self, pw_func, *args, **kwargs):
        """
        Safely call a pypowerwall function with global exception handling.
        Returns None on any exception and logs a clean error message.
        Includes health tracking, fail-fast mode, and rate-limited logging.
        """
        # In fail-fast mode with degraded connection, return None immediately
        if self.configuration[CONFIG_TYPE.PW_FAIL_FAST] and self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
            with _connection_health_lock:
                if _connection_health['is_degraded']:
                    return None

        try:
            result = pw_func(*args, **kwargs)
            if self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
                update_connection_health(success=True)
            return result
        except (PyPowerwallInvalidConfigurationParameter,
                InvalidBatteryReserveLevelException,
                PyPowerwallTEDAPINoTeslaAuthFile,
                PyPowerwallTEDAPITeslaNotConnected,
                PyPowerwallTEDAPINotImplemented,
                PyPowerwallTEDAPIInvalidPayload,
                PyPowerwallFleetAPINoTeslaAuthFile,
                PyPowerwallFleetAPITeslaNotConnected,
                PyPowerwallFleetAPINotImplemented,
                PyPowerwallFleetAPIInvalidPayload,
                PyPowerwallCloudNoTeslaAuthFile,
                PyPowerwallCloudTeslaNotConnected,
                PyPowerwallCloudNotImplemented,
                PyPowerwallCloudInvalidPayload,
                LoginError,
                PowerwallConnectionError) as e:
            func_name = getattr(pw_func, '__name__', str(pw_func))
            log.warning(f"Powerwall API Error in {func_name}: {e}")
            self.proxystats[PROXY_STATS_TYPE.ERRORS] += 1
            return None
        except (ConnectionError,
                TimeoutError,
                OSError,
                requests.exceptions.RequestException,
                requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError,
                urllib3.exceptions.ReadTimeoutError,
                urllib3.exceptions.ConnectTimeoutError,
                urllib3.exceptions.TimeoutError,
                urllib3.exceptions.MaxRetryError) as e:
            func_name = getattr(pw_func, '__name__', str(pw_func))
            error_type = type(e).__name__

            if self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
                update_connection_health(success=False)

            track_network_error(func_name, error_type)

            rate_limit = self.configuration[CONFIG_TYPE.PW_NETWORK_ERROR_RATE_LIMIT]
            if not self.configuration[CONFIG_TYPE.PW_SUPPRESS_NETWORK_ERRORS] and should_log_network_error(func_name, rate_limit):
                if "timeout" in error_type.lower():
                    log.info(f"Network timeout in {func_name}: {error_type}")
                else:
                    log.info(f"Network error in {func_name}: {error_type}")

            self.proxystats[PROXY_STATS_TYPE.TIMEOUT] += 1
            return None
        except Exception as e:
            func_name = getattr(pw_func, '__name__', str(pw_func))
            error_type = type(e).__name__

            if self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
                update_connection_health(success=False)

            if SERVER_DEBUG:
                log.error(f"Unexpected error in {func_name}: {error_type}: {e}")
            else:
                log.warning(f"Unexpected error in {func_name}: {error_type}")
            self.proxystats[PROXY_STATS_TYPE.ERRORS] += 1
            return None

    def safe_endpoint_call(self, endpoint_name, pw_func, *args, **kwargs):
        """
        Safely call a pypowerwall function for an endpoint with caching
        and graceful degradation.

        Returns response data on success, cached data if available and fresh
        enough, or None if no data available.
        """
        result = self.safe_pw_call(pw_func, *args, **kwargs)

        if result is not None:
            if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION]:
                cache_response(endpoint_name, result)
            return result

        # Failed to get fresh data - try cached response
        if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION]:
            cached = get_cached_response(endpoint_name, self.configuration[CONFIG_TYPE.PW_CACHE_TTL])
            if cached is not None:
                return cached

        return None

    def handle_control_post(self, self_path) -> bool:
        """Handle control POST requests."""
        if not self.pw_control:
            self.proxystats[PROXY_STATS_TYPE.ERRORS] += 1
            self.send_json_response(
                {"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"},
                status_code=HTTPStatus.BAD_REQUEST
            )
            return False

        try:
            action = urlparse(self_path).path.split('/')[2]
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            query_params = parse_qs(post_data.decode(UTF_8))
            value = query_params.get('value', [''])[0]
            token = query_params.get('token', [''])[0]
        except Exception as er:
            log.error("Control Command Error: %s", er)
            self.send_json_response(
                {"error": "Control Command Error: Invalid Request"},
                status_code=HTTPStatus.BAD_REQUEST
            )
            return False

        if token != self.configuration[CONFIG_TYPE.PW_CONTROL_SECRET]:
            self.send_json_response(
                {"unauthorized": "Control Command Token Invalid"},
                status_code=HTTPStatus.UNAUTHORIZED
            )
            return False

        if action == 'reserve':
            if not value:
                self.send_json_response({"reserve": self.safe_pw_call(self.pw_control.get_reserve)})
                return True
            elif value.isdigit():
                result = self.safe_pw_call(self.pw_control.set_reserve, int(value))
                log.info(f"Control Command: Set Reserve to {value}")
                self.send_json_response(result if result is not None else {"error": "Failed to set reserve"})
                return True
            else:
                self.send_json_response(
                    {"error": "Control Command Value Invalid"},
                    status_code=HTTPStatus.BAD_REQUEST
                )
        elif action == 'mode':
            if not value:
                self.send_json_response({"mode": self.safe_pw_call(self.pw_control.get_mode)})
                return True
            elif value in ['self_consumption', 'backup', 'autonomous']:
                result = self.safe_pw_call(self.pw_control.set_mode, value)
                log.info(f"Control Command: Set Mode to {value}")
                self.send_json_response(result if result is not None else {"error": "Failed to set mode"})
                return True
            else:
                self.send_json_response(
                    {"error": "Control Command Value Invalid"},
                    status_code=HTTPStatus.BAD_REQUEST
                )
        else:
            self.send_json_response(
                {"error": "Invalid Command Action"},
                status_code=HTTPStatus.BAD_REQUEST
            )
        return False


    def do_POST(self):
        """Handle POST requests."""
        if self.path.startswith('/control'):
            stat = PROXY_STATS_TYPE.POSTS if self.handle_control_post(self.path) else PROXY_STATS_TYPE.ERRORS
            self.proxystats[stat] += 1
        else:
            self.send_json_response(
                {"error": "Invalid Request"},
                status_code=HTTPStatus.BAD_REQUEST
            )


    def do_GET(self):
        """Handle GET requests."""
        path = self.path

        # Map paths to handler functions
        path_handlers = {
            '/aggregates': self.handle_combined_aggregates,
            '/alerts': self.handle_alerts,
            '/alerts/pw': self.handle_alerts_pw,
            '/api/meters/aggregates': self.handle_individual_gateway_aggregates,
            '/api/system_status/grid_status': self.handle_grid_status,
            '/api/system_status/soe': self.handle_soe_scaled,
            '/api/troubleshooting/problems': self.handle_problems,
            '/fans': self.handle_fans,
            '/fans/pw': self.handle_fans,
            '/freq': self.handle_freq,
            '/health': self.handle_health,
            '/health/reset': self.handle_health_reset,
            '/help': self.handle_help,
            '/json': self.handle_json,
            '/pod': self.handle_pod,
            '/soe': self.handle_soe,
            '/stats': self.handle_stats,
            '/stats/clear': self.handle_stats_clear,
            '/strings': self.handle_strings,
            '/temps': self.handle_temps,
            '/temps/pw': self.handle_temps_pw,
            '/version': self.handle_version,
            '/vitals': self.handle_vitals,
        }

        result: str = ""
        if path in DISABLED:
            result = self.send_json_response(
                {"status": "404 Response - API Disabled"}
            )
        elif path in path_handlers:
            result = path_handlers[path]()
        elif path.startswith('/pw/'):
            result = self.handle_pw_api()
        elif path in ALLOWLIST:
            result = self.handle_allowlist(path)
        elif path.startswith('/csv') or path.startswith('/csv/v2'):
            # CSV Output - Grid,Home,Solar,Battery,Level
            # CSV2 Output - Grid,Home,Solar,Battery,Level,GridStatus,Reserve
            # Add ?headers to include CSV headers, e.g. http://localhost:8675/csv?headers
            result = self.handle_csv()
        elif path.startswith('/tedapi'):
            result = self.handle_tedapi(path)
        elif path.startswith('/cloud'):
            result = self.handle_cloud(path)
        elif path.startswith('/fleetapi'):
            result = self.handle_fleetapi(path)
        elif path.startswith('/control/reserve'):
            # Current battery reserve level
            if not self.pw_control:
                result = self.send_json_response({"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"})
            else:
                result = self.send_json_response({"reserve": self.safe_pw_call(self.pw_control.get_reserve)})
        elif path.startswith('/control/mode'):
            # Current operating mode
            if not self.pw_control:
                result = self.send_json_response({"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"})
            else:
                result = self.send_json_response({"mode": self.safe_pw_call(self.pw_control.get_mode)})
        else:
            result = self.handle_static_content(path)

        if result is None or result == "":
            self.proxystats[PROXY_STATS_TYPE.TIMEOUT] += 1
        elif result == "ERROR!":
            self.proxystats[PROXY_STATS_TYPE.ERRORS] += 1
        else:
            self.proxystats[PROXY_STATS_TYPE.GETS] += 1
            if path in self.proxystats[PROXY_STATS_TYPE.URI]:
                self.proxystats[PROXY_STATS_TYPE.URI][path] += 1
            else:
                self.proxystats[PROXY_STATS_TYPE.URI][path] = 1


    def handle_individual_gateway_aggregates(self) -> str:
        aggregates = self.safe_pw_call(self.pw.poll, '/api/meters/aggregates')
        if not self.configuration[CONFIG_TYPE.PW_NEG_SOLAR] and aggregates and 'solar' in aggregates:
            solar = aggregates['solar']
            if solar and 'instant_power' in solar and solar['instant_power'] < 0:
                solar['instant_power'] = 0
                # Shift energy from solar to load
                if 'load' in aggregates and 'instant_power' in aggregates['load']:
                    aggregates['load']['instant_power'] -= solar['instant_power']
            else:
                load = aggregates.get("load", {})
                if load:
                    load["instant_power"] = abs(load.get("instant_power"))
                site = aggregates.get("site", {})
                if site:
                    site["instant_power"] = abs(site.get("instant_power"))
        appended = {f"{self.pw.pw_din_suffix}_{key}": value for key, value in aggregates.items()}
        return self.send_json_response(appended)


    def handle_combined_aggregates(self) -> str:
        def merge_category(dest: Dict[Any, Any], src: Dict[Any, Any]) -> None:
            """
            Merge two dictionaries representing the same meter category.
            Numeric values (or None, treated as 0) are added together,
            while non-numeric values (like timestamps) are set only if not already present.
            """
            SKIP_KEYS: Final[List[str]] = ["instant_average_voltage", "timeout", "disclaimer"]
            for key, value in src.items():
                if key in SKIP_KEYS:
                    dest.setdefault(key, value)
                    continue
                if isinstance(value, (int, float)):
                    # Treat None as 0 when summing.
                    dest[key] = (dest.get(key, 0) or 0) + (value if value is not None else 0)
                    continue
                # For non-numeric fields, only set a value if one hasn't been set yet.
                dest.setdefault(key, value)

        def aggregate_meter_results(meter_results: List[Dict[Any, Any]]) -> Dict[Any, Any]:
            """
            Combine a list of meter result dictionaries into a single aggregated dict.
            """
            COMBINE_CATEGORIES: Final[List[str]] = ["solar", "load", "site"]
            combined = {}
            for result in meter_results:
                for category, readings in result.items():
                    combined.setdefault(category, {})
                    if category in COMBINE_CATEGORIES:
                        merge_category(combined[category], readings)
                        continue
                    combined[category] = readings
            return combined

        def update_power_metrics(combined: dict) -> None:
            # Retrieve sections from the combined dictionary
            site = combined.get("site", {})
            solar = combined.get("solar", {})
            load = combined.get("load", {})

            # Ensure all required sections are available
            if not (site and solar and load):
                return

            # Get values with defaults to avoid None values
            site_power = site.get("instant_power", 0)
            site_current = site.get("instant_average_current", 0)
            solar_power = solar.get("instant_power", 0)
            solar_voltage = solar.get("instant_average_voltage", 0)

            # Calculate load power as the sum of solar and site power
            load_power = solar_power + site_power
            load["instant_power"] = load_power

            # Calculate solar total current if voltage is available
            solar_total_current = solar_power / solar_voltage if solar_voltage else 0
            solar["instant_total_current"] = solar_total_current

            # Calculate load total current by adding site current and solar total current
            load_current = solar_total_current + site_current
            load["instant_total_current"] = load_current

            # Update voltages, ensuring we avoid division by zero
            load["instant_average_voltage"] = abs(load_power) / abs(load_current) if load_current else 0
            if not site.get("instant_average_voltage", 0):
                site["instant_average_voltage"] = abs(site_power) / abs(site_current) if site_current else 0

        # Poll all meter objects and gather non-empty results.
        results = [copy.deepcopy(result) for pws in self.all_pws if (result := self.safe_pw_call(pws[0].poll, "/api/meters/aggregates"))]
        if not results:
            # No fresh data - try cached response
            if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION]:
                cached = get_cached_response('/aggregates', self.configuration[CONFIG_TYPE.PW_CACHE_TTL])
                if cached is not None:
                    return self.send_json_response(cached)
            return self.send_json_response(None)

        combined = aggregate_meter_results(results)
        update_power_metrics(combined)

        # Adjust negative solar values if configuration disallows negative solar.
        if not self.configuration[CONFIG_TYPE.PW_NEG_SOLAR]:
            solar = combined.get("solar", {})
            if solar.get("instant_power", 0) < 0:
                negative_value = solar["instant_power"]
                solar["instant_power"] = 0
                if "load" in combined:
                    load = combined["load"]
                    load["instant_power"] = load.get("instant_power", 0) + (-negative_value)
            else:
                load = combined.get("load", {})
                if load:
                    load["instant_power"] = abs(load.get("instant_power"))
                site = combined.get("site", {})
                if site:
                    site["instant_power"] = abs(site.get("instant_power"))

        # Cache the combined result for graceful degradation
        if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION]:
            cache_response('/aggregates', combined)

        return self.send_json_response(combined)


    def handle_soe(self) -> str:
        soe = self.safe_endpoint_call('/soe', self.pw.poll, '/api/system_status/soe', jsonformat=True)
        return self.send_json_response(json.loads(soe) if soe else None)


    def handle_soe_scaled(self) -> str:
        level = self.safe_pw_call(self.pw.level, scale=True)
        return self.send_json_response({"percentage": level} if level is not None else None)


    def handle_grid_status(self) -> str:
        grid_status = self.safe_pw_call(self.pw.poll, '/api/system_status/grid_status', jsonformat=True)
        return self.send_json_response(json.loads(grid_status) if grid_status else {})


    def handle_json(self) -> str:
        # JSON - Grid,Home,Solar,Battery,SoE,GridStatus,Reserve,TimeRemaining,FullEnergy,RemainingEnergy,Strings
        d = self.safe_pw_call(self.pw.system_status) or {}
        values = {
            'grid': self.safe_pw_call(self.pw.grid) or 0,
            'home': self.safe_pw_call(self.pw.home) or 0,
            'solar': self.safe_pw_call(self.pw.solar) or 0,
            'battery': self.safe_pw_call(self.pw.battery) or 0,
            'soe': self.safe_pw_call(self.pw.level) or 0,
            'grid_status': int(self.safe_pw_call(self.pw.grid_status) == 'UP'),
            'reserve': self.safe_pw_call(self.pw.get_reserve) or 0,
            'time_remaining_hours': self.safe_pw_call(self.pw.get_time_remaining) or 0,
            'full_pack_energy': get_value(d, 'nominal_full_pack_energy') or 0,
            'energy_remaining': get_value(d, 'nominal_energy_remaining') or 0,
            'strings': self.safe_pw_call(self.pw.strings, jsonformat=False) or {},
        }
        if not self.configuration[CONFIG_TYPE.PW_NEG_SOLAR] and values['solar'] < 0:
            # Shift negative solar to load
            values['home'] -= values['solar']
            values['solar'] = 0
        return self.send_json_response(values)


    def handle_csv(self) -> str:
        # Grid,Home,Solar,Battery,BatteryLevel[,GridStatus,Reserve] - CSV
        grid = self.safe_pw_call(self.pw.grid) or 0
        solar = self.safe_pw_call(self.pw.solar) or 0
        battery = self.safe_pw_call(self.pw.battery) or 0
        home = self.safe_pw_call(self.pw.home) or 0
        if not self.configuration[CONFIG_TYPE.PW_NEG_SOLAR] and solar < 0:
            solar = 0
            # Shift energy from solar to load
            home -= solar
        fields = [grid, home, solar, battery, self.safe_pw_call(self.pw.level) or 0]
        headers = ["Grid", "Home", "Solar", "Battery", "BatteryLevel"]
        if self.path.startswith('/csv/v2'):
            fields.append(1 if self.safe_pw_call(self.pw.grid_status) == 'UP' else 0)
            fields.append(self.safe_pw_call(self.pw.get_reserve) or 0)
            headers += ["GridStatus", "Reserve"]
        message = ""
        if "headers" in self.path:
            message += ",".join(headers) + "\n"
        message += ",".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in fields) + "\n"
        return self.send_json_response(message)


    def handle_vitals(self) -> str:
        vitals = self.safe_endpoint_call('/vitals', self.pw.vitals, jsonformat=True)
        return self.send_json_response(json.loads(vitals) if vitals else None)


    def handle_strings(self) -> str:
        strings = self.safe_endpoint_call('/strings', self.pw.strings, jsonformat=True)
        if not strings:
            return self.send_json_response(None)
        output = json.loads(strings)
        if len(self.all_pws) > 1:
            output = {f"{key}_{self.pw.pw_din_suffix}": value for key, value in output.items()}
        return self.send_json_response(output)


    def handle_stats(self) -> str:
        self.proxystats.update({
            PROXY_STATS_TYPE.TS: int(time.time()),
            PROXY_STATS_TYPE.UPTIME: str(datetime.timedelta(seconds=(float(self.proxystats[PROXY_STATS_TYPE.TS]) - float(self.proxystats[PROXY_STATS_TYPE.START])))),
            PROXY_STATS_TYPE.MEM: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            PROXY_STATS_TYPE.SITE_NAME: self.safe_pw_call(self.pw.site_name) or "",
            PROXY_STATS_TYPE.CLOUDMODE: self.pw.cloudmode,
            PROXY_STATS_TYPE.FLEETAPI: self.pw.fleetapi,
            PROXY_STATS_TYPE.AUTH_MODE: self.pw.authmode
        })
        if (self.pw.cloudmode or self.pw.fleetapi) and self.pw.client:
            self.proxystats[PROXY_STATS_TYPE.SITEID] = self.pw.client.siteid
            self.proxystats[PROXY_STATS_TYPE.COUNTER] = self.pw.client.counter
        if self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
            with _connection_health_lock:
                self.proxystats[PROXY_STATS_TYPE.CONNECTION_HEALTH] = {
                    'consecutive_failures': _connection_health['consecutive_failures'],
                    'total_failures': _connection_health['total_failures'],
                    'total_successes': _connection_health['total_successes'],
                    'is_degraded': _connection_health['is_degraded'],
                    'last_success_time': _connection_health['last_success_time'],
                    'cache_size': len(_last_good_responses) if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION] else 0,
                }
        return self.send_json_response(self.proxystats)


    def handle_stats_clear(self) -> str:
        # Clear Internal Stats
        log.debug("Clear internal stats")
        self.proxystats.update({
            PROXY_STATS_TYPE.GETS: 0,
            PROXY_STATS_TYPE.ERRORS: 0,
            PROXY_STATS_TYPE.URI: {},
            PROXY_STATS_TYPE.CLEAR: int(time.time()),
        })
        return self.send_json_response(self.proxystats)


    def handle_health(self) -> str:
        health_info = {
            'cache_ttl_seconds': self.configuration[CONFIG_TYPE.PW_CACHE_TTL],
            'graceful_degradation': self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION],
            'fail_fast_mode': self.configuration[CONFIG_TYPE.PW_FAIL_FAST],
            'health_check_enabled': self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK],
        }
        if self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
            with _connection_health_lock:
                health_info['connection_health'] = {
                    'consecutive_failures': _connection_health['consecutive_failures'],
                    'total_failures': _connection_health['total_failures'],
                    'total_successes': _connection_health['total_successes'],
                    'is_degraded': _connection_health['is_degraded'],
                    'last_success_time': _connection_health['last_success_time'],
                    'last_success_age_seconds': time.time() - _connection_health['last_success_time'],
                }
        if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION]:
            with _last_good_responses_lock:
                cached_endpoints = {}
                current_time = time.time()
                for endpoint, (data, timestamp) in _last_good_responses.items():
                    age = current_time - timestamp
                    cached_endpoints[endpoint] = {
                        'age_seconds': age,
                        'is_expired': age >= self.configuration[CONFIG_TYPE.PW_CACHE_TTL],
                    }
                health_info['cached_data'] = {
                    'cache_size': len(_last_good_responses),
                    'endpoints': cached_endpoints,
                }
        return self.send_json_response(health_info)


    def handle_health_reset(self) -> str:
        cache_size_before = 0
        if self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK]:
            with _connection_health_lock:
                _connection_health['consecutive_failures'] = 0
                _connection_health['total_failures'] = 0
                _connection_health['total_successes'] = 0
                _connection_health['is_degraded'] = False
                _connection_health['last_success_time'] = time.time()
        if self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION]:
            with _last_good_responses_lock:
                cache_size_before = len(_last_good_responses)
                _last_good_responses.clear()
        log.info("Health counters and cache reset via /health/reset endpoint")
        return self.send_json_response({
            'status': 'reset_complete',
            'health_counters_reset': self.configuration[CONFIG_TYPE.PW_HEALTH_CHECK],
            'cache_cleared': self.configuration[CONFIG_TYPE.PW_GRACEFUL_DEGRADATION],
            'cache_entries_removed': cache_size_before,
        })


    def handle_fans(self) -> str:
        if not self.pw.tedapi:
            return self.send_json_response({})
        fan_speeds = self.safe_pw_call(self.pw.tedapi.get_fan_speeds) or {}
        if self.path.startswith('/fans/pw'):
            # Fan speeds in simplified format (e.g. FAN1_actual, FAN1_target)
            output = {}
            for i, (_, value) in enumerate(sorted(fan_speeds.items())):
                key = f"FAN{i+1}"
                output[f"{key}_actual"] = value.get('PVAC_Fan_Speed_Actual_RPM')
                output[f"{key}_target"] = value.get('PVAC_Fan_Speed_Target_RPM')
            return self.send_json_response(output)
        return self.send_json_response(fan_speeds)


    def handle_pw_api(self) -> str:
        # Expose Powerwall API methods as JSON endpoints via /pw/XXX
        # Entries with a wrapper key return {key: value}, others return the result directly
        pw_endpoints = {
            '/pw/level':              ('level', lambda: self.safe_pw_call(self.pw.level)),
            '/pw/power':              (None, lambda: self.safe_pw_call(self.pw.power)),
            '/pw/site':               (None, lambda: self.safe_pw_call(self.pw.site, verbose=True)),
            '/pw/solar':              (None, lambda: self.safe_pw_call(self.pw.solar, verbose=True)),
            '/pw/battery':            (None, lambda: self.safe_pw_call(self.pw.battery, verbose=True)),
            '/pw/battery_blocks':     (None, lambda: self.safe_pw_call(self.pw.battery_blocks)),
            '/pw/load':               (None, lambda: self.safe_pw_call(self.pw.load, verbose=True)),
            '/pw/grid':               (None, lambda: self.safe_pw_call(self.pw.grid, verbose=True)),
            '/pw/home':               (None, lambda: self.safe_pw_call(self.pw.home, verbose=True)),
            '/pw/vitals':             (None, lambda: self.safe_pw_call(self.pw.vitals)),
            '/pw/aggregates':         (None, lambda: self.safe_pw_call(self.pw.poll, '/api/meters/aggregates')),
            '/pw/temps':              (None, lambda: self.safe_pw_call(self.pw.temps)),
            '/pw/strings':            (None, lambda: self.safe_pw_call(self.pw.strings, verbose=True)),
            '/pw/din':                ('din', lambda: self.safe_pw_call(self.pw.din)),
            '/pw/uptime':             ('uptime', lambda: self.safe_pw_call(self.pw.uptime)),
            '/pw/version':            ('version', lambda: self.safe_pw_call(self.pw.version)),
            '/pw/status':             (None, lambda: self.safe_pw_call(self.pw.status)),
            '/pw/system_status':      (None, lambda: self.safe_pw_call(self.pw.system_status)),
            '/pw/grid_status':        (None, lambda: json.loads(self.safe_pw_call(self.pw.grid_status, type="json") or '{}')),
            '/pw/site_name':          ('site_name', lambda: self.safe_pw_call(self.pw.site_name)),
            '/pw/alerts':             ('alerts', lambda: self.safe_pw_call(self.pw.alerts)),
            '/pw/is_connected':       ('is_connected', lambda: self.safe_pw_call(self.pw.is_connected)),
            '/pw/get_reserve':        ('reserve', lambda: self.safe_pw_call(self.pw.get_reserve)),
            '/pw/get_mode':           ('mode', lambda: self.safe_pw_call(self.pw.get_mode)),
            '/pw/get_time_remaining': ('time_remaining', lambda: self.safe_pw_call(self.pw.get_time_remaining)),
        }
        endpoint = pw_endpoints.get(self.path)
        if not endpoint:
            return self.send_json_response({"error": "Invalid Request"}, status_code=HTTPStatus.BAD_REQUEST)
        wrapper_key, fn = endpoint
        result = fn()
        if wrapper_key:
            result = {wrapper_key: result}
        return self.send_json_response(result)

    def handle_temps(self) -> str:
        temps = self.safe_pw_call(self.pw.temps, jsonformat=True) or '{}'
        return self.send_json_response(json.loads(temps))


    def handle_temps_pw(self) -> str:
        temps = self.safe_pw_call(self.pw.temps) or {}
        pw_temp = {f"PW{idx}_temp": temp for idx, temp in enumerate(temps.values(), 1)}
        return self.send_json_response(pw_temp)


    def handle_alerts(self) -> str:
        alerts = self.safe_pw_call(self.pw.alerts, jsonformat=True) or '[]'
        output = json.loads(alerts)
        if len(self.all_pws) > 1:
            output = [f"{self.pw.pw_din_suffix}_{alert}" for alert in output]
        return self.send_json_response(output)


    def handle_alerts_pw(self) -> str:
        alerts = self.safe_pw_call(self.pw.alerts) or []
        if len(self.all_pws) > 1:
            alerts = {f"{self.pw.pw_din_suffix}_{alert}": 1 for alert in alerts}
        return self.send_json_response(alerts)


    def handle_freq(self) -> str:
        fcv = {}
        system_status = self.safe_pw_call(self.pw.system_status) or {}
        blocks = system_status.get("battery_blocks", [])
        for idx, block in enumerate(blocks, 1):
            fcv.update({
                f"PW{idx}_name": None,
                f"PW{idx}_PINV_Fout": get_value(block, "f_out"),
                f"PW{idx}_PINV_VSplit1": None,
                f"PW{idx}_PINV_VSplit2": None,
                f"PW{idx}_PackagePartNumber": get_value(block, "PackagePartNumber"),
                f"PW{idx}_PackageSerialNumber": get_value(block, "PackageSerialNumber"),
                f"PW{idx}_p_out": get_value(block, "p_out"),
                f"PW{idx}_q_out": get_value(block, "q_out"),
                f"PW{idx}_v_out": get_value(block, "v_out"),
                f"PW{idx}_f_out": get_value(block, "f_out"),
                f"PW{idx}_i_out": get_value(block, "i_out"),
            })
        vitals = self.safe_pw_call(self.pw.vitals) or {}
        din_suffix = self.pw.pw_din_suffix if len(self.all_pws) > 1 else None
        for idx, (device, data) in enumerate(vitals.items()):
            if device.startswith('TEPINV'):
                fcv.update({
                    f"PW{idx}_name": device,
                    f"PW{idx}_PINV_Fout": get_value(data, 'PINV_Fout'),
                    f"PW{idx}_PINV_VSplit1": get_value(data, 'PINV_VSplit1'),
                    f"PW{idx}_PINV_VSplit2": get_value(data, 'PINV_VSplit2')
                })
            if device.startswith(('PVAC', 'TESYNC', 'TEMSA')):
                fcv.update({(f"{key}" if not din_suffix else f"{din_suffix}_{key}"): value for key, value in data.items() if key.startswith(('ISLAND', 'METER', 'PVAC_Fan_Speed', 'PVAC_Fout', 'PVAC_VL'))})
        fcv["grid_status"] = self.safe_pw_call(self.pw.grid_status, type="numeric")
        return self.send_json_response(fcv)


    def handle_pod(self) -> str:
        # Powerwall Battery Data
        pod = {}
        # Get Individual Powerwall Battery Data
        system_status = self.safe_pw_call(self.pw.system_status) or {}
        blocks = system_status.get("battery_blocks", [])
        for idx, block in enumerate(blocks, 1):
            pod.update({
                # Vital Placeholders
                f"PW{idx}_name": None,
                f"PW{idx}_POD_ActiveHeating": None,
                f"PW{idx}_POD_ChargeComplete": None,
                f"PW{idx}_POD_ChargeRequest": None,
                f"PW{idx}_POD_DischargeComplete": None,
                f"PW{idx}_POD_PermanentlyFaulted": None,
                f"PW{idx}_POD_PersistentlyFaulted": None,
                f"PW{idx}_POD_enable_line": None,
                f"PW{idx}_POD_available_charge_power": None,
                f"PW{idx}_POD_available_dischg_power": None,
                f"PW{idx}_POD_nom_energy_remaining": None,
                f"PW{idx}_POD_nom_energy_to_be_charged": None,
                f"PW{idx}_POD_nom_full_pack_energy": None,
                # Additional System Status Data
                f"PW{idx}_POD_nom_energy_remaining": get_value(block, "nominal_energy_remaining"), # map
                f"PW{idx}_POD_nom_full_pack_energy": get_value(block, "nominal_full_pack_energy"), # map
                f"PW{idx}_PackagePartNumber": get_value(block, "PackagePartNumber"),
                f"PW{idx}_PackageSerialNumber": get_value(block, "PackageSerialNumber"),
                f"PW{idx}_pinv_state": get_value(block, "pinv_state"),
                f"PW{idx}_pinv_grid_state": get_value(block, "pinv_grid_state"),
                f"PW{idx}_p_out": get_value(block, "p_out"),
                f"PW{idx}_q_out": get_value(block, "q_out"),
                f"PW{idx}_v_out": get_value(block, "v_out"),
                f"PW{idx}_f_out": get_value(block, "f_out"),
                f"PW{idx}_i_out": get_value(block, "i_out"),
                f"PW{idx}_energy_charged": get_value(block, "energy_charged"),
                f"PW{idx}_energy_discharged": get_value(block, "energy_discharged"),
                f"PW{idx}_off_grid": int(get_value(block, "off_grid") or 0),
                f"PW{idx}_vf_mode": int(get_value(block, "vf_mode") or 0),
                f"PW{idx}_wobble_detected": int(get_value(block, "wobble_detected") or 0),
                f"PW{idx}_charge_power_clamped": int(get_value(block, "charge_power_clamped") or 0),
                f"PW{idx}_backup_ready": int(get_value(block, "backup_ready") or 0),
                f"PW{idx}_OpSeqState": get_value(block, "OpSeqState"),
                f"PW{idx}_version": get_value(block, "version")
            })

        vitals = self.safe_pw_call(self.pw.vitals) or {}
        for idx, (device, data) in enumerate(vitals.items(), 1):
            if not device.startswith('TEPOD'):
                continue
            pod.update({
                f"PW{idx}_name": device,
                f"PW{idx}_POD_ActiveHeating": int(get_value(data, 'POD_ActiveHeating') or 0),
                f"PW{idx}_POD_ChargeComplete": int(get_value(data, 'POD_ChargeComplete') or 0),
                f"PW{idx}_POD_ChargeRequest": int(get_value(data, 'POD_ChargeRequest') or 0),
                f"PW{idx}_POD_DischargeComplete": int(get_value(data, 'POD_DischargeComplete') or 0),
                f"PW{idx}_POD_PermanentlyFaulted": int(get_value(data, 'POD_PermanentlyFaulted') or 0),
                f"PW{idx}_POD_PersistentlyFaulted": int(get_value(data, 'POD_PersistentlyFaulted') or 0),
                f"PW{idx}_POD_enable_line": int(get_value(data, 'POD_enable_line') or 0),
                f"PW{idx}_POD_available_charge_power": get_value(data, 'POD_available_charge_power'),
                f"PW{idx}_POD_available_dischg_power": get_value(data, 'POD_available_dischg_power'),
                f"PW{idx}_POD_nom_energy_remaining": get_value(data, 'POD_nom_energy_remaining'),
                f"PW{idx}_POD_nom_energy_to_be_charged": get_value(data, 'POD_nom_energy_to_be_charged'),
                f"PW{idx}_POD_nom_full_pack_energy": get_value(data, 'POD_nom_full_pack_energy')
            })

        pod.update({
            "nominal_full_pack_energy": get_value(system_status, 'nominal_full_pack_energy'),
            "nominal_energy_remaining": get_value(system_status, 'nominal_energy_remaining'),
            "time_remaining_hours": self.safe_pw_call(self.pw.get_time_remaining),
            "backup_reserve_percent": self.safe_pw_call(self.pw.get_reserve)
        })
        return self.send_json_response(pod)


    def handle_version(self) -> str:
        version = self.safe_pw_call(self.pw.version)
        r = {"version": "SolarOnly", "vint": 0} if version is None else {"version": version, "vint": parse_version(version)}
        return self.send_json_response(r)


    def handle_help(self) -> str:
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        # Display friendly help screen link and stats

        self.proxystats.update({
            PROXY_STATS_TYPE.TS: int(time.time()),
            PROXY_STATS_TYPE.UPTIME: str(datetime.timedelta(seconds=int(time.time()) - self.proxystats[PROXY_STATS_TYPE.START])),
            PROXY_STATS_TYPE.MEM: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            PROXY_STATS_TYPE.SITE_NAME: self.safe_pw_call(self.pw.site_name),
            PROXY_STATS_TYPE.CLOUDMODE: self.pw.cloudmode,
            PROXY_STATS_TYPE.FLEETAPI: self.pw.fleetapi,
        })

        if (self.pw.cloudmode or self.pw.fleetapi) and self.pw.client is not None:
            self.proxystats[PROXY_STATS_TYPE.SITEID] = self.pw.client.siteid
            self.proxystats[PROXY_STATS_TYPE.COUNTER] = self.pw.client.counter
        self.proxystats[PROXY_STATS_TYPE.AUTH_MODE] = self.pw.authmode
        message = f"""
        <html>
        <head>
            <meta http-equiv="refresh" content="5" />
            <style>
                p, td, th {{ font-family: Helvetica, Arial, sans-serif; font-size: 10px;}}
                h1 {{ font-family: Helvetica, Arial, sans-serif; font-size: 20px;}}
            </style>
        </head>
        <body>
            <h1>pyPowerwall [{pypowerwall.version}] Proxy [{BUILD}]</h1>
            <p><a href="https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md">Click here for API help.</a></p>
            <table>
                <tr><th align="left">Stat</th><th align="left">Value</th></tr>
        """
        for key, value in self.proxystats.items():
            if key not in ['uri', 'config']:
                message += f'<tr><td align="left">{key}</td><td align="left">{value}</td></tr>\n'
        for uri, count in self.proxystats[PROXY_STATS_TYPE.URI].items():
            message += f'<tr><td align="left">URI: {uri}</td><td align="left">{count}</td></tr>\n'
        message += """
        <tr>
            <td align="left">Config:</td>
            <td align="left">
                <details id="config-details">
                    <summary>Click to view</summary>
                    <table>
        """
        for key, value in self.proxystats[PROXY_STATS_TYPE.CONFIG].items():
            display_value = '*' * len(value) if any(substr in key for substr in ['PASSWORD', 'SECRET']) else value
            message += f'<tr><td align="left">{key}</td><td align="left">{display_value}</td></tr>\n'
        message += """
                    </table>
                </details>
            </td>
        </tr>
        <script>
            document.addEventListener("DOMContentLoaded", function() {
                var details = document.getElementById("config-details");
                if (localStorage.getItem("config-details-open") === "true") {
                    details.setAttribute("open", "open");
                }
                details.addEventListener("toggle", function() {
                    localStorage.setItem("config-details-open", details.open);
                });
            });
        </script>
        """
        message += "</table>\n"
        message += f'\n<p>Page refresh: {str(datetime.datetime.fromtimestamp(time.time()))}</p>\n</body>\n</html>'
        return self.wfile.write(message.encode(UTF_8))


    def handle_problems(self) -> str:
        return self.send_json_response({"problems": []})

    def handle_allowlist(self, path) -> str:
        response = self.safe_pw_call(self.pw.poll, path, jsonformat=True) or '{}'
        return self.send_json_response(json.loads(response))

    def handle_tedapi(self, path) -> str:
        if not self.pw.tedapi:
            return self.send_json_response({"error": "TEDAPI not enabled"}, status_code=HTTPStatus.BAD_REQUEST)

        commands = {
            '/tedapi/config': self.pw.tedapi.get_config,
            '/tedapi/status': self.pw.tedapi.get_status,
            '/tedapi/components': self.pw.tedapi.get_components,
            '/tedapi/battery': self.pw.tedapi.get_battery_blocks,
            '/tedapi/controller': self.pw.tedapi.get_device_controller,
        }
        command = commands.get(path)
        if command:
            return self.send_json_response(self.safe_pw_call(command) or {})

        return self.send_json_response(
            {"error": "Use /tedapi/config, /tedapi/status, /tedapi/components, /tedapi/battery, /tedapi/controller"},
            status_code=HTTPStatus.BAD_REQUEST
        )


    def handle_cloud(self, path) -> str:
        if not self.pw.cloudmode or self.pw.fleetapi:
            return self.send_json_response({"error": "Cloud API not enabled"}, status_code=HTTPStatus.BAD_REQUEST)

        commands = {
            '/cloud/battery': self.pw.client.get_battery,
            '/cloud/power': self.pw.client.get_site_power,
            '/cloud/config': self.pw.client.get_site_config,
        }
        command = commands.get(path)
        if command:
            return self.send_json_response(self.safe_pw_call(command) or {})
        return self.send_json_response({"error": "Use /cloud/battery, /cloud/power, /cloud/config"}, status_code=HTTPStatus.BAD_REQUEST)


    def handle_fleetapi(self, path) -> str:
        if not self.pw.fleetapi:
            return self.send_json_response({"error": "FleetAPI not enabled"}, status_code=HTTPStatus.BAD_REQUEST)

        commands = {
            '/fleetapi/info': self.pw.client.get_site_info,
            '/fleetapi/status': self.pw.client.get_live_status,
        }
        command = commands.get(path)
        if command:
            return self.send_json_response(self.safe_pw_call(command) or {})

        return self.send_json_response({"error": "Use /fleetapi/info, /fleetapi/status"}, status_code=HTTPStatus.BAD_REQUEST)


    def handle_static_content(self, path) -> str:
        self.proxystats[PROXY_STATS_TYPE.GETS] += 1
        self.send_response(HTTPStatus.OK)
        if self.pw.authmode == "token":
            self.send_header("Set-Cookie", f"AuthCookie=1234567890;{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
            self.send_header("Set-Cookie", f"UserRecord=1234567890;{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
        else:
            auth = self.pw.client.auth
            self.send_header("Set-Cookie", f"AuthCookie={auth['AuthCookie']};{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
            self.send_header("Set-Cookie", f"UserRecord={auth['UserRecord']};{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")

        content, content_type = get_static(WEB_ROOT, path)
        if path == "/" or path == "":
            path = "/index.html"
            status = self.safe_pw_call(self.pw.status) or {}
            content = content.decode(UTF_8)
            # fix the following variables that if they are None, return ""
            content = content.replace("{VERSION}", status.get("version", "") or "")
            content = content.replace("{HASH}", status.get("git_hash", "") or "")
            content = content.replace("{EMAIL}", self.configuration.get(CONFIG_TYPE.PW_EMAIL, "") or "")
            content = content.replace("{STYLE}", self.configuration.get(CONFIG_TYPE.PW_STYLE, "") or "")
            # convert fcontent back to bytes
            content = bytes(content, UTF_8)
        elif path == "/app.js":
            content = content.decode(UTF_8)
            content = content.replace("{PW_HOST}", str(get_local_ip()) or "")
            content = content.replace("{PW_PORT}", str(self.configuration.get(CONFIG_TYPE.PW_PORT, "")) or "")
            content = bytes(content, UTF_8)

        if content:
            log.info("Served from local web root: {} type {}".format(path, content_type))
        # If not found, serve from Powerwall web server
        elif self.pw.cloudmode or self.pw.fleetapi:
            log.info(f"Cloud Mode - File not found: {path}")
            content = bytes("Not Found", UTF_8)
            content_type = "text/plain"
        elif self.pw.client.session:
            # Proxy request to Powerwall web server.
            pw_url = f"https://{self.pw.host}/{path.lstrip('/')}"
            log.info(f"Proxy request to: {pw_url}")
            try:
                session = self.pw.client.session
                response = session.get(
                    url=pw_url,
                    headers=self.pw.auth if self.pw.authmode == "token" else None,
                    cookies=None if self.pw.authmode == "token" else self.pw.auth,
                    verify=False,
                    stream=True,
                    timeout=self.pw.timeout,
                )
                content = response.content
                log.info(f"Proxy request content: {content}")
                content_type = response.headers.get('content-type', 'text/html')
            except Exception as exc:
                log.info("Error proxying request: %s", exc)
                content = b"Error during proxy"
                content_type = "text/plain"

        if self.configuration[CONFIG_TYPE.PW_BROWSER_CACHE] > 0 and content_type in ['text/css', 'application/javascript', 'image/png']:
            self.send_header("Cache-Control", f"max-age={self.configuration[CONFIG_TYPE.PW_BROWSER_CACHE]}")
        else:
            self.send_header("Cache-Control", "no-cache, no-store")

        if path.split('?')[0] == "/":
            if os.path.exists(os.path.join(WEB_ROOT, self.configuration[CONFIG_TYPE.PW_STYLE])):
                content = bytes(inject_js(content, self.configuration[CONFIG_TYPE.PW_STYLE]), UTF_8)

        self.send_header('Content-type', content_type)
        self.end_headers()
        try:
            self.wfile.write(content)
        except Exception as exc:
            if "Broken pipe" in str(exc):
                log.info(f"Client disconnected before payload sent [doGET]: {exc}")
                return content
            log.info(f"Error occured while sending PROXY response to client [doGET], Error: {exc}, Content: {content}, Content_Type: {content_type} Path: {path}")
        return content


def check_for_environmental_pw_configs() -> List[str]:
    """
    Checks for environment variables with specific suffix patterns and returns the list of matching suffixes.

    This function iterates over predefined suffixes (starting with an empty string and "1") to check if any
    configuration-related environment variables are defined. If a match is found, the suffix is added to the
    result list. For numeric suffixes, the function dynamically generates and checks the next numeric suffix.

    Returns:
        List[str]: A list of suffixes for which environment variables were found.

    Notes:
        - Environment variable names are constructed by appending the suffix to the `value` attribute of each
          item in `CONFIG_TYPE`.
        - The function dynamically appends numeric suffixes based on the highest found numeric suffix.
    """
    suffixes_to_check = {"", "1"}
    actual_configs = []

    environment = [key.lower() for key in os.environ]
    while suffixes_to_check:
        current_suffix = suffixes_to_check.pop()
        test_suffix = f"_{current_suffix}" if current_suffix.isnumeric() else current_suffix
        if any(f"{config.value}{test_suffix}" in environment for config in CONFIG_TYPE):
            actual_configs.append(test_suffix)
        elif current_suffix.isnumeric() and int(current_suffix) > 1:
            break
        if current_suffix.isnumeric():
            next_suffix = str(int(current_suffix) + 1)
            if next_suffix not in suffixes_to_check:
                suffixes_to_check.add(next_suffix)

    return actual_configs


def read_env_configs() -> List[PROXY_CONFIG]:
    suffixes = check_for_environmental_pw_configs()
    configs: List[PROXY_CONFIG] = []
    for s in suffixes:
        def get_env_value(config_type: CONFIG_TYPE, default: str | None) -> str | None:
            """Helper function to construct environment variable names and retrieve their values."""
            env_var = f"{config_type.value}{s}".upper()
            return os.getenv(env_var, default)

        config: PROXY_CONFIG = {
            CONFIG_TYPE.PW_AUTH_MODE: get_env_value(CONFIG_TYPE.PW_AUTH_MODE, "cookie"),
            CONFIG_TYPE.PW_AUTH_PATH: get_env_value(CONFIG_TYPE.PW_AUTH_PATH, ""),
            CONFIG_TYPE.PW_BIND_ADDRESS: get_env_value(CONFIG_TYPE.PW_BIND_ADDRESS, ""),
            CONFIG_TYPE.PW_BROWSER_CACHE: int(get_env_value(CONFIG_TYPE.PW_BROWSER_CACHE, "0")),
            CONFIG_TYPE.PW_CACHE_EXPIRE: int(get_env_value(CONFIG_TYPE.PW_CACHE_EXPIRE, "10")),
            CONFIG_TYPE.PW_CACHE_FILE: get_env_value(CONFIG_TYPE.PW_CACHE_FILE, ""),
            CONFIG_TYPE.PW_CACHE_TTL: int(get_env_value(CONFIG_TYPE.PW_CACHE_TTL, "30")),
            CONFIG_TYPE.PW_CONTROL_SECRET: get_env_value(CONFIG_TYPE.PW_CONTROL_SECRET, ""),
            CONFIG_TYPE.PW_EMAIL: get_env_value(CONFIG_TYPE.PW_EMAIL, "email@example.com"),
            CONFIG_TYPE.PW_FAIL_FAST: bool((get_env_value(CONFIG_TYPE.PW_FAIL_FAST, "no") or "no").lower() == "yes"),
            CONFIG_TYPE.PW_GRACEFUL_DEGRADATION: bool((get_env_value(CONFIG_TYPE.PW_GRACEFUL_DEGRADATION, "yes") or "yes").lower() == "yes"),
            CONFIG_TYPE.PW_GW_PWD: get_env_value(CONFIG_TYPE.PW_GW_PWD, None),
            CONFIG_TYPE.PW_HEALTH_CHECK: bool((get_env_value(CONFIG_TYPE.PW_HEALTH_CHECK, "yes") or "yes").lower() == "yes"),
            CONFIG_TYPE.PW_HOST: get_env_value(CONFIG_TYPE.PW_HOST, ""),
            CONFIG_TYPE.PW_HTTPS: (get_env_value(CONFIG_TYPE.PW_HTTPS, "no") or "no").lower(),
            CONFIG_TYPE.PW_NEG_SOLAR: bool((get_env_value(CONFIG_TYPE.PW_NEG_SOLAR, "yes") or "yes").lower() == "yes"),
            CONFIG_TYPE.PW_NETWORK_ERROR_RATE_LIMIT: int(get_env_value(CONFIG_TYPE.PW_NETWORK_ERROR_RATE_LIMIT, "5")),
            CONFIG_TYPE.PW_PASSWORD: get_env_value(CONFIG_TYPE.PW_PASSWORD, ""),
            CONFIG_TYPE.PW_POOL_MAXSIZE: int(get_env_value(CONFIG_TYPE.PW_POOL_MAXSIZE, "15")),
            CONFIG_TYPE.PW_PORT: int(get_env_value(CONFIG_TYPE.PW_PORT, "8675")),
            CONFIG_TYPE.PW_SITEID: get_env_value(CONFIG_TYPE.PW_SITEID, None),
            CONFIG_TYPE.PW_STYLE: str(get_env_value(CONFIG_TYPE.PW_STYLE, "clear")) + ".js",
            CONFIG_TYPE.PW_SUPPRESS_NETWORK_ERRORS: bool((get_env_value(CONFIG_TYPE.PW_SUPPRESS_NETWORK_ERRORS, "no") or "no").lower() == "yes"),
            CONFIG_TYPE.PW_TIMEOUT: int(get_env_value(CONFIG_TYPE.PW_TIMEOUT, "5")),
            CONFIG_TYPE.PW_TIMEZONE: get_env_value(CONFIG_TYPE.PW_TIMEZONE, "America/Los_Angeles")
        }
        configs.append(config)
    return configs


def build_configuration() -> List[PROXY_CONFIG]:
    COOKIE_SUFFIX: Final[str] = "path=/;SameSite=None;Secure;"
    configs = read_env_configs()
    if len(configs) == 0:
        log.error("No Tesla Energy Gateway configurations found. This should never happen. Proxy cannot start.")
        exit(0)

    for config in configs:
        # HTTP/S configuration
        if config[CONFIG_TYPE.PW_HTTPS] == "yes":
            config[CONFIG_TYPE.PW_COOKIE_SUFFIX] = COOKIE_SUFFIX
            config[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTPS"
        elif config[CONFIG_TYPE.PW_HTTPS] == "http":
            config[CONFIG_TYPE.PW_COOKIE_SUFFIX] = COOKIE_SUFFIX
            config[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTP"
        else:
            config[CONFIG_TYPE.PW_COOKIE_SUFFIX] = "path=/;"
            config[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTP"

        if config[CONFIG_TYPE.PW_CACHE_FILE] == "":
            config[CONFIG_TYPE.PW_CACHE_FILE] = os.path.join(config[CONFIG_TYPE.PW_AUTH_PATH], ".powerwall") if config[CONFIG_TYPE.PW_AUTH_PATH] else ".powerwall"

        # Check for cache expire time limit below 5s
        if int(config[CONFIG_TYPE.PW_CACHE_EXPIRE]) < 5:
            log.warning(f"Cache expiration set below 5s for host:port={config[CONFIG_TYPE.PW_HOST]}:{config[CONFIG_TYPE.PW_PORT]} (PW_CACHE_EXPIRE={config[CONFIG_TYPE.PW_CACHE_EXPIRE]})")

    return configs


def run_server(host, port, enable_https, configuration: PROXY_CONFIG, pw: pypowerwall.Powerwall, pw_control: pypowerwall.Powerwall, pws: List[Tuple[pypowerwall.Powerwall, pypowerwall.Powerwall, PROXY_CONFIG]]):
    proxystats: PROXY_STATS = {
        PROXY_STATS_TYPE.CF: configuration[CONFIG_TYPE.PW_CACHE_FILE],
        PROXY_STATS_TYPE.CLEAR: int(time.time()),
        PROXY_STATS_TYPE.CLOUDMODE: False,
        PROXY_STATS_TYPE.CONFIG: configuration.copy(),
        PROXY_STATS_TYPE.COUNTER: 0,
        PROXY_STATS_TYPE.ERRORS: 0,
        PROXY_STATS_TYPE.FLEETAPI: False,
        PROXY_STATS_TYPE.GETS: 0,
        PROXY_STATS_TYPE.MEM: 0,
        PROXY_STATS_TYPE.MODE: "Unknown",
        PROXY_STATS_TYPE.POSTS: 0,
        PROXY_STATS_TYPE.PW3: False,
        PROXY_STATS_TYPE.PYPOWERWALL: f"{pypowerwall.version} Proxy {BUILD}",
        PROXY_STATS_TYPE.SITE_NAME: "",
        PROXY_STATS_TYPE.SITEID: None,
        PROXY_STATS_TYPE.START: int(time.time()),
        PROXY_STATS_TYPE.TEDAPI_MODE: "off",
        PROXY_STATS_TYPE.TEDAPI: False,
        PROXY_STATS_TYPE.TIMEOUT: 0,
        PROXY_STATS_TYPE.TS: int(time.time()),
        PROXY_STATS_TYPE.UPTIME: "",
        PROXY_STATS_TYPE.URI: {}
    }

    def handler_factory(*args, **kwargs):
        return Handler(*args, configuration=configuration, pw=pw, pw_control=pw_control, proxy_stats=proxystats, all_pws=pws, **kwargs)

    with ThreadingHTTPServer((host, port), handler_factory) as server:
        if enable_https:
            log.debug(f"Activating HTTPS on {host}:{port}")
            server.socket = ssl.wrap_socket(
                server.socket,
                certfile=os.path.join(os.path.dirname(__file__), 'localhost.pem'),
                server_side=True,
                ssl_version=ssl.PROTOCOL_TLSv1_2,
                ca_certs=None,
                do_handshake_on_connect=True
            )
        try:
            log.info(f"Starting server on {host}:{port}")
            site_name = pw.site_name() or "Unknown"
            if pw.cloudmode or pw.fleetapi:
                if pw.fleetapi:
                    proxystats[PROXY_STATS_TYPE.MODE] = "FleetAPI"
                    log.info("pyPowerwall Proxy Server - FleetAPI Mode")
                else:
                    proxystats[PROXY_STATS_TYPE.MODE] = "Cloud"
                    log.info("pyPowerwall Proxy Server - Cloud Mode")
                log.info(f"Connected to Site ID {pw.client.siteid} ({site_name.strip()})")
                if configuration[CONFIG_TYPE.PW_SITEID] is not None and configuration[CONFIG_TYPE.PW_SITEID] != str(pw.client.siteid):
                    log.info(f"Switch to Site ID {configuration[CONFIG_TYPE.PW_SITEID]}")
                    if not pw.client.change_site(configuration[CONFIG_TYPE.PW_SITEID]):
                        log.error("Fatal Error: Unable to connect. Please fix config and restart.")
                        while True:
                            try:
                                time.sleep(5)  # Infinite loop to keep container running
                            except (KeyboardInterrupt, SystemExit):
                                sys.exit(0)
            else:
                proxystats[PROXY_STATS_TYPE.MODE] = "Local"
                log.info("pyPowerwall Proxy Server - Local Mode")
                log.info(f"Connected to Energy Gateway {configuration[CONFIG_TYPE.PW_HOST]} ({site_name.strip()})")
                if pw.tedapi:
                    proxystats[PROXY_STATS_TYPE.TEDAPI] = True
                    proxystats[PROXY_STATS_TYPE.TEDAPI_MODE] = pw.tedapi_mode
                    proxystats[PROXY_STATS_TYPE.PW3] = pw.tedapi.pw3
                    log.info(f"TEDAPI Mode Enabled for Device Vitals ({pw.tedapi_mode})")

            server.serve_forever()
        except (Exception, KeyboardInterrupt, SystemExit) as e:
            log.info(f"Server on {host}:{port} stopped due to exception {e}")
            sys.exit(0)


def main() -> None:
    servers: List[threading.Thread] = []
    pws: List[Tuple[pypowerwall.Powerwall, pypowerwall.Powerwall, PROXY_CONFIG]] = []
    configs = build_configuration()

    # Build powerwalls objects
    for config in configs:
        try:
            pw_monitor = pypowerwall.Powerwall(
                host=config[CONFIG_TYPE.PW_HOST],
                password=config[CONFIG_TYPE.PW_PASSWORD],
                email=config[CONFIG_TYPE.PW_EMAIL],
                timezone=config[CONFIG_TYPE.PW_TIMEZONE],
                pwcacheexpire=config[CONFIG_TYPE.PW_CACHE_EXPIRE],
                timeout=config[CONFIG_TYPE.PW_TIMEOUT],
                poolmaxsize=config[CONFIG_TYPE.PW_POOL_MAXSIZE],
                siteid=config[CONFIG_TYPE.PW_SITEID],
                authpath=config[CONFIG_TYPE.PW_AUTH_PATH],
                authmode=config[CONFIG_TYPE.PW_AUTH_MODE],
                cachefile=config[CONFIG_TYPE.PW_CACHE_FILE],
                auto_select=True,
                retry_modes=True,
                gw_pwd=config[CONFIG_TYPE.PW_GW_PWD],
                tedapi_auth_mode="bearer"
            )
            pw_control = configure_pw_control(pw_monitor, config)
            pws.append((pw_monitor, pw_control, config))
        except Exception as e:
            log.error(e)
            log.error("Fatal Error: Unable to connect. Please fix config and restart.")
            while True:
                try:
                    time.sleep(5)  # Infinite loop to keep container running
                except (KeyboardInterrupt, SystemExit):
                    sys.exit(0)

    # Create the servers
    for pw in pws:
        powerwall_monitor = pw[0]
        powerwall_control = pw[1]
        config = pw[2]
        server = threading.Thread(
            target=run_server,
            args=(
                config[CONFIG_TYPE.PW_BIND_ADDRESS],   # Host
                config[CONFIG_TYPE.PW_PORT],           # Port
                config[CONFIG_TYPE.PW_HTTPS] == "yes", # HTTPS
                config,
                powerwall_monitor,
                powerwall_control,
                pws
            )
        )
        servers.append(server)

    # Start all server threads
    for config, server in zip(configs, servers):
        log.info(
            f"pyPowerwall [{pypowerwall.version}] Proxy Server [{BUILD}] - {config[CONFIG_TYPE.PW_HTTP_TYPE]} Port {config[CONFIG_TYPE.PW_PORT]}{' - DEBUG' if SERVER_DEBUG else ''}"
        )
        log.info("pyPowerwall Proxy Started\n")
        server.start()

    # Wait for all server threads to finish
    for server in servers:
        server.join()

    log.info("pyPowerwall Proxy Stopped")
    sys.exit(0)


if __name__ == '__main__':
    main()

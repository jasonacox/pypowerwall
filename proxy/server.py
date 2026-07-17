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

 Error Handling
    Global exception handling has been implemented for all pypowerwall
    function calls to provide clean error logging instead of deep stack
    traces. Connection errors, API errors, and unexpected exceptions are
    caught and logged with descriptive messages while maintaining API
    functionality through graceful error responses.

 Weak WiFi / Network Error Handling
    For environments with weak WiFi or unstable network connections, use:
    - PW_SUPPRESS_NETWORK_ERRORS=yes to completely suppress individual
      network error logs (summary reports every 5 minutes)
    - PW_NETWORK_ERROR_RATE_LIMIT=N to limit network errors to N per
      minute per function (default: 5)
    - PW_FAIL_FAST=yes to return immediately when connection is degraded
      instead of attempting new requests (reduces timeout delays)
    - PW_GRACEFUL_DEGRADATION=yes to return cached data when fresh data
      is unavailable (default: yes, improves telegraf reliability)
    - PW_HEALTH_CHECK=yes to enable connection health monitoring and
      automatic degraded mode detection (default: yes)
    - PW_CACHE_TTL=N to set maximum age in seconds for cached data before
      returning null instead of stale data (default: 30)
    - Consider reducing PW_TIMEOUT to fail faster (e.g., PW_TIMEOUT=3)

 TEDAPI SolarOnly Fallback Recovery (PW3/TEDAPI modes)
    When TEDAPI drops mid-session (e.g. firmware 403 or route loss), the proxy
    falls back to SolarOnly mode — solar data continues but battery/grid detail
    is unavailable. The proxy now tracks this as a distinct `is_fallback_mode`
    state (separate from `is_degraded`) and a background thread retries the
    TEDAPI connection periodically with exponential backoff until data returns.
    - PW_TEDAPI_RECOVERY=yes/no — enable/disable auto-recovery (default: yes)
    - PW_TEDAPI_PROBE_INTERVAL=N — seconds between health probes (default: 30)
    The fallback state is visible in /health and /stats under "fallback_mode".

 Monitoring & Health Endpoints
    - /health - returns connection health status and feature configuration
    - /health/reset - resets health counters and clears cache
    - /stats - includes connection health metrics when enabled

 Data Freshness & Cache Behavior
    The proxy prioritizes data freshness over availability. When fresh data
    cannot be retrieved and cached data exceeds PW_CACHE_TTL seconds old,
    endpoints return null instead of stale/zero values. This ensures
    monitoring systems like telegraf can distinguish between actual zero
    values and missing/stale data, preventing false alerts and misleading
    metrics.

 Telegraf Compatibility
    Key endpoints return null when no fresh or reasonably recent cached
    data is available, allowing telegraf to handle missing data appropriately:
    - /aggregates returns null when no power data is available
    - /soe returns null when battery level data is unavailable
    - /vitals and /strings return null when device data is unavailable
    - CSV endpoints continue to return zero values for backwards compatibility

"""
import datetime
import hmac
import html
import json
import logging
import os
import resource
import signal
import ssl
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
import urllib3

# Robust import of transform helpers to support multiple invocation patterns:
# 1. python -m proxy.server (package-relative import works)
# 2. python proxy/server.py from project root (absolute package import works)
# 3. Executing from within the proxy directory (plain module import)
try:  # Prefer relative when executed as a package module
    from .transform import get_static, inject_js  # type: ignore
except ImportError:  # noqa: BLE001 - fall back to other strategies
    try:
        from proxy.transform import get_static, inject_js  # type: ignore
    except ImportError:  # noqa: BLE001
        from transform import get_static, inject_js  # type: ignore  # Last resort
import pypowerwall
from pypowerwall import parse_version
from pypowerwall.exceptions import (
    PyPowerwallInvalidConfigurationParameter,
    InvalidBatteryReserveLevelException,
)
from pypowerwall.tedapi.exceptions import (
    PyPowerwallTEDAPINoTeslaAuthFile,
    PyPowerwallTEDAPITeslaNotConnected,
    PyPowerwallTEDAPINotImplemented,
    PyPowerwallTEDAPIInvalidPayload,
)
from pypowerwall.fleetapi.exceptions import (
    PyPowerwallFleetAPINoTeslaAuthFile,
    PyPowerwallFleetAPITeslaNotConnected,
    PyPowerwallFleetAPINotImplemented,
    PyPowerwallFleetAPIInvalidPayload,
)

BUILD = "t97"
ALLOWLIST = [
    "/api/status",
    "/api/site_info/site_name",
    "/api/meters/site",
    "/api/meters/solar",
    "/api/sitemaster",
    "/api/powerwalls",
    "/api/customer/registration",
    "/api/system_status",
    "/api/system_status/grid_status",
    "/api/system/update/status",
    "/api/site_info",
    "/api/system_status/grid_faults",
    "/api/operation",
    "/api/site_info/grid_codes",
    "/api/solars",
    "/api/solars/brands",
    "/api/customer",
    "/api/meters",
    "/api/installer",
    "/api/networks",
    "/api/system/networks",
    "/api/meters/readings",
    "/api/synchrometer/ct_voltage_references",
    "/api/troubleshooting/problems",
    "/api/auth/toggle/supported",
    "/api/solar_powerwall",
]
DISABLED = [
    "/api/customer/registration",
]
# Maximum POST body size (bytes) accepted for /control commands
MAX_POST_BODY = 4096
web_root = os.path.join(os.path.dirname(__file__), "web")

# Configuration for Proxy - Check for environmental variables
#    and always use those if available (required for Docker)
bind_address = os.getenv("PW_BIND_ADDRESS", "")
password = os.getenv("PW_PASSWORD", "")
email = os.getenv("PW_EMAIL", "email@example.com")
host = os.getenv("PW_HOST", "")
timezone = os.getenv("PW_TIMEZONE", "America/Los_Angeles")
debugmode = os.getenv("PW_DEBUG", "no").lower() == "yes"
cache_expire = int(os.getenv("PW_CACHE_EXPIRE", "5"))
browser_cache = int(os.getenv("PW_BROWSER_CACHE", "0"))
timeout = int(os.getenv("PW_TIMEOUT", "5"))
pool_maxsize = int(os.getenv("PW_POOL_MAXSIZE", "15"))
https_mode = os.getenv("PW_HTTPS", "no")
port = int(os.getenv("PW_PORT", "8675"))
style = os.getenv("PW_STYLE", "clear") + ".js"
siteid = os.getenv("PW_SITEID", None)
authpath = os.getenv("PW_AUTH_PATH", "")
authmode = os.getenv("PW_AUTH_MODE", "cookie")
cf = ".powerwall"
if authpath:
    cf = os.path.join(authpath, ".powerwall")
cachefile = os.getenv("PW_CACHE_FILE", cf)
control_secret = os.getenv("PW_CONTROL_SECRET", "")
gw_pwd = os.getenv("PW_GW_PWD", None)
rsa_key_path = os.getenv("PW_RSA_KEY_PATH", None)
wifi_host = os.getenv("PW_WIFI_HOST", None)
tedapi_api_version = os.getenv("PW_TEDAPI_API_VERSION", "V2024_06")
neg_solar = os.getenv("PW_NEG_SOLAR", "yes").lower() == "yes"
try:
    site_zero_threshold = int(os.getenv("PW_SITE_ZERO_THRESHOLD", "0"))
except (ValueError, TypeError):
    print(f"WARNING: PW_SITE_ZERO_THRESHOLD must be an integer, defaulting to 0")
    site_zero_threshold = 0
api_base_url = os.getenv(
    "PROXY_BASE_URL", "/"
)  # Prefix for public API calls, e.g. if you have everything behind a reverse proxy

# Network error handling configuration for weak WiFi scenarios
suppress_network_errors = os.getenv("PW_SUPPRESS_NETWORK_ERRORS", "no").lower() == "yes"
network_error_rate_limit = int(
    os.getenv("PW_NETWORK_ERROR_RATE_LIMIT", "5")
)  # errors per minute per function

# Additional robustness features for poor network conditions
fail_fast_mode = (
    os.getenv("PW_FAIL_FAST", "no").lower() == "yes"
)  # Return cached/empty data instead of retrying
graceful_degradation = (
    os.getenv("PW_GRACEFUL_DEGRADATION", "yes").lower() == "yes"
)  # Return partial data on errors
health_check_enabled = (
    os.getenv("PW_HEALTH_CHECK", "yes").lower() == "yes"
)  # Track connection health
degradation_cache_ttl_seconds = int(
    os.getenv("PW_CACHE_TTL", "30")
)  # Maximum age for cached data before returning None
tedapi_recovery_enabled = (
    os.getenv("PW_TEDAPI_RECOVERY", "yes").lower() == "yes"
)  # Auto-recover TEDAPI connection when proxy falls back to SolarOnly mode
try:
    TEDAPI_PROBE_INTERVAL = max(5, int(os.getenv("PW_TEDAPI_PROBE_INTERVAL", "30")))
except (ValueError, TypeError):
    TEDAPI_PROBE_INTERVAL = 30  # seconds between probes; default if env var is non-integer
TEDAPI_FALLBACK_THRESHOLD = 3  # consecutive probe failures before entering fallback mode
TEDAPI_RECOVERY_INITIAL_INTERVAL = 60   # initial recovery retry interval (seconds)
TEDAPI_RECOVERY_MAX_INTERVAL = 300      # cap on retry interval (seconds)

# Global Stats
proxystats = {
    "pypowerwall": "%s Proxy %s" % (pypowerwall.version, BUILD),
    "mode": "Unknown",
    "gets": 0,
    "posts": 0,
    "errors": 0,
    "timeout": 0,
    "uri": {},
    "ts": int(time.time()),
    "start": int(time.time()),
    "clear": int(time.time()),
    "uptime": "",
    "mem": 0,
    "site_name": "",
    "cloudmode": False,
    "fleetapi": False,
    "tedapi": False,
    "pw3": False,
    "tedapi_mode": "off",
    "tedapi_api_version": "V2024_06",
    "siteid": None,
    "counter": 0,
    "cf": cachefile,
    "config": {
        "PW_BIND_ADDRESS": bind_address,
        "PW_PASSWORD": "*" * len(password) if password else None,
        "PW_EMAIL": email,
        "PW_HOST": host,
        "PW_TIMEZONE": timezone,
        "PW_DEBUG": debugmode,
        "PW_CACHE_EXPIRE": cache_expire,
        "PW_BROWSER_CACHE": browser_cache,
        "PW_TIMEOUT": timeout,
        "PW_POOL_MAXSIZE": pool_maxsize,
        "PW_HTTPS": https_mode,
        "PW_PORT": port,
        "PW_STYLE": style,
        "PW_SITEID": siteid,
        "PW_AUTH_PATH": authpath,
        "PW_AUTH_MODE": authmode,
        "PW_CACHE_FILE": cachefile,
        "PW_CONTROL_SECRET": "*" * len(control_secret) if control_secret else None,
        "PW_GW_PWD": "*" * len(gw_pwd) if gw_pwd else None,
        "PW_RSA_KEY_PATH": rsa_key_path,
        "PW_WIFI_HOST": wifi_host,
        "PW_NEG_SOLAR": neg_solar,
        "PW_SITE_ZERO_THRESHOLD": site_zero_threshold,
        "PW_SUPPRESS_NETWORK_ERRORS": suppress_network_errors,
        "PW_NETWORK_ERROR_RATE_LIMIT": network_error_rate_limit,
        "PW_FAIL_FAST": fail_fast_mode,
        "PW_GRACEFUL_DEGRADATION": graceful_degradation,
        "PW_HEALTH_CHECK": health_check_enabled,
        "PW_CACHE_TTL": degradation_cache_ttl_seconds,
        "PW_TEDAPI_RECOVERY": tedapi_recovery_enabled,
        "PW_TEDAPI_PROBE_INTERVAL": TEDAPI_PROBE_INTERVAL,
    },
}
proxystats_lock = threading.RLock()
# Cap on distinct paths tracked in proxystats["uri"] (matches the 100-entry
# cap used by _endpoint_stats). Query strings are stripped before counting;
# new distinct paths beyond the cap are aggregated under "other".
URI_STATS_MAX = 100

if https_mode == "yes":
    # run https mode with self-signed cert
    cookiesuffix = "path=/;SameSite=None;Secure;"
    httptype = "HTTPS"
elif https_mode == "http":
    # run http mode but simulate https for proxy behind https proxy
    cookiesuffix = "path=/;SameSite=None;Secure;"
    httptype = "HTTP"
else:
    # run in http mode
    cookiesuffix = "path=/;"
    httptype = "HTTP"

# Logging
log = logging.getLogger("proxy")
logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
log.setLevel(logging.INFO)

if debugmode:
    log.info(
        "pyPowerwall [%s] Proxy Server [%s] - %s Port %d - DEBUG"
        % (pypowerwall.version, BUILD, httptype, port)
    )
    pypowerwall.set_debug(True)
    log.setLevel(logging.DEBUG)
else:
    log.info(
        "pyPowerwall [%s] Proxy Server [%s] - %s Port %d"
        % (pypowerwall.version, BUILD, httptype, port)
    )
log.info("pyPowerwall Proxy Started")

# Log network error handling configuration
if suppress_network_errors:
    log.info("Network error logging suppressed (PW_SUPPRESS_NETWORK_ERRORS=yes)")
else:
    log.info(
        f"Network error rate limiting: {network_error_rate_limit} errors/minute per function"
    )

# Log additional robustness features
if fail_fast_mode:
    log.info(
        "Fail-fast mode enabled (PW_FAIL_FAST=yes) - degraded connections return immediately"
    )
if graceful_degradation:
    log.info(
        f"Graceful degradation enabled (PW_GRACEFUL_DEGRADATION=yes) - cached data TTL: {degradation_cache_ttl_seconds}s"
    )
if health_check_enabled:
    log.info("Connection health monitoring enabled (PW_HEALTH_CHECK=yes)")

# Rate limiter for network error logging to prevent spam
_error_counts = {}
_error_counts_lock = threading.RLock()
_network_error_summary = {}
_last_summary_time = time.time()


def should_log_network_error(func_name, max_per_minute=5):
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
        current_keys = {
            f"{func_name}_{minute_bucket}",
            f"{func_name}_{minute_bucket-1}",
        }
        keys_to_remove = [
            k
            for k in _error_counts.keys()
            if k not in current_keys and k.startswith(f"{func_name}_")
        ]
        for k in keys_to_remove:
            del _error_counts[k]

        return _error_counts[key] <= max_per_minute


def track_network_error(func_name, error_type):
    """Track network errors for summary reporting."""
    global _network_error_summary, _last_summary_time

    with _error_counts_lock:
        if func_name not in _network_error_summary:
            _network_error_summary[func_name] = {}

        if error_type not in _network_error_summary[func_name]:
            _network_error_summary[func_name][error_type] = 0

        _network_error_summary[func_name][error_type] += 1

        # Log summary every 5 minutes if there are errors
        current_time = time.time()
        if current_time - _last_summary_time > 300:  # 5 minutes
            if _network_error_summary:
                log.warning("Network Error Summary (last 5 minutes):")
                for func, errors in _network_error_summary.items():
                    for error_type, count in errors.items():
                        log.warning(f"  {func}: {count} {error_type} errors")
                _network_error_summary.clear()
            _last_summary_time = current_time


# Connection health tracking and caching for graceful degradation
_connection_health = {
    "consecutive_failures": 0,
    "last_success_time": time.time(),
    "total_failures": 0,
    "total_successes": 0,
    "is_degraded": False,
}
_connection_health_lock = threading.RLock()

# SolarOnly fallback mode tracking (distinct from connection_health degradation)
# is_degraded = transient transport failures; is_fallback_mode = TEDAPI fell back to SolarOnly
_fallback_mode = {
    "is_fallback_mode": False,
    "fallback_since": None,       # timestamp when fallback was entered
    "recovery_attempts": 0,
    "last_recovery_attempt": None,
}
_fallback_mode_lock = threading.RLock()
_fallback_recovery_lock = threading.Lock()  # serializes pw.connect() calls from recovery thread

# Cache for last known good responses (graceful degradation)
_last_good_responses = {}
_last_good_responses_lock = threading.RLock()

# Performance cache for frequently-hit endpoints (separate from degradation cache)
_performance_cache = {}
_performance_cache_lock = threading.RLock()

# Endpoint call tracking for success/failure statistics
_endpoint_stats = {}
_endpoint_stats_lock = threading.RLock()

# Health thresholds
HEALTH_FAILURE_THRESHOLD = 5  # consecutive failures before degraded mode
HEALTH_RECOVERY_THRESHOLD = 3  # consecutive successes to exit degraded mode


def update_connection_health(success=True):
    """Update connection health metrics and degraded mode status."""
    global _connection_health

    with _connection_health_lock:
        if success:
            _connection_health["consecutive_failures"] = 0
            _connection_health["last_success_time"] = time.time()
            _connection_health["total_successes"] += 1

            # Check if we should exit degraded mode
            if _connection_health["is_degraded"]:
                if (
                    _connection_health["total_successes"] % HEALTH_RECOVERY_THRESHOLD
                    == 0
                ):
                    _connection_health["is_degraded"] = False
                    if not suppress_network_errors:
                        log.info("Connection health recovered - exiting degraded mode")
        else:
            _connection_health["consecutive_failures"] += 1
            _connection_health["total_failures"] += 1

            # Check if we should enter degraded mode
            if not _connection_health["is_degraded"]:
                if (
                    _connection_health["consecutive_failures"]
                    >= HEALTH_FAILURE_THRESHOLD
                ):
                    _connection_health["is_degraded"] = True
                    if not suppress_network_errors:
                        log.warning(
                            f"Connection health degraded after {HEALTH_FAILURE_THRESHOLD} consecutive failures - entering graceful degradation mode"
                        )


def enter_fallback_mode(reason="TEDAPI data unavailable"):
    """Signal that proxy has entered SolarOnly fallback mode (distinct from is_degraded)."""
    with _fallback_mode_lock:
        if not _fallback_mode["is_fallback_mode"]:
            _fallback_mode["is_fallback_mode"] = True
            _fallback_mode["fallback_since"] = time.time()
            _fallback_mode["recovery_attempts"] = 0
            _fallback_mode["last_recovery_attempt"] = None
            log.warning(
                f"Proxy entering SolarOnly fallback mode: {reason}. "
                "Background recovery will retry periodically."
            )


def exit_fallback_mode():
    """Signal that proxy has recovered from SolarOnly fallback mode."""
    with _fallback_mode_lock:
        if _fallback_mode["is_fallback_mode"]:
            duration = time.time() - (_fallback_mode["fallback_since"] or time.time())
            attempts = _fallback_mode["recovery_attempts"]
            _fallback_mode["is_fallback_mode"] = False
            _fallback_mode["fallback_since"] = None
            _fallback_mode["recovery_attempts"] = 0
            _fallback_mode["last_recovery_attempt"] = None
            log.info(
                f"Proxy recovered from SolarOnly fallback mode after "
                f"{duration:.0f}s and {attempts} recovery attempt(s)."
            )


def _tedapi_probe_and_recover():
    """
    Background thread: probe TEDAPI health and recover from SolarOnly fallback.

    Runs only when TEDAPI mode is active. Polls pw.version() every TEDAPI_PROBE_INTERVAL
    seconds to detect SolarOnly entry. After TEDAPI_FALLBACK_THRESHOLD consecutive None
    results, enters fallback mode and starts attempting reconnect via pw.connect(retry=False).
    On successful recovery, exits fallback mode and resets exponential backoff.
    Stays in SolarOnly if recovery fails — proxy keeps serving available data.
    """
    consecutive_failures = 0
    recovery_interval = TEDAPI_RECOVERY_INITIAL_INTERVAL

    while True:
        try:
            time.sleep(TEDAPI_PROBE_INTERVAL)

            # Only probe when in TEDAPI mode
            if not getattr(pw, 'tedapi', None):
                consecutive_failures = 0
                continue

            with _fallback_mode_lock:
                in_fallback = _fallback_mode["is_fallback_mode"]

            if not in_fallback:
                # Healthy path: probe TEDAPI (treat exceptions as probe failures)
                try:
                    version = pw.version()  # direct call — don't want safe_pw_call health side-effects
                except Exception as probe_exc:
                    log.debug(f"TEDAPI probe exception (counts as failure): {probe_exc}")
                    version = None
                if version is not None:
                    consecutive_failures = 0
                    recovery_interval = TEDAPI_RECOVERY_INITIAL_INTERVAL
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= TEDAPI_FALLBACK_THRESHOLD:
                        enter_fallback_mode(
                            f"TEDAPI returned no data for {consecutive_failures} consecutive probes"
                        )
            else:
                # Fallback path: wait the backoff interval then attempt reconnect
                extra_wait = recovery_interval - TEDAPI_PROBE_INTERVAL
                if extra_wait > 0:
                    time.sleep(extra_wait)

                with _fallback_mode_lock:
                    _fallback_mode["recovery_attempts"] += 1
                    _fallback_mode["last_recovery_attempt"] = time.time()
                    attempt_num = _fallback_mode["recovery_attempts"]

                log.info(f"TEDAPI recovery attempt #{attempt_num} (interval={recovery_interval}s)...")

                recovered = False
                with _fallback_recovery_lock:
                    try:
                        if pw.connect(retry=False):
                            # Verify data flows after reconnect
                            version = pw.version()
                            if version is not None:
                                recovered = True
                    except Exception as exc:
                        log.warning(f"TEDAPI recovery attempt #{attempt_num} exception: {exc}")

                if recovered:
                    exit_fallback_mode()
                    consecutive_failures = 0
                    recovery_interval = TEDAPI_RECOVERY_INITIAL_INTERVAL
                else:
                    next_interval = min(recovery_interval * 2, TEDAPI_RECOVERY_MAX_INTERVAL)
                    log.warning(
                        f"TEDAPI recovery attempt #{attempt_num} failed — "
                        f"staying in SolarOnly, next retry in {next_interval}s"
                    )
                    recovery_interval = next_interval

        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as exc:
            log.debug(f"TEDAPI probe/recovery thread unexpected error: {exc}")


def get_cached_response(endpoint):
    """Get cached response for graceful degradation."""
    if not graceful_degradation:
        return None

    with _last_good_responses_lock:
        if endpoint in _last_good_responses:
            cached_data, timestamp = _last_good_responses[endpoint]
            age = time.time() - timestamp
            if age < degradation_cache_ttl_seconds:
                if debugmode:
                    log.debug(f"Using cached response for {endpoint} (age: {age:.1f}s)")
                return cached_data
            else:
                # Cache expired - remove entry and return None
                if debugmode:
                    log.debug(
                        f"Cache expired for {endpoint} (age: {age:.1f}s > {degradation_cache_ttl_seconds}s)"
                    )
                del _last_good_responses[endpoint]
    return None


def cache_response(endpoint, response):
    """Cache successful response for graceful degradation."""
    if not graceful_degradation or response is None:
        return

    with _last_good_responses_lock:
        _last_good_responses[endpoint] = (response, time.time())

        # Limit cache size to prevent memory growth
        if len(_last_good_responses) > 50:
            # Remove oldest entries
            oldest_key = min(
                _last_good_responses.keys(), key=lambda k: _last_good_responses[k][1]
            )
            del _last_good_responses[oldest_key]


def get_performance_cached(cache_key):
    """
    Get cached endpoint response for performance optimization.
    Uses standard cache_expire TTL (typically 5 seconds).

    Args:
        cache_key: The cache key (e.g., '/csv/v2', '/json', '/freq', '/pod')

    Returns:
        Cached response string if available and fresh, None otherwise
    """
    with _performance_cache_lock:
        if cache_key not in _performance_cache:
            return None

        data, timestamp = _performance_cache[cache_key]
        age = time.time() - timestamp

        # Use standard cache_expire (same as pypowerwall's internal cache)
        if age < cache_expire:
            log.debug(f"Performance cache hit for {cache_key} (age: {age:.2f}s)")
            return data
        else:
            log.debug(f"Performance cache expired for {cache_key} (age: {age:.2f}s)")
            return None


def cache_performance_response(cache_key, data):
    """
    Cache endpoint response for performance optimization.

    Args:
        cache_key: The cache key (e.g., '/csv/v2', '/json', '/freq', '/pod')
        data: The response string to cache
    """
    with _performance_cache_lock:
        _performance_cache[cache_key] = (data, time.time())
        log.debug(f"Cached performance response for {cache_key}")


def performance_cached(cache_key):
    """
    Decorator for performance caching of route handlers.

    Args:
        cache_key: The cache key to use (e.g., '/vitals', '/strings', '/freq')

    Returns:
        Decorator function that wraps route handlers with caching logic
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Try cache first
            cached_response = get_performance_cached(cache_key)
            if cached_response is not None:
                return cached_response

            # Cache miss - generate fresh data
            result = func(*args, **kwargs)

            # Only cache non-None results
            if result is not None:
                cache_performance_response(cache_key, result)

            return result

        return wrapper
    return decorator


def cached_route_handler(cache_key, data_generator):
    """
    Helper function for performance-cached route handling.

    Args:
        cache_key: The cache key to use for this route
        data_generator: Function that generates the response data

    Returns:
        Cached response if available, otherwise fresh data (and caches it)
    """
    # Try cache first
    cached_response = get_performance_cached(cache_key)
    if cached_response is not None:
        return cached_response

    # Cache miss - generate fresh data
    result = data_generator()

    # Only cache non-None results
    if result is not None:
        cache_performance_response(cache_key, result)

    return result


def track_endpoint_call(endpoint, success=True):
    """Track endpoint call success/failure statistics."""
    with _endpoint_stats_lock:
        if endpoint not in _endpoint_stats:
            _endpoint_stats[endpoint] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "last_success_time": None,
                "last_failure_time": None,
            }

        _endpoint_stats[endpoint]["total_calls"] += 1
        current_time = time.time()

        if success:
            _endpoint_stats[endpoint]["successful_calls"] += 1
            _endpoint_stats[endpoint]["last_success_time"] = current_time
        else:
            _endpoint_stats[endpoint]["failed_calls"] += 1
            _endpoint_stats[endpoint]["last_failure_time"] = current_time

        # Limit endpoint stats size to prevent memory growth
        if len(_endpoint_stats) > 100:
            # Remove oldest entries (by last activity)
            oldest_endpoint = min(
                _endpoint_stats.keys(),
                key=lambda k: max(
                    _endpoint_stats[k]["last_success_time"] or 0,
                    _endpoint_stats[k]["last_failure_time"] or 0,
                ),
            )
            del _endpoint_stats[oldest_endpoint]


# Global wrapper for pypowerwall function calls
def safe_pw_call(pw_func, *args, **kwargs):
    """
    Safely call a pypowerwall function with global exception handling.
    Returns None on any exception and logs a clean error message.
    Optimized for weak WiFi connections with fast failure and concise logging.
    Includes health tracking and graceful degradation support.
    """
    global proxystats

    def get_descriptive_name():
        """Build descriptive function name with arguments for better debugging."""
        func_name = getattr(pw_func, "__name__", str(pw_func))
        if func_name == "poll" and args:
            # For poll() calls, include the URI endpoint being called
            return f"{func_name}('{args[0]}')" if args[0] else func_name
        elif args:
            # For other functions, show first argument if it exists
            first_arg = str(args[0])[:50]  # Limit to 50 chars to keep logs readable
            return f"{func_name}({first_arg})"
        else:
            return func_name

    # In fail-fast mode with degraded connection, return None immediately
    if fail_fast_mode and health_check_enabled:
        with _connection_health_lock:
            if _connection_health["is_degraded"]:
                return None

    try:
        result = pw_func(*args, **kwargs)

        # Only update health tracking on true, fresh connection success
        if health_check_enabled and result is not None:
            update_connection_health(success=True)

        return result
    except (
        PyPowerwallInvalidConfigurationParameter,
        InvalidBatteryReserveLevelException,
        PyPowerwallTEDAPINoTeslaAuthFile,
        PyPowerwallTEDAPITeslaNotConnected,
        PyPowerwallTEDAPINotImplemented,
        PyPowerwallTEDAPIInvalidPayload,
        PyPowerwallFleetAPINoTeslaAuthFile,
        PyPowerwallFleetAPITeslaNotConnected,
        PyPowerwallFleetAPINotImplemented,
        PyPowerwallFleetAPIInvalidPayload,
    ) as e:
        descriptive_name = get_descriptive_name()
        log.warning(f"Powerwall API Error in {descriptive_name}: {str(e)}")
        with proxystats_lock:
            proxystats["errors"] = proxystats["errors"] + 1
        return None
    except (
        ConnectionError,
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
        urllib3.exceptions.MaxRetryError,
    ) as e:
        func_name = getattr(pw_func, "__name__", str(pw_func))
        descriptive_name = get_descriptive_name()
        error_type = type(e).__name__

        # Update health tracking on network failure
        if health_check_enabled:
            update_connection_health(success=False)

        # Track error for summary reporting
        track_network_error(func_name, error_type)

        # Rate limit individual error logging to prevent spam
        if not suppress_network_errors and should_log_network_error(
            func_name, network_error_rate_limit
        ):
            if "timeout" in error_type.lower():
                log.info(f"Network timeout in {descriptive_name}: {error_type}")
            else:
                log.info(f"Network error in {descriptive_name}: {error_type}")

        with proxystats_lock:
            proxystats["timeout"] = proxystats["timeout"] + 1
        return None
    except Exception as e:
        descriptive_name = get_descriptive_name()
        error_type = type(e).__name__

        # Update health tracking on unexpected failure
        if health_check_enabled:
            update_connection_health(success=False)

        # Log unexpected errors - focus on function and likely payload issues
        if error_type == "TypeError":
            log.warning(f"Bad payload response in {descriptive_name} - likely null/malformed data from Powerwall")
        else:
            if debugmode:
                log.error(f"Unexpected error in {descriptive_name}: {error_type}: {str(e)}")
            else:
                log.warning(f"Unexpected error in {descriptive_name}: {error_type}")
        with proxystats_lock:
            proxystats["errors"] = proxystats["errors"] + 1
        return None


def safe_endpoint_call(endpoint_name, pw_func, *args, jsonformat=True, **kwargs):
    """
    Safely call a pypowerwall function for an endpoint with caching and graceful degradation.

    Args:
        endpoint_name: Name of the endpoint for caching (e.g., '/aggregates')
        pw_func: The pypowerwall function to call
        *args: Arguments to pass to the function
        jsonformat: Whether to return JSON formatted response (default True)
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Response data on success, cached data if available and fresh enough, None if no data available
    """
    # Namespace the degradation-cache key by response format: the same endpoint can be
    # called with jsonformat=True (caches a JSON string) and jsonformat=False (caches a
    # dict). Sharing one key would serve a string to dict consumers during outages.
    cache_key = f"{endpoint_name}:json" if jsonformat else endpoint_name

    # Try to get fresh data
    if jsonformat:
        result = safe_pw_call(pw_func, *args, jsonformat=True, **kwargs)
    else:
        result = safe_pw_call(pw_func, *args, **kwargs)

    # Only treat as a true success if result is not None and is not a cached response
    if result is not None:
        cache_response(cache_key, result)
        track_endpoint_call(endpoint_name, success=True)
        return result

    # Failed to get fresh data - track failure
    track_endpoint_call(endpoint_name, success=False)

    # Try cached response (do NOT reset consecutive_failures if using cache)
    cached_result = get_cached_response(cache_key)
    if cached_result is not None:
        # Do not call update_connection_health(success=True) here
        return cached_result

    # No fresh or cached data available
    return None


# Ensure api_base_url ends with a /
if not api_base_url.endswith("/"):
    api_base_url += "/"
    log.info(f"Added trailing / to API Base URL: {api_base_url}")

# Check for cache expire time limit below 5s
if cache_expire < 5:
    log.warning("Cache expiration set below 5s (PW_CACHE_EXPIRE=%d)" % cache_expire)


# Signal handler - Exit on SIGTERM
# noinspection PyUnusedLocal
def sig_term_handle(signum, frame):
    raise SystemExit


# Register signal handler
signal.signal(signal.SIGTERM, sig_term_handle)


# Reap terminated child processes to prevent zombie (<defunct>) accumulation.
#
# When this server runs as PID 1 (e.g. without an init wrapper), the container
# HEALTHCHECK (curl -sf ... /health, every 30s) spawns curl as a child process.
# Without a SIGCHLD handler, terminated children accumulate as zombies and can
# eventually exhaust the PID table. The Docker image uses tini as PID 1, which
# handles reaping automatically; this handler is kept as a safety net for bare
# invocations where the server itself is PID 1.
#
# This server currently spawns no child processes of its own. The WNOHANG flag
# ensures only already-exited children are collected; if subprocess use is added
# later, review whether a shared SIGCHLD handler remains appropriate.
# A targeted waitpid(WNOHANG) loop is preferred over signal.SIG_IGN so that
# exit status is not silently discarded.
# noinspection PyUnusedLocal
def reap_children(signum, frame):
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break  # no child processes remain
        if pid == 0:
            break  # no more terminated children to reap right now


# SIGCHLD is not available on Windows. Only register when this process is PID 1
# (bare container without tini). When tini is the ENTRYPOINT it runs as PID 1
# and handles zombie reaping itself; this handler is defense-in-depth for
# deployments that skip the ENTRYPOINT (e.g. --entrypoint python3).
if hasattr(signal, "SIGCHLD") and os.getpid() == 1:
    signal.signal(signal.SIGCHLD, reap_children)


# Get Value Function - Key to Value or Return Null
def get_value(a, key):
    if key in a:
        return a[key]
    else:
        log.debug("Missing key in payload [%s]" % key)
        return None


# Connect to Powerwall
# TODO: Add support for multiple Powerwalls
try:
    pw = pypowerwall.Powerwall(
        host=host,
        password=password,
        email=email,
        timezone=timezone,
        pwcacheexpire=cache_expire,
        timeout=timeout,
        poolmaxsize=pool_maxsize,
        siteid=siteid,
        authpath=authpath,
        authmode=authmode,
        cachefile=cachefile,
        auto_select=True,
        retry_modes=True,
        gw_pwd=gw_pwd,
        rsa_key_path=rsa_key_path,
        wifi_host=wifi_host,
        tedapi_api_version=tedapi_api_version,
    )
except Exception as e:
    log.error(f"Powerwall Connection Error: {str(e)}")
    log.error("Fatal Error: Unable to connect. Please fix config and restart.")
    while True:
        try:
            time.sleep(5)  # Infinite loop to keep container running
        except (KeyboardInterrupt, SystemExit):
            sys.exit(0)

site_name = safe_pw_call(pw.site_name) or "Unknown"
if pw.cloudmode or pw.fleetapi:
    if pw.fleetapi:
        proxystats["mode"] = "FleetAPI"
        log.info("pyPowerwall Proxy Server - FleetAPI Mode")
    else:
        proxystats["mode"] = "Cloud"
        log.info("pyPowerwall Proxy Server - Cloud Mode")
    log.info("Connected to Site ID %s (%s)" % (pw.client.siteid, site_name.strip()))
    if siteid is not None and siteid != str(pw.client.siteid):
        log.info("Switch to Site ID %s" % siteid)
        if not pw.client.change_site(siteid):
            log.error("Fatal Error: Unable to connect. Please fix config and restart.")
            while True:
                try:
                    time.sleep(5)  # Infinite loop to keep container running
                except (KeyboardInterrupt, SystemExit):
                    sys.exit(0)
else:
    log.info("pyPowerwall Proxy Server - Local Mode")
    log.info("Connected to Energy Gateway %s (%s)" % (host, site_name.strip()))
    if pw.tedapi:
        proxystats["tedapi"] = True
        proxystats["tedapi_mode"] = pw.tedapi_mode
        proxystats["tedapi_api_version"] = pw.tedapi_api_version
        proxystats["pw3"] = pw.tedapi.pw3
        log.info(f"TEDAPI Mode Enabled for Device Vitals ({pw.tedapi_mode}, queries={pw.tedapi_api_version})")
    # Set mode string with transport detail
    def build_mode_string(control=False):
        """Build mode display string from active transports."""
        if not pw.tedapi:
            return "Local"
        parts = [pw.tedapi_mode]
        tedapi = pw.tedapi
        if getattr(tedapi, 'v1r', False) and getattr(tedapi, 'wifi_session', None):
            parts.append("wifi")
        if control:
            parts.append("control")
        return f"Local ({'+'.join(parts)})"
    proxystats["mode"] = build_mode_string()

pw_control = None
if control_secret:
    log.info("Control Commands Activating - WARNING: Use with caution!")
    try:
        if pw.cloudmode or pw.fleetapi:
            pw_control = pw
        elif pw.tedapi and pw.tedapi.v1r:
            pw_control = pw
            log.info("Control Mode: Using TEDapi LAN control (v1r filestore)")
        else:
            pw_control = pypowerwall.Powerwall(
                "",
                password,
                email,
                siteid=siteid,
                authpath=authpath,
                authmode=authmode,
                cachefile=cachefile,
                auto_select=True,
            )
    except Exception as e:
        log.error("Control Mode Failed: Unable to connect to cloud - Run Setup")
        control_secret = ""
    if pw_control:
        if pw.tedapi and pw.tedapi.v1r and not pw.cloudmode and not pw.fleetapi:
            log.info(f"Control Mode Enabled: LAN Mode ({pw.tedapi_mode}+control)")
        else:
            log.info(f"Control Mode Enabled: Cloud Mode ({pw_control.mode}) Connected")
        # Update mode string to include control transport
        if not pw.cloudmode and not pw.fleetapi and pw.tedapi:
            proxystats["mode"] = build_mode_string(control=True)
    else:
        log.error("Control Mode Failed: Unable to connect to cloud - Run Setup")
        control_secret = None


# Start background TEDAPI probe/recovery thread (TEDAPI modes only)
if tedapi_recovery_enabled and pw.tedapi:
    _recovery_thread = threading.Thread(
        target=_tedapi_probe_and_recover, name="tedapi-recovery", daemon=True
    )
    _recovery_thread.start()
    log.info(
        "TEDAPI probe/recovery thread started (interval=%ds, threshold=%d)",
        TEDAPI_PROBE_INTERVAL, TEDAPI_FALLBACK_THRESHOLD
    )


def get_transport_health():
    """Build transport health status dict for /health endpoint."""
    transports = {}
    tedapi = getattr(pw, 'tedapi', None)
    if tedapi and hasattr(tedapi, 'v1r') and tedapi.v1r:
        # v1r LAN transport
        v1r_info = {
            "active": True,
            "status": "ok" if tedapi.din else "unavailable",
            "host": tedapi.gw_ip,
            "leader_din": tedapi.din,
        }
        if tedapi.lan_last_success:
            v1r_info["last_success_age_seconds"] = round(time.time() - tedapi.lan_last_success, 1)
        transports["v1r_lan"] = v1r_info
        # WiFi TEDAPI transport (follower fallback)
        if tedapi.wifi_session:
            cooldown_remaining = max(0, tedapi.wifi_cooldown - time.time())
            if tedapi.wifi_available:
                wifi_status = "ok"
            elif cooldown_remaining > 0:
                wifi_status = "degraded"
            else:
                wifi_status = "unavailable"
            transports["wifi_tedapi"] = {
                "active": True,
                "status": wifi_status,
                "host": tedapi.wifi_host,
                "available": tedapi.wifi_available,
                "cooldown_remaining_seconds": round(cooldown_remaining, 0),
            }
        else:
            transports["wifi_tedapi"] = {"active": False}
    elif tedapi:
        # Standard WiFi TEDAPI
        transports["wifi_tedapi"] = {
            "active": True,
            "status": "ok" if tedapi.din else "unavailable",
            "host": tedapi.gw_ip,
        }
    # Control transport
    if pw_control:
        if tedapi and tedapi.v1r:
            transports["lan_control"] = {
                "active": True,
                "status": "ok",
                "mode": "v1r_filestore",
            }
        else:
            transports["cloud_control"] = {
                "active": True,
                "status": "ok",
                "mode": getattr(pw_control, 'mode', 'unknown'),
            }
    elif control_secret:
        transports["cloud_control"] = {"active": False, "status": "failed"}
    return transports


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# pylint: disable=arguments-differ,global-variable-not-assigned
# noinspection PyPep8Naming
class Handler(BaseHTTPRequestHandler):
    def log_message(self, log_format, *args):
        if debugmode:
            log.debug("%s %s" % (self.address_string(), log_format % args))
        else:
            pass

    def address_string(self):
        # replace function to avoid lookup delays
        hostaddr, hostport = self.client_address[:2]
        return hostaddr

    def do_POST(self):
        global proxystats
        contenttype = "application/json"
        message = '{"error": "Invalid Request"}'

        # If set, remove the api_base_url from the requested path. This allows installing the
        # the proxy on a path without impacting the use of Telegraf or other integrations. Python 3.9+
        request_path = self.path
        new_path = request_path.removeprefix(api_base_url)
        if new_path is not request_path:
            request_path = "/" + new_path

        if request_path.startswith("/control"):
            # curl -X POST -d "value=20&token=1234" http://localhost:8675/control/reserve
            # curl -X POST -d "value=backup&token=1234" http://localhost:8675/control/mode
            message = None
            if not control_secret:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                value = token = ""
                try:
                    action = urlparse(request_path).path.split("/")[2]
                    content_length = int(self.headers["Content-Length"])
                    # Cap the POST body size - control commands are tiny
                    # (value/token/mode params); anything larger is abuse.
                    if content_length < 0 or content_length > MAX_POST_BODY:
                        message = '{"error": "Control Command Error: Invalid Request"}'
                        log.error(f"Control Command Error: POST body too large ({content_length} bytes)")
                    else:
                        post_data = self.rfile.read(content_length)
                        query_params = parse_qs(post_data.decode("utf-8"))
                        value = query_params.get("value", [""])[0]
                        token = query_params.get("token", [""])[0]
                except Exception as er:
                    message = '{"error": "Control Command Error: Invalid Request"}'
                    log.error(f"Control Command Error: {er}")
                if not message:
                    # Check if unable to connect (cloud mode needs client, tedapi needs tedapi)
                    has_tedapi_control = pw.tedapi and pw.tedapi.v1r
                    if not has_tedapi_control and pw_control.client is None:
                        message = '{"error": "Control Command Error: Unable to connect to cloud mode - Run Setup"}'
                        log.error(
                            "Control Command Error: Unable to connect to cloud mode - Run Setup"
                        )
                    else:
                        # Constant-time compare to avoid timing side channel
                        if token and hmac.compare_digest(token, control_secret):
                            if action == "reserve":
                                # ensure value is an integer
                                if not value:
                                    # return current reserve level in json string
                                    message = '{"reserve": %s}' % (
                                        safe_pw_call(pw_control.get_reserve) or 0
                                    )
                                elif value.isdigit():
                                    # Optional companion `mode` parameter lets a single
                                    # /control/reserve POST update both reserve and mode
                                    # in one set_operation() invocation. Without it, a
                                    # caller that wants to change both has to POST to
                                    # /control/reserve AND /control/mode, which causes
                                    # set_operation() to run twice -- writing the Tesla
                                    # /backup and /operation endpoints twice each and
                                    # producing duplicate audit-log entries. Omitting
                                    # the parameter preserves the original behaviour.
                                    mode = query_params.get("mode", [""])[0]
                                    if mode in [
                                        "self_consumption",
                                        "backup",
                                        "autonomous",
                                    ]:
                                        result = safe_pw_call(
                                            pw_control.set_operation,
                                            int(value),
                                            mode,
                                        )
                                        message = json.dumps(
                                            result
                                            if result is not None
                                            else {"error": "Failed to set reserve+mode"}
                                        )
                                        log.info(
                                            f"Control Command: Set Reserve to {value} (mode={mode})"
                                        )
                                    elif mode:
                                        message = (
                                            '{"error": "Control Command Mode Invalid"}'
                                        )
                                    else:
                                        result = safe_pw_call(
                                            pw_control.set_reserve, int(value)
                                        )
                                        message = json.dumps(
                                            result
                                            if result is not None
                                            else {"error": "Failed to set reserve"}
                                        )
                                        log.info(f"Control Command: Set Reserve to {value}")
                                else:
                                    message = (
                                        '{"error": "Control Command Value Invalid"}'
                                    )
                            elif action == "mode":
                                if not value:
                                    # return current mode in json string
                                    message = '{"mode": "%s"}' % (
                                        safe_pw_call(pw_control.get_mode) or "unknown"
                                    )
                                elif value in [
                                    "self_consumption",
                                    "backup",
                                    "autonomous",
                                ]:
                                    # Optional companion `level` parameter -- see the
                                    # comment in the /control/reserve branch above.
                                    level = query_params.get("level", [""])[0]
                                    if level.isdigit():
                                        result = safe_pw_call(
                                            pw_control.set_operation,
                                            int(level),
                                            value,
                                        )
                                        message = json.dumps(
                                            result
                                            if result is not None
                                            else {"error": "Failed to set reserve+mode"}
                                        )
                                        log.info(
                                            f"Control Command: Set Mode to {value} (level={level})"
                                        )
                                    elif level:
                                        message = (
                                            '{"error": "Control Command Level Invalid"}'
                                        )
                                    else:
                                        result = safe_pw_call(pw_control.set_mode, value)
                                        message = json.dumps(
                                            result
                                            if result is not None
                                            else {"error": "Failed to set mode"}
                                        )
                                        log.info(f"Control Command: Set Mode to {value}")
                                else:
                                    message = (
                                        '{"error": "Control Command Value Invalid"}'
                                    )
                            elif action == "grid_charging":
                                # if empty or not a string, return current status
                                if not value:
                                    # return current grid_charging status in json string
                                    message = '{"grid_charging": %s}' % (
                                        "true" if safe_pw_call(pw_control.get_grid_charging) else "false"
                                    )
                                elif isinstance(value, str) and value.lower() in ["true", "false"]:
                                    bool_value = value.lower() == "true"
                                    result = safe_pw_call(
                                        pw_control.set_grid_charging, bool_value
                                    )
                                    if result is not None:
                                        message = '{"grid_charging": "Set Successfully"}'
                                    else:
                                        message = '{"error": "Failed to set grid_charging"}'
                                    log.info(
                                        f"Control Command: Set Grid Charging to {value}"
                                    )
                                else:
                                    message = (
                                        '{"error": "Control Command Value Invalid"}'
                                    )
                            elif action == "grid_export":
                                if not value:
                                    # return current grid_export status in json string
                                    message = '{"grid_export": %s}' % (
                                        str(
                                            safe_pw_call(pw_control.get_grid_export)
                                        ).lower()
                                        or "false"
                                    )
                                elif isinstance(value, str) and value.lower() in ["battery_ok", "pv_only", "never"]:
                                    result = safe_pw_call(
                                        pw_control.set_grid_export, value.lower()
                                    )
                                    if result is not None:
                                        message = '{"grid_export": "Set Successfully"}'
                                    else:
                                        message = '{"error": "Failed to set grid_export"}'
                                    log.info(
                                        f"Control Command: Set Grid Export to {value}"
                                    )
                                else:
                                    message = (
                                        '{"error": "Control Command Value Invalid"}'
                                    )
                            elif action == "max_backup":
                                if not pw.tedapi or not pw.tedapi.v1r:
                                    message = '{"error": "max_backup requires v1r LAN transport"}'
                                elif not value:
                                    # Return current backup events
                                    result = safe_pw_call(pw.tedapi.get_backup_events)
                                    message = json.dumps(
                                        result if result is not None
                                        else {"error": "Failed to get backup events"}
                                    )
                                elif value.lower() == "cancel":
                                    result = safe_pw_call(pw.tedapi.cancel_max_backup)
                                    if result:
                                        message = '{"max_backup": "Cancelled"}'
                                    else:
                                        message = '{"error": "Failed to cancel max backup"}'
                                    log.info("Control Command: Cancel Max Backup")
                                elif value.isdigit():
                                    result = safe_pw_call(
                                        pw.tedapi.schedule_max_backup, int(value)
                                    )
                                    if result:
                                        message = '{"max_backup": "Scheduled for %s seconds"}' % value
                                    else:
                                        message = '{"error": "Failed to schedule max backup"}'
                                    log.info(f"Control Command: Schedule Max Backup for {value}s")
                                else:
                                    message = '{"error": "Control Command Value Invalid - use seconds or cancel"}'
                            else:
                                message = '{"error": "Invalid Command Action"}'
                        else:
                            message = (
                                '{"unauthorized": "Control Command Token Invalid"}'
                            )
        if "error" in message:
            self.send_response(400)
            with proxystats_lock:
                proxystats["errors"] = proxystats["errors"] + 1
        elif "unauthorized" in message:
            self.send_response(401)
        else:
            self.send_response(200)
            with proxystats_lock:
                proxystats["posts"] = proxystats["posts"] + 1
        # Encode once - Content-Length must count bytes, not characters
        body = message.encode("utf8")
        self.send_header("Content-type", contenttype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global proxystats
        self.send_response(200)
        contenttype = "application/json"

        # If set, remove the api_base_url from the requested path. This allows installing the
        # the proxy on a path without impacting the use of Telegraf or other integrations. Python 3.9+
        request_path = self.path
        new_path = request_path.removeprefix(api_base_url)
        if new_path is not request_path:
            request_path = "/" + new_path

        if request_path == "/aggregates" or request_path == "/api/meters/aggregates":
            # Meters - JSON
            def generate_aggregates():
                # Both routes deliver same payload, use shared cache key
                aggregates = safe_endpoint_call(
                    "/aggregates", pw.poll, "/api/meters/aggregates"
                )

                # Parse aggregates if it's a JSON string
                if isinstance(aggregates, str):
                    try:
                        aggregates = json.loads(aggregates)
                    except (json.JSONDecodeError, TypeError):
                        aggregates = None

                # Apply site zero threshold - suppress phantom grid noise
                # Pass through None values - they indicate a data gap, not zero
                if (
                    site_zero_threshold > 0
                    and aggregates
                    and "site" in aggregates
                    and "instant_power" in aggregates["site"]
                    and aggregates["site"]["instant_power"] is not None
                    and abs(aggregates["site"]["instant_power"]) <= site_zero_threshold
                ):
                    aggregates["site"]["instant_power"] = 0

                if aggregates and not neg_solar and "solar" in aggregates:
                    solar = aggregates["solar"]
                    if solar and solar.get("instant_power") is not None and solar["instant_power"] < 0:
                        # Shift energy from solar to load
                        if "load" in aggregates and (aggregates["load"] or {}).get("instant_power") is not None:
                            aggregates["load"]["instant_power"] -= solar["instant_power"]
                        # Finally, clamp solar to 0
                        solar["instant_power"] = 0

                try:
                    if aggregates:
                        return json.dumps(aggregates)
                    else:
                        # No data available - return None to indicate stale/missing data
                        return None
                except:
                    log.error(f"JSON encoding error in payload: {aggregates}")
                    return None

            message = cached_route_handler("/aggregates", generate_aggregates)
        elif request_path == "/soe":
            # Battery Level - JSON
            message: str = safe_endpoint_call(
                "/soe", pw.poll, "/api/system_status/soe", jsonformat=True
            )
            # Return None if no current data available (better than fake 0%)
        elif request_path == "/api/system_status/soe":
            # Force 95% Scale
            level = safe_pw_call(pw.level, scale=True)
            message: str = (
                json.dumps({"percentage": level}) if level is not None else None
            )
        elif request_path == "/api/system_status/grid_status":
            # Grid Status - JSON
            message: str = safe_pw_call(
                pw.poll, "/api/system_status/grid_status", jsonformat=True
            )
        elif request_path.startswith("/csv") or request_path.startswith("/csv/v2"):
            # CSV Output - Grid,Home,Solar,Battery,Level
            # CSV2 Output - Grid,Home,Solar,Battery,Level,GridStatus,Reserve
            # Add ?headers to include CSV headers, e.g. http://localhost:8675/csv?headers
            # None values are treated as 0 in CSV output (use JSON endpoints to see data gaps as nulls)
            contenttype = "text/plain; charset=utf-8"

            # Determine endpoint and whether to include headers
            is_v2 = request_path.startswith("/csv/v2")
            include_headers = "headers" in request_path
            cache_key = f"/csv/v2{'_headers' if include_headers else ''}" if is_v2 else f"/csv{'_headers' if include_headers else ''}"

            def generate_csv():
                # Optimization: Use single aggregates call for all power values
                aggregates = safe_endpoint_call("/aggregates", pw.poll, "/api/meters/aggregates", jsonformat=False)
                if aggregates:
                    grid = (aggregates.get('site') or {}).get('instant_power', 0)
                    solar = (aggregates.get('solar') or {}).get('instant_power', 0)
                    battery = (aggregates.get('battery') or {}).get('instant_power', 0)
                    home = (aggregates.get('load') or {}).get('instant_power', 0)
                else:
                    grid = solar = battery = home = 0

                # Convert None to 0 for output BEFORE any comparisons below
                # (None = data gap, output as 0; comparing None crashes)
                grid = grid or 0
                solar = solar or 0
                battery = battery or 0
                home = home or 0

                # Apply negative solar correction if configured
                if not neg_solar and solar < 0:
                    # Shift energy from solar to load
                    home -= solar
                    solar = 0

                # Apply site zero threshold - suppress phantom grid noise
                if site_zero_threshold > 0 and abs(grid) <= site_zero_threshold:
                    grid = 0

                # Get battery level - poll() handles caching internally
                batterylevel = safe_pw_call(pw.level) or 0

                if is_v2:
                    # Get grid status and reserve - these use cached data internally
                    gridstatus = 1 if safe_pw_call(pw.grid_status) == "UP" else 0
                    reserve = safe_pw_call(pw.get_reserve) or 0

                # Build CSV response
                if is_v2:
                    result = ""
                    if include_headers:
                        result += (
                            "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n"
                        )
                    result += "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f,%d,%d\n" % (
                        grid,
                        home,
                        solar,
                        battery,
                        batterylevel,
                        gridstatus,
                        reserve,
                    )
                else:
                    result = ""
                    if include_headers:
                        result += "Grid,Home,Solar,Battery,BatteryLevel\n"
                    result += "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" % (
                        grid,
                        home,
                        solar,
                        battery,
                        batterylevel,
                    )
                return result

            message = cached_route_handler(cache_key, generate_csv)
        elif request_path == "/vitals":
            # Vitals Data - JSON
            message = cached_route_handler(
                "/vitals",
                lambda: safe_endpoint_call("/vitals", pw.vitals, jsonformat=True)
            )
        elif request_path == "/strings":
            # Strings Data - JSON
            message = cached_route_handler(
                "/strings",
                lambda: safe_endpoint_call("/strings", pw.strings, jsonformat=True)
            )
        elif request_path == "/stats":
            # Give Internal Stats
            # Do the slow work (network call, rusage) BEFORE taking the lock -
            # holding proxystats_lock across a gateway call would serialize
            # every other request thread for up to the pw timeout during outages
            stats_site_name = safe_pw_call(pw.site_name)
            stats_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            with proxystats_lock:
                proxystats["ts"] = int(time.time())
                delta = proxystats["ts"] - proxystats["start"]
                proxystats["uptime"] = str(datetime.timedelta(seconds=delta))
                proxystats["mem"] = stats_mem
                proxystats["site_name"] = stats_site_name
                proxystats["cloudmode"] = pw.cloudmode
                proxystats["fleetapi"] = pw.fleetapi
                if (pw.cloudmode or pw.fleetapi) and pw.client is not None:
                    proxystats["siteid"] = pw.client.siteid
                    proxystats["counter"] = pw.client.counter

                # Add connection health stats if enabled
                if health_check_enabled:
                    with _connection_health_lock:
                        proxystats["connection_health"] = {
                            "consecutive_failures": _connection_health[
                                "consecutive_failures"
                            ],
                            "total_failures": _connection_health["total_failures"],
                            "total_successes": _connection_health["total_successes"],
                            "is_degraded": _connection_health["is_degraded"],
                            "last_success_time": _connection_health[
                                "last_success_time"
                            ],
                            "cache_size": len(_last_good_responses)
                            if graceful_degradation
                            else 0,
                        }

                # Add SolarOnly fallback mode state
                with _fallback_mode_lock:
                    fm_snap = dict(_fallback_mode)
                proxystats["fallback_mode"] = {
                    "is_fallback_mode": fm_snap["is_fallback_mode"],
                    "fallback_since": fm_snap["fallback_since"],
                    "fallback_duration_seconds": (
                        round(time.time() - fm_snap["fallback_since"], 1)
                        if fm_snap["fallback_since"] else None
                    ),
                    "recovery_attempts": fm_snap["recovery_attempts"],
                    "last_recovery_attempt": fm_snap["last_recovery_attempt"],
                    "recovery_enabled": tedapi_recovery_enabled,
                }

                # Add cache memory usage statistics
                proxystats["mem_cache"] = {}

                with _error_counts_lock:
                    proxystats["mem_cache"]["error_counts"] = {
                        "entries": len(_error_counts),
                        "size_bytes": sys.getsizeof(_error_counts) + sum(
                            sys.getsizeof(k) + sys.getsizeof(v)
                            for k, v in _error_counts.items()
                        ),
                    }
                    proxystats["mem_cache"]["network_error_summary"] = {
                        "entries": len(_network_error_summary),
                        "size_bytes": sys.getsizeof(_network_error_summary) + sum(
                            sys.getsizeof(k) + sys.getsizeof(v) + sum(
                                sys.getsizeof(ek) + sys.getsizeof(ev)
                                for ek, ev in v.items()
                            ) for k, v in _network_error_summary.items()
                        ),
                    }

                with _last_good_responses_lock:
                    proxystats["mem_cache"]["degradation_cache"] = {
                        "entries": len(_last_good_responses),
                        "size_bytes": sys.getsizeof(_last_good_responses) + sum(
                            sys.getsizeof(k) + sys.getsizeof(v) + sys.getsizeof(v[0]) + sys.getsizeof(v[1])
                            for k, v in _last_good_responses.items()
                        ),
                    }

                with _performance_cache_lock:
                    proxystats["mem_cache"]["performance_cache"] = {
                        "entries": len(_performance_cache),
                        "size_bytes": sys.getsizeof(_performance_cache) + sum(
                            sys.getsizeof(k) + sys.getsizeof(v) + sys.getsizeof(v[0]) + sys.getsizeof(v[1])
                            for k, v in _performance_cache.items()
                        ),
                    }

                with _endpoint_stats_lock:
                    proxystats["mem_cache"]["endpoint_stats"] = {
                        "entries": len(_endpoint_stats),
                        "size_bytes": sys.getsizeof(_endpoint_stats) + sum(
                            sys.getsizeof(k) + sys.getsizeof(v) + sum(
                                sys.getsizeof(ek) + sys.getsizeof(ev)
                                for ek, ev in v.items()
                            ) for k, v in _endpoint_stats.items()
                        ),
                    }

                # Add total cache memory usage
                total_cache_bytes = sum(
                    cache_info["size_bytes"] for cache_info in proxystats["mem_cache"].values()
                )
                proxystats["mem_cache"]["total_cache_bytes"] = total_cache_bytes
                proxystats["mem_cache"]["total_cache_mb"] = round(total_cache_bytes / 1024 / 1024, 2)

                message: str = json.dumps(proxystats)
        elif request_path == "/stats/clear":
            # Clear Internal Stats
            log.debug("Clear internal stats")
            with proxystats_lock:
                proxystats["gets"] = 0
                proxystats["errors"] = 0
                proxystats["uri"] = {}
                proxystats["clear"] = int(time.time())
            message: str = json.dumps(proxystats)
        elif request_path == "/health":
            # Connection Health and Cache Status
            health_info = {
                "pypowerwall": "%s Proxy %s" % (pypowerwall.version, BUILD),
                "mode": proxystats.get("mode", "Unknown"),
                "tedapi_mode": proxystats.get("tedapi_mode", "off"),
                "pypowerwall_cache_expire": cache_expire,
                "degradation_cache_ttl_seconds": degradation_cache_ttl_seconds,
                "graceful_degradation": graceful_degradation,
                "fail_fast_mode": fail_fast_mode,
                "health_check_enabled": health_check_enabled,
                "startup_time": datetime.datetime.fromtimestamp(
                    proxystats["start"]
                ).isoformat(),
                "current_time": datetime.datetime.now().isoformat(),
            }

            # Add transport status for v1r/hybrid modes
            health_info["transports"] = get_transport_health()

            # Add overall proxy response counters
            with proxystats_lock:
                health_info["proxy_stats"] = {
                    "total_gets": proxystats["gets"],
                    "total_posts": proxystats["posts"],
                    "total_errors": proxystats["errors"],
                    "total_timeouts": proxystats["timeout"],
                }

            if health_check_enabled:
                with _connection_health_lock:
                    health_info["connection_health"] = {
                        "consecutive_failures": _connection_health[
                            "consecutive_failures"
                        ],
                        "total_failures": _connection_health["total_failures"],
                        "total_successes": _connection_health["total_successes"],
                        "is_degraded": _connection_health["is_degraded"],
                        "last_success_time": _connection_health["last_success_time"],
                        "last_success_age_seconds": time.time()
                        - _connection_health["last_success_time"],
                    }

            # SolarOnly fallback mode state (separate from connection_health degradation)
            with _fallback_mode_lock:
                fm = dict(_fallback_mode)
            health_info["fallback_mode"] = {
                "is_fallback_mode": fm["is_fallback_mode"],
                "fallback_since": fm["fallback_since"],
                "fallback_duration_seconds": (
                    round(time.time() - fm["fallback_since"], 1)
                    if fm["fallback_since"] else None
                ),
                "recovery_attempts": fm["recovery_attempts"],
                "last_recovery_attempt": fm["last_recovery_attempt"],
                "recovery_enabled": tedapi_recovery_enabled,
            }

            if graceful_degradation:
                with _last_good_responses_lock:
                    cached_endpoints = {}
                    current_time = time.time()
                    for endpoint, (data, timestamp) in _last_good_responses.items():
                        age = current_time - timestamp
                        cached_endpoints[endpoint] = {
                            "age_seconds": age,
                            "is_expired": age >= degradation_cache_ttl_seconds,
                        }
                    health_info["cached_data"] = {
                        "cache_size": len(_last_good_responses),
                        "endpoints": cached_endpoints,
                    }

            # Add endpoint call statistics
            with _endpoint_stats_lock:
                endpoint_stats = {}
                current_time = time.time()
                for endpoint, stats in _endpoint_stats.items():
                    success_rate = (
                        (stats["successful_calls"] / stats["total_calls"] * 100)
                        if stats["total_calls"] > 0
                        else 0
                    )
                    endpoint_info = {
                        "total_calls": stats["total_calls"],
                        "successful_calls": stats["successful_calls"],
                        "failed_calls": stats["failed_calls"],
                        "success_rate_percent": round(success_rate, 2),
                    }

                    if stats["last_success_time"]:
                        endpoint_info["last_success_age_seconds"] = (
                            current_time - stats["last_success_time"]
                        )
                    if stats["last_failure_time"]:
                        endpoint_info["last_failure_age_seconds"] = (
                            current_time - stats["last_failure_time"]
                        )

                    endpoint_stats[endpoint] = endpoint_info

                if endpoint_stats:
                    health_info["endpoint_statistics"] = endpoint_stats

            message: str = json.dumps(health_info)
        elif request_path == "/health/reset":
            # Reset Health Counters and Clear Cache
            cache_size_before = 0

            if health_check_enabled:
                with _connection_health_lock:
                    _connection_health["consecutive_failures"] = 0
                    _connection_health["total_failures"] = 0
                    _connection_health["total_successes"] = 0
                    _connection_health["is_degraded"] = False
                    _connection_health["last_success_time"] = time.time()

            # Reset SolarOnly fallback mode state
            with _fallback_mode_lock:
                _fallback_mode["is_fallback_mode"] = False
                _fallback_mode["fallback_since"] = None
                _fallback_mode["recovery_attempts"] = 0
                _fallback_mode["last_recovery_attempt"] = None

            if graceful_degradation:
                with _last_good_responses_lock:
                    cache_size_before = len(_last_good_responses)
                    _last_good_responses.clear()

            # Reset endpoint statistics
            endpoint_stats_count = 0
            with _endpoint_stats_lock:
                endpoint_stats_count = len(_endpoint_stats)
                _endpoint_stats.clear()

            log.info(
                "Health counters, cache, and endpoint statistics reset via /health/reset endpoint"
            )
            message: str = json.dumps(
                {
                    "status": "reset_complete",
                    "health_counters_reset": health_check_enabled,
                    "cache_cleared": graceful_degradation,
                    "cache_entries_removed": cache_size_before
                    if graceful_degradation
                    else 0,
                    "endpoint_stats_cleared": endpoint_stats_count,
                }
            )
        elif request_path == "/temps":
            # Temps of Powerwalls
            message: str = safe_pw_call(pw.temps, jsonformat=True) or json.dumps({})
        elif request_path == "/temps/pw":
            # Temps of Powerwalls with Simple Keys
            def generate_temps_pw():
                pwtemp = {}
                idx = 1
                temps = safe_pw_call(pw.temps)
                if temps:
                    for i in temps:
                        key = "PW%d_temp" % idx
                        pwtemp[key] = temps[i]
                        idx = idx + 1
                return json.dumps(pwtemp)

            message = cached_route_handler("/temps/pw", generate_temps_pw)
        elif request_path == "/alerts":
            # Alerts
            message: str = safe_pw_call(pw.alerts, jsonformat=True) or json.dumps([])
        elif request_path == "/alerts/pw":
            # Alerts in dictionary/object format
            def generate_alerts_pw():
                pwalerts = {}
                alerts = safe_pw_call(pw.alerts)
                if alerts is None:
                    return None
                else:
                    for alert in alerts:
                        pwalerts[alert] = 1
                    return json.dumps(pwalerts) or json.dumps({})

            message = cached_route_handler("/alerts/pw", generate_alerts_pw)
        elif request_path == "/freq":
            # Frequency, Current, Voltage and Grid Status
            def generate_freq():
                fcv = {}
                idx = 1
                # Pull freq, current, voltage of each Powerwall via system_status
                d = safe_pw_call(pw.system_status) or {}
                if "battery_blocks" in d:
                    for block in d["battery_blocks"]:
                        fcv["PW%d_name" % idx] = None  # Placeholder for vitals
                        fcv["PW%d_PINV_Fout" % idx] = get_value(block, "f_out")
                        fcv["PW%d_PINV_VSplit1" % idx] = None  # Placeholder for vitals
                        fcv["PW%d_PINV_VSplit2" % idx] = None  # Placeholder for vitals
                        fcv["PW%d_PackagePartNumber" % idx] = get_value(
                            block, "PackagePartNumber"
                        )
                        fcv["PW%d_PackageSerialNumber" % idx] = get_value(
                            block, "PackageSerialNumber"
                        )
                        fcv["PW%d_p_out" % idx] = get_value(block, "p_out")
                        fcv["PW%d_q_out" % idx] = get_value(block, "q_out")
                        fcv["PW%d_v_out" % idx] = get_value(block, "v_out")
                        fcv["PW%d_f_out" % idx] = get_value(block, "f_out")
                        fcv["PW%d_i_out" % idx] = get_value(block, "i_out")
                        idx = idx + 1
                # Pull freq, current, voltage of each Powerwall via vitals if available
                vitals = safe_pw_call(pw.vitals) or {}
                idx = 1
                for device in vitals:
                    d = vitals[device]
                    if device.startswith("TEPINV"):
                        # PW freq
                        fcv["PW%d_name" % idx] = device
                        fcv["PW%d_PINV_Fout" % idx] = get_value(d, "PINV_Fout")
                        fcv["PW%d_PINV_VSplit1" % idx] = get_value(d, "PINV_VSplit1")
                        fcv["PW%d_PINV_VSplit2" % idx] = get_value(d, "PINV_VSplit2")
                        idx = idx + 1
                    if device.startswith("TESYNC") or device.startswith("TEMSA"):
                        # Island and Meter Metrics from Backup Gateway or Backup Switch
                        for i in d:
                            if i.startswith("ISLAND") or i.startswith("METER"):
                                fcv[i] = d[i]
                fcv["grid_status"] = safe_pw_call(pw.grid_status, "numeric")
                return json.dumps(fcv)

            message = cached_route_handler("/freq", generate_freq)
        elif request_path == "/pod":
            # Powerwall Battery Data
            def generate_pod():
                pod = {}
                # Get Individual Powerwall Battery Data
                d = safe_pw_call(pw.system_status) or {}
                if "battery_blocks" in d:
                    idx = 1
                    for block in d["battery_blocks"]:
                        # Vital Placeholders
                        pod["PW%d_name" % idx] = None
                        pod["PW%d_POD_ActiveHeating" % idx] = None
                        pod["PW%d_POD_ChargeComplete" % idx] = None
                        pod["PW%d_POD_ChargeRequest" % idx] = None
                        pod["PW%d_POD_DischargeComplete" % idx] = None
                        pod["PW%d_POD_PermanentlyFaulted" % idx] = None
                        pod["PW%d_POD_PersistentlyFaulted" % idx] = None
                        pod["PW%d_POD_enable_line" % idx] = None
                        pod["PW%d_POD_available_charge_power" % idx] = None
                        pod["PW%d_POD_available_dischg_power" % idx] = None
                        pod["PW%d_POD_nom_energy_remaining" % idx] = None
                        pod["PW%d_POD_nom_energy_to_be_charged" % idx] = None
                        pod["PW%d_POD_nom_full_pack_energy" % idx] = None
                        # Additional System Status Data
                        pod["PW%d_POD_nom_energy_remaining" % idx] = get_value(
                            block, "nominal_energy_remaining"
                        )  # map
                        pod["PW%d_POD_nom_full_pack_energy" % idx] = get_value(
                            block, "nominal_full_pack_energy"
                        )  # map
                        pod["PW%d_PackagePartNumber" % idx] = get_value(
                            block, "PackagePartNumber"
                        )
                        pod["PW%d_PackageSerialNumber" % idx] = get_value(
                            block, "PackageSerialNumber"
                        )
                        pod["PW%d_pinv_state" % idx] = get_value(block, "pinv_state")
                        pod["PW%d_pinv_grid_state" % idx] = get_value(
                            block, "pinv_grid_state"
                        )
                        pod["PW%d_p_out" % idx] = get_value(block, "p_out")
                        pod["PW%d_q_out" % idx] = get_value(block, "q_out")
                        pod["PW%d_v_out" % idx] = get_value(block, "v_out")
                        pod["PW%d_f_out" % idx] = get_value(block, "f_out")
                        pod["PW%d_i_out" % idx] = get_value(block, "i_out")
                        pod["PW%d_energy_charged" % idx] = get_value(
                            block, "energy_charged"
                        )
                        pod["PW%d_energy_discharged" % idx] = get_value(
                            block, "energy_discharged"
                        )
                        pod["PW%d_off_grid" % idx] = int(get_value(block, "off_grid") or 0)
                        pod["PW%d_vf_mode" % idx] = int(get_value(block, "vf_mode") or 0)
                        pod["PW%d_wobble_detected" % idx] = int(
                            get_value(block, "wobble_detected") or 0
                        )
                        pod["PW%d_charge_power_clamped" % idx] = int(
                            get_value(block, "charge_power_clamped") or 0
                        )
                        pod["PW%d_backup_ready" % idx] = int(
                            get_value(block, "backup_ready") or 0
                        )
                        pod["PW%d_OpSeqState" % idx] = get_value(block, "OpSeqState")
                        pod["PW%d_version" % idx] = get_value(block, "version")
                        idx = idx + 1
                # Augment with Vitals Data if available
                vitals = safe_pw_call(pw.vitals) or {}
                idx = 1
                for device in vitals:
                    v = vitals[device]
                    if device.startswith("TEPOD"):
                        pod["PW%d_name" % idx] = device
                        pod["PW%d_POD_ActiveHeating" % idx] = int(
                            get_value(v, "POD_ActiveHeating") or 0
                        )
                        pod["PW%d_POD_ChargeComplete" % idx] = int(
                            get_value(v, "POD_ChargeComplete") or 0
                        )
                        pod["PW%d_POD_ChargeRequest" % idx] = int(
                            get_value(v, "POD_ChargeRequest") or 0
                        )
                        pod["PW%d_POD_DischargeComplete" % idx] = int(
                            get_value(v, "POD_DischargeComplete") or 0
                        )
                        pod["PW%d_POD_PermanentlyFaulted" % idx] = int(
                            get_value(v, "POD_PermanentlyFaulted") or 0
                        )
                        pod["PW%d_POD_PersistentlyFaulted" % idx] = int(
                            get_value(v, "POD_PersistentlyFaulted") or 0
                        )
                        pod["PW%d_POD_enable_line" % idx] = int(
                            get_value(v, "POD_enable_line") or 0
                        )
                        pod["PW%d_POD_available_charge_power" % idx] = get_value(
                            v, "POD_available_charge_power"
                        )
                        pod["PW%d_POD_available_dischg_power" % idx] = get_value(
                            v, "POD_available_dischg_power"
                        )
                        pod["PW%d_POD_nom_energy_remaining" % idx] = get_value(
                            v, "POD_nom_energy_remaining"
                        )
                        pod["PW%d_POD_nom_energy_to_be_charged" % idx] = get_value(
                            v, "POD_nom_energy_to_be_charged"
                        )
                        pod["PW%d_POD_nom_full_pack_energy" % idx] = get_value(
                            v, "POD_nom_full_pack_energy"
                        )
                        idx = idx + 1
                # Note: Expansion packs are now included in vitals() as TEPOD entries,
                # so they're automatically picked up by the loop above.
                # Aggregate data
                pod["nominal_full_pack_energy"] = get_value(d, "nominal_full_pack_energy")
                pod["nominal_energy_remaining"] = get_value(d, "nominal_energy_remaining")
                pod["time_remaining_hours"] = safe_pw_call(pw.get_time_remaining)
                pod["backup_reserve_percent"] = safe_pw_call(pw.get_reserve)
                return json.dumps(pod)

            message = cached_route_handler("/pod", generate_pod)
        elif request_path == "/json":
            # JSON - Grid,Home,Solar,Battery,Level,GridStatus,Reserve,TimeRemaining,FullEnergy,RemainingEnergy,Strings
            def generate_json():
                # Optimization: Use single aggregates call for all power values (like CSV endpoint)
                aggregates = safe_endpoint_call("/aggregates", pw.poll, "/api/meters/aggregates", jsonformat=False)
                if aggregates:
                    grid = aggregates.get('site', {}).get('instant_power', 0)
                    solar = aggregates.get('solar', {}).get('instant_power', 0)
                    battery = aggregates.get('battery', {}).get('instant_power', 0)
                    home = aggregates.get('load', {}).get('instant_power', 0)
                else:
                    grid = solar = battery = home = None

                # Apply negative solar correction if configured
                if not neg_solar and solar is not None and solar < 0:
                    # Shift energy from solar to load
                    home -= solar
                    solar = 0

                # Apply site zero threshold - suppress phantom grid noise
                # Pass through None values — they indicate a data gap, not zero
                if site_zero_threshold > 0 and grid is not None and abs(grid) <= site_zero_threshold:
                    grid = 0

                # Convert None to 0 for output (None = data gap, output as 0)
                grid = grid or 0
                solar = solar or 0
                battery = battery or 0
                home = home or 0

                # Get remaining data
                d = safe_pw_call(pw.system_status) or {}
                values = {
                    "grid": grid,
                    "home": home,
                    "solar": solar,
                    "battery": battery,
                    "soe": safe_pw_call(pw.level) or 0,
                    "grid_status": int(safe_pw_call(pw.grid_status) == "UP"),
                    "reserve": safe_pw_call(pw.get_reserve) or 0,
                    "time_remaining_hours": safe_pw_call(pw.get_time_remaining) or 0,
                    "full_pack_energy": get_value(d, "nominal_full_pack_energy") or 0,
                    "energy_remaining": get_value(d, "nominal_energy_remaining") or 0,
                    "strings": safe_pw_call(pw.strings, jsonformat=False) or {},
                }
                return json.dumps(values)

            message = cached_route_handler("/json", generate_json)
        elif request_path == "/version":
            # Firmware Version
            version = safe_pw_call(pw.version)
            v = {}
            if version is None:
                v["version"] = "SolarOnly"
                v["vint"] = 0
                message: str = json.dumps(v)
            else:
                v["version"] = version
                v["vint"] = parse_version(version)
                message: str = json.dumps(v)
        elif request_path == "/help":
            # Display friendly help screen link and stats
            # Slow work (network call, rusage) happens before taking the lock
            help_site_name = safe_pw_call(pw.site_name)
            help_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            with proxystats_lock:
                proxystats["ts"] = int(time.time())
                delta = proxystats["ts"] - proxystats["start"]
                proxystats["uptime"] = str(datetime.timedelta(seconds=delta))
                proxystats["mem"] = help_mem
                proxystats["site_name"] = help_site_name
                proxystats["cloudmode"] = pw.cloudmode
                proxystats["fleetapi"] = pw.fleetapi
                if (pw.cloudmode or pw.fleetapi) and pw.client is not None:
                    proxystats["siteid"] = pw.client.siteid
                    proxystats["counter"] = pw.client.counter
                proxystats["authmode"] = pw.authmode
            contenttype = "text/html"
            message: str = """
            <html>\n<head><meta http-equiv="refresh" content="5" />\n
            <style>p, td, th { font-family: Helvetica, Arial, sans-serif; font-size: 10px;}</style>\n
            <style>h1 { font-family: Helvetica, Arial, sans-serif; font-size: 20px;}</style>\n
            </head>\n<body>\n<h1>pyPowerwall [%VER%] Proxy [%BUILD%] </h1>\n\n
            <p><a href="https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md">
            Click here for API help.</a></p>\n\n
            <table>\n<tr><th align ="left">Stat</th><th align ="left">Value</th></tr>
            """
            message = message.replace("%VER%", pypowerwall.version).replace(
                "%BUILD%", BUILD
            )
            with proxystats_lock:
                # html.escape() everything interpolated into the page - URI keys
                # are attacker-controlled request paths (stored XSS vector)
                for i in proxystats:
                    if i != "uri" and i != "config":
                        message += f'<tr><td align="left">{html.escape(str(i))}</td><td align ="left">{html.escape(str(proxystats[i]))}</td></tr>\n'
                for i in proxystats["uri"]:
                    message += f'<tr><td align="left">URI: {html.escape(str(i))}</td><td align ="left">{html.escape(str(proxystats["uri"][i]))}</td></tr>\n'
            message += """
            <tr>
                <td align="left">Config:</td>
                <td align="left">
                    <details id="config-details">
                        <summary>Click to view</summary>
                        <table>
            """
            with proxystats_lock:
                for i in proxystats["config"]:
                    message += f'<tr><td align="left">{html.escape(str(i))}</td><td align ="left">{html.escape(str(proxystats["config"][i]))}</td></tr>\n'
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
            message += f"\n<p>Page refresh: {str(datetime.datetime.fromtimestamp(time.time()))}</p>\n</body>\n</html>"
        elif request_path == "/api/troubleshooting/problems":
            # Simulate old API call and respond with empty list
            message = '{"problems": []}'
            # message = pw.poll('/api/troubleshooting/problems') or '{"problems": []}'
        elif request_path.startswith("/tedapi"):
            # TEDAPI Specific Calls
            if pw.tedapi:
                message = '{"error": "Use /tedapi/config, /tedapi/status, /tedapi/components, /tedapi/battery, /tedapi/controller"}'
                if request_path == "/tedapi/config":
                    message = json.dumps(safe_pw_call(pw.tedapi.get_config))
                if request_path == "/tedapi/status":
                    message = json.dumps(safe_pw_call(pw.tedapi.get_status))
                if request_path == "/tedapi/components":
                    message = json.dumps(safe_pw_call(pw.tedapi.get_components))
                if request_path == "/tedapi/battery":
                    message = json.dumps(safe_pw_call(pw.tedapi.get_battery_blocks))
                if request_path == "/tedapi/controller":
                    message = json.dumps(safe_pw_call(pw.tedapi.get_device_controller))
            else:
                message = '{"error": "TEDAPI not enabled"}'
        elif request_path.startswith("/cloud"):
            # Cloud API Specific Calls - pw.client can be None if connect() failed,
            # so guard before dereferencing (safe_pw_call can't catch that)
            if pw.cloudmode and not pw.fleetapi and pw.client is not None:
                message = '{"error": "Use /cloud/battery, /cloud/power, /cloud/config"}'
                if request_path == "/cloud/battery":
                    message = json.dumps(safe_pw_call(pw.client.get_battery))
                if request_path == "/cloud/power":
                    message = json.dumps(safe_pw_call(pw.client.get_site_power))
                if request_path == "/cloud/config":
                    message = json.dumps(safe_pw_call(pw.client.get_site_config))
            else:
                message = '{"error": "Cloud API not enabled"}'
        elif request_path.startswith("/fleetapi"):
            # FleetAPI Specific Calls - guard pw.client like the /cloud routes
            if pw.fleetapi and pw.client is not None:
                message = '{"error": "Use /fleetapi/info, /fleetapi/status"}'
                if request_path == "/fleetapi/info":
                    message = json.dumps(safe_pw_call(pw.client.get_site_info))
                if request_path == "/fleetapi/status":
                    message = json.dumps(safe_pw_call(pw.client.get_live_status))
            else:
                message = '{"error": "FleetAPI not enabled"}'
        elif urlparse(request_path).path in DISABLED:
            # Disabled API Calls - match on path only so a query string
            # (e.g. ?x=1) cannot be used to bypass the block
            message = '{"status": "404 Response - API Disabled"}'
        elif urlparse(request_path).path in ALLOWLIST:
            # Allowed API Calls - Proxy to Powerwall (query string stripped)
            message: str = safe_pw_call(pw.poll, urlparse(request_path).path, jsonformat=True)
        elif request_path.startswith("/control/reserve"):
            # Current battery reserve level
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"reserve": %s}' % (
                    safe_pw_call(pw_control.get_reserve) or 0
                )
        elif request_path.startswith("/control/mode"):
            # Current operating mode
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"mode": "%s"}' % (
                    safe_pw_call(pw_control.get_mode) or "unknown"
                )
        elif request_path.startswith("/control/grid_charging"):
            # Current grid charging state
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"grid_charging": %s}' % (
                    "true" if safe_pw_call(pw_control.get_grid_charging) else "false"
                )
        elif request_path.startswith("/control/grid_export"):
            # Current grid export state
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                # battery_ok, pv_only, and never
                message = '{"grid_export": "%s"}' % (
                    safe_pw_call(pw_control.get_grid_export) or "unknown"
                )
        elif request_path.startswith("/control/max_backup"):
            # Current backup events (requires v1r)
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            elif not pw.tedapi or not pw.tedapi.v1r:
                message = '{"error": "max_backup requires v1r LAN transport"}'
            else:
                result = safe_pw_call(pw.tedapi.get_backup_events)
                if result is not None:
                    # Auto-cancel expired events (gateway leaves them lingering).
                    # Cancel is a *write*, so it requires a valid control token
                    # (?token=<PW_CONTROL_SECRET>); a plain GET stays read-only.
                    mb = result.get('manual_backup')
                    if mb and not mb.get('active'):
                        token = parse_qs(urlparse(request_path).query).get("token", [""])[0]
                        if token and control_secret and hmac.compare_digest(token, control_secret):
                            safe_pw_call(pw.tedapi.cancel_max_backup)
                            result['manual_backup'] = None
                    message = json.dumps(result)
                else:
                    message = '{"error": "Failed to get backup events"}'
        elif request_path == "/fans":
            # Fan speeds in raw format
            message = json.dumps(
                safe_pw_call(pw.tedapi.get_fan_speeds) if pw.tedapi else {}
            )
        elif request_path.startswith("/fans/pw"):
            # Fan speeds in simplified format (e.g. FAN1_actual, FAN1_target)
            if pw.tedapi:
                fans = {}
                fan_speeds = safe_pw_call(pw.tedapi.get_fan_speeds) or {}
                for i, (_, value) in enumerate(sorted(fan_speeds.items())):
                    key = f"FAN{i+1}"
                    fans[f"{key}_actual"] = value.get("PVAC_Fan_Speed_Actual_RPM")
                    fans[f"{key}_target"] = value.get("PVAC_Fan_Speed_Target_RPM")
                message = json.dumps(fans)
            else:
                message = "{}"
        elif self.path.startswith("/pw/"):
            # Map library functions into /pw/ API calls
            path = self.path[4:]  # Remove '/pw/' prefix
            simple_mappings = {
                "level": lambda: {"level": safe_pw_call(pw.level)},
                "power": lambda: safe_pw_call(pw.power),
                "site": lambda: safe_pw_call(pw.site, True),
                "solar": lambda: safe_pw_call(pw.solar, True),
                "battery": lambda: safe_pw_call(pw.battery, True),
                "battery_blocks": lambda: safe_pw_call(pw.battery_blocks),
                "load": lambda: safe_pw_call(pw.load, True),
                "grid": lambda: safe_pw_call(pw.grid, True),
                "home": lambda: safe_pw_call(pw.home, True),
                "vitals": lambda: safe_pw_call(pw.vitals),
                "temps": lambda: safe_pw_call(pw.temps),
                "strings": lambda: safe_pw_call(pw.strings, False, True),
                "din": lambda: {"din": safe_pw_call(pw.din)},
                "uptime": lambda: {"uptime": safe_pw_call(pw.uptime)},
                "version": lambda: {"version": safe_pw_call(pw.version)},
                "status": lambda: safe_pw_call(pw.status),
                "system_status": lambda: safe_pw_call(pw.system_status, False),
                "grid_status": lambda: json.loads(
                    safe_pw_call(pw.grid_status, "json") or "{}"
                ),
                "aggregates": lambda: safe_pw_call(
                    pw.poll, "/api/meters/aggregates", False
                ),
                "site_name": lambda: {"site_name": safe_pw_call(pw.site_name)},
                "alerts": lambda: {"alerts": safe_pw_call(pw.alerts)},
                "is_connected": lambda: {"is_connected": safe_pw_call(pw.is_connected)},
                "get_reserve": lambda: {"reserve": safe_pw_call(pw.get_reserve)},
                "get_mode": lambda: {"mode": safe_pw_call(pw.get_mode)},
                "get_time_remaining": lambda: {
                    "time_remaining": safe_pw_call(pw.get_time_remaining)
                },
            }
            # Check if the path is in the simple mappings
            if path in simple_mappings:
                result = simple_mappings[path]()
            else:
                result = {"error": "Invalid Request"}
            message = json.dumps(result)
        else:
            # Everything else - Set auth headers required for web application
            proxystats["gets"] = proxystats["gets"] + 1
            if pw.authmode == "token":
                # Create bogus cookies
                self.send_header("Set-Cookie", f"AuthCookie=1234567890;{cookiesuffix}")
                self.send_header("Set-Cookie", f"UserRecord=1234567890;{cookiesuffix}")
            else:
                # Safely access auth cookies with fallback - pw.client can be
                # None if backend init failed, so guard before touching .auth
                client_auth = pw.client.auth if pw.client is not None else None
                auth_cookie = (
                    client_auth.get("AuthCookie", "1234567890")
                    if client_auth
                    else "1234567890"
                )
                user_record = (
                    client_auth.get("UserRecord", "1234567890")
                    if client_auth
                    else "1234567890"
                )
                self.send_header(
                    "Set-Cookie", f"AuthCookie={auth_cookie};{cookiesuffix}"
                )
                self.send_header(
                    "Set-Cookie", f"UserRecord={user_record};{cookiesuffix}"
                )

            # Serve static assets from web root first, if found.
            # pylint: disable=attribute-defined-outside-init
            if request_path == "/" or request_path == "":
                request_path = "/index.html"
                fcontent, ftype = get_static(web_root, request_path)
                # Replace {VARS} with current data
                status = safe_pw_call(pw.status) or {}
                # convert fcontent to string
                fcontent = fcontent.decode("utf-8")
                # fix the following variables that if they are None, return ""
                fcontent = fcontent.replace(
                    "{VERSION}", status.get("version", "") or ""
                )
                fcontent = fcontent.replace("{HASH}", status.get("git_hash", "") or "")
                fcontent = fcontent.replace("{EMAIL}", email)

                static_asset_prefix = (
                    api_base_url + "viz-static/"
                )  # prefix for static files so they can be detected by a reverse proxy easily
                fcontent = fcontent.replace("{STYLE}", static_asset_prefix + style)
                fcontent = fcontent.replace("{ASSET_PREFIX}", static_asset_prefix)

                fcontent = fcontent.replace("{API_BASE_URL}", api_base_url + "api")
                # convert fcontent back to bytes
                fcontent = bytes(fcontent, "utf-8")
            else:
                fcontent, ftype = get_static(web_root, request_path)
            if fcontent:
                log.debug(
                    "Served from local web root: {} type {}".format(request_path, ftype)
                )
            # If not found, serve from Powerwall web server
            elif pw.cloudmode or pw.fleetapi:
                log.debug("Cloud Mode - File not found: {}".format(request_path))
                fcontent = bytes("Not Found", "utf-8")
                ftype = "text/plain"
            elif urlparse(request_path).path.startswith("/api/"):
                # Never proxy unmatched /api/ paths to the gateway - only
                # ALLOWLIST endpoints may reach the gateway API with the
                # proxy's credentials attached (open-proxy prevention).
                log.debug("API not allowed: {}".format(request_path))
                fcontent = bytes("Not Found", "utf-8")
                ftype = "text/plain"
            else:
                # Proxy request to Powerwall web server (web app assets).
                proxy_path = request_path
                if proxy_path.startswith("/"):
                    proxy_path = proxy_path[1:]
                pw_url = "https://{}/{}".format(pw.host, proxy_path)
                log.debug("Proxy request to: {}".format(pw_url))
                try:
                    if pw.authmode == "token":
                        r = pw.client.session.get(
                            url=pw_url,
                            headers=pw.auth,
                            verify=False,
                            stream=True,
                            timeout=pw.timeout,
                        )
                    else:
                        r = pw.client.session.get(
                            url=pw_url,
                            cookies=pw.auth,
                            verify=False,
                            stream=True,
                            timeout=pw.timeout,
                        )
                    fcontent = r.content
                    ftype = r.headers.get("content-type", "text/plain")
                except (AttributeError, requests.exceptions.RequestException) as exc:
                    # Gateway unreachable, timed out, or session unavailable -
                    # fall through and serve the standard "Not Found" body
                    log.debug("Unable to fetch {} from gateway: {}".format(request_path, exc))
                    fcontent = bytes("Not Found", "utf-8")
                    ftype = "text/plain"

            # Allow browser caching, if user permits, only for CSS, JavaScript and PNG images...
            if browser_cache > 0 and (
                ftype == "text/css"
                or ftype == "application/javascript"
                or ftype == "image/png"
            ):
                self.send_header("Cache-Control", "max-age={}".format(browser_cache))
            else:
                self.send_header("Cache-Control", "no-cache, no-store")

                # Inject transformations
            if request_path.split("?")[0] == "/":
                if os.path.exists(os.path.join(web_root, style)):
                    fcontent = bytes(inject_js(fcontent, style), "utf-8")

            self.send_header("Content-type", "{}".format(ftype))
            self.end_headers()
            try:
                self.wfile.write(fcontent)
            except Exception as exc:
                if "Broken pipe" in str(exc):
                    log.debug(f"Client disconnected before payload sent [doGET]: {exc}")
                    return
                log.error(
                    f"Error occured while sending PROXY response to client [doGET]: {exc}"
                )
            return

        # Count
        if message is None:
            with proxystats_lock:
                proxystats["timeout"] = proxystats["timeout"] + 1
            # Return null/empty response instead of timeout message for API endpoints
            if request_path.startswith("/api/") or request_path in [
                "/aggregates",
                "/soe",
                "/vitals",
                "/strings",
            ]:
                message = "null"  # JSON null for API endpoints
            else:
                message = "TIMEOUT!"
        elif message == "ERROR!":
            with proxystats_lock:
                proxystats["errors"] = proxystats["errors"] + 1
            message = "ERROR!"
        else:
            # Count by query-stripped path so unique querystring URLs cannot
            # grow proxystats["uri"] without bound
            uri_key = urlparse(request_path).path
            with proxystats_lock:
                proxystats["gets"] = proxystats["gets"] + 1
                if uri_key not in proxystats["uri"] and len(proxystats["uri"]) >= URI_STATS_MAX:
                    # Cap reached - aggregate new distinct paths under "other"
                    uri_key = "other"
                proxystats["uri"][uri_key] = proxystats["uri"].get(uri_key, 0) + 1

        # Send headers and payload
        try:
            # Encode once - Content-Length must count bytes, not characters
            body = message.encode("utf8")
            self.send_header("Content-type", contenttype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            log.debug(f"Socket broken sending API response to client [doGET]: {exc}")

# noinspection PyTypeChecker
def main() -> None:
    with ThreadingHTTPServer((bind_address, port), Handler) as server:
        if https_mode == "yes":
            # Activate HTTPS
            log.debug("Activating HTTPS")
            # ssl.wrap_socket() was removed in Python 3.12 - use SSLContext instead
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(
                os.path.join(os.path.dirname(__file__), "localhost.pem")
            )
            server.socket = ctx.wrap_socket(server.socket, server_side=True)

        # noinspection PyBroadException
        try:
            server.serve_forever()
        except (Exception, KeyboardInterrupt, SystemExit):
            print(" CANCEL \n")

        log.info("pyPowerwall Proxy Stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()

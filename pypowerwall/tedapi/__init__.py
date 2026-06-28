# pyPowerWall - Tesla TEDAPI Class
# -*- coding: utf-8 -*-
"""
 Tesla TEADAPI Class

 This module allows you to access the Tesla Powerwall Gateway
 TEDAPI on 192.168.91.1 as used by the Tesla One app.

 Class:
    TEDAPI(gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
              pwconfigexpire: int = 5, host: str = GW_IP) - Initialize TEDAPI

 Parameters:
    gw_pwd - Powerwall Gateway Password
    debug - Enable Debug Output
    pwcacheexpire - Cache Expiration in seconds
    timeout - API Timeout in seconds
    pwconfigexpire - Configuration Cache Expiration in seconds
    host - Powerwall Gateway IP Address (default: 192.168.91.1)

 Functions:
    get_din() - Get the DIN from the Powerwall Gateway
    get_config() - Get the Powerwall Gateway Configuration
    get_status() - Get the Powerwall Gateway Status
    connect() - Connect to the Powerwall Gateway
    backup_time_remaining() - Get the time remaining in hours
    battery_level() - Get the battery level as a percentage
    vitals() - Use tedapi data to create a vitals dictionary
    get_firmware_version() - Get the Powerwall Firmware Version
    get_battery_blocks() - Get list of Powerwall Battery Blocks
    get_components() - Get the Powerwall 3 Device Information
    get_battery_block(din) - Get the Powerwall 3 Battery Block Information
    get_pw3_vitals() - Get the Powerwall 3 Vitals Information
    get_device_controller() - Get the Powerwall Device Controller Status
    get_fan_speed() - Get the fan speeds in RPM

 Note:
    This module requires access to the Powerwall Gateway. You can add a route to
    using the command: sudo route add -host 192.168.91.1 <Powerwall_IP>
    The Powerwall Gateway password is required to access the TEDAPI.

 Author: Jason A. Cox
 Date: 1 Jun 2024
 For more information see https://github.com/jasonacox/pypowerwall
"""
# Lazy annotations so PEP 604 syntax (e.g. `str | None`) in signatures is not
# evaluated at runtime — keeps import working on Python < 3.10.
from __future__ import annotations

import gzip
import json
import logging
import math
import sys
import threading
import time
from functools import wraps
from http import HTTPStatus
from typing import Any, Dict, Final, List, Optional, Tuple, Union

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning

from pypowerwall import __version__
from pypowerwall.api_lock import acquire_lock_with_backoff
from pypowerwall.helpers import lookup

from .protobuf.june_2024 import tedapi_pb2
from .protobuf.june_2024 import tedapi_combined_pb2 as combined_pb2
from .api_version import TEDAPIApiVersion
from .queries import apply_query, get_query

urllib3.disable_warnings(InsecureRequestWarning)

# TEDAPI Fixed Gateway IP Address
GW_IP = "192.168.91.1"

# Rate Limit Codes
BUSY_CODES: Final[List[HTTPStatus]] = [HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE]
RETRY_FORCE_CODES: Final[List[int]] = [int(i) for i in [
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.GATEWAY_TIMEOUT,
    HTTPStatus.INTERNAL_SERVER_ERROR,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.TOO_MANY_REQUESTS
]]

# Setup Logging
log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

# Utility Functions
# lookup() is imported (and re-exported) from pypowerwall.helpers - the
# shared None-safe implementation used by all backends

def uses_api_lock(func):
    # If the attribute doesn't exist or isn't a valid threading.Lock, overwrite it.
    if not hasattr(func, 'api_lock') or not isinstance(func.api_lock, type(threading.Lock)):
        func.api_lock = threading.Lock()
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Inject the function object itself into kwargs.
        kwargs['self_function'] = func
        return func(*args, **kwargs)
    return wrapper

def decompress_response(content: bytes) -> bytes:
    """
    Decompress gzip-compressed response content if needed.

    Firmware 25.42.2+ returns gzip-compressed responses from TEDAPI endpoints.
    This function checks for the gzip magic bytes (0x1f 0x8b) and decompresses
    if necessary.

    Args:
        content: Raw response content bytes

    Returns:
        Decompressed bytes if gzip-compressed, otherwise original content
    """
    if len(content) > 2 and content[0:2] == b'\x1f\x8b':
        try:
            return gzip.decompress(content)
        except Exception as e:
            log.debug(f"Gzip decompression failed: {e}")
    return content

# TEDAPI Class
class TEDAPI:
    def __init__(self, gw_pwd: str = "", debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
                 pwconfigexpire: int = 5, host: str = GW_IP, poolmaxsize: int = 10,
                 v1r: bool = False, password: str | None = None, rsa_key_path: str | None = None,
                 wifi_host: str | None = None,
                 tedapi_api_version: TEDAPIApiVersion = TEDAPIApiVersion.JUNE_2024) -> None:
        """Initialize the TEDAPI client for Powerwall Gateway communication."""
        self.debug = debug
        # Query/protobuf version set: JUNE_2024 (default, hand-rolled captures) or
        # JUNE_2026 (Tesla-signed pairs sent via the energy_device graphql path).
        # Accepts a TEDAPIApiVersion or a plain string (e.g. from an env var / CLI).
        self.tedapi_api_version = TEDAPIApiVersion.coerce(tedapi_api_version)
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire status cache
        self.pwconfigexpire = pwconfigexpire  # seconds to expire config cache
        self.poolmaxsize = poolmaxsize # maximum size of the connection
        self.pwcache = {}  # holds the cached data for api
        self.timeout = timeout
        self.pwcooldown = 0
        self.gw_ip = host
        self.din = None
        self.pw3 = False # Powerwall 3 Gateway only supports TEDAPI
        self.v1r = v1r
        self.v1r_transport = None
        # WiFi fallback for v1r mode.
        # - Follower queries always use wifi_host when set.
        # - Primary queries fall back to wifi_host when the wired LAN (v1r) is down.
        # Only enabled when the caller explicitly provides a wifi_host string.
        self.wifi_host = wifi_host
        self.wifi_session = None
        self.wifi_available = False
        self.wifi_cooldown = 0      # timestamp when follower WiFi cooldown expires
        self.wifi_last_success = 0  # timestamp of last successful WiFi call
        self.wifi_fail_count = 0    # consecutive follower WiFi failures (exponential backoff)
        self._wifi_lock = threading.Lock()  # protects wifi_fail_count and wifi_cooldown
        # LAN (v1r) failure tracking — triggers full fallback to WiFi TEDAPI v1
        self.lan_failed = False     # True when wired LAN is unreachable
        self.lan_fail_count = 0     # consecutive LAN failures
        self.lan_recover_after = 0  # timestamp after which to retry LAN
        self.lan_last_success = 0   # timestamp of last successful LAN call
        if v1r:
            if not password or not rsa_key_path:
                raise ValueError("v1r mode requires password and rsa_key_path")
            from .tedapi_v1r import TEDAPIv1r
            self.v1r_transport = TEDAPIv1r(
                host=host, password=password, rsa_key_path=rsa_key_path,
                timeout=timeout, poolmaxsize=poolmaxsize
            )
            self.gw_pwd = gw_pwd or ""
            # Enable WiFi fallback only when an explicit wifi_host was provided
            if gw_pwd and self.wifi_host:
                self._init_wifi_session(gw_pwd)
        else:
            if not gw_pwd:
                raise ValueError("Missing gw_pwd")
            self.gw_pwd = gw_pwd
        if self.debug:
            self.set_debug(True)
        log.debug(f"TEDAPI initialized with pwcacheexpire={self.pwcacheexpire}s, pwconfigexpire={self.pwconfigexpire}s, v1r={self.v1r}")
        # Connect to Powerwall Gateway
        if not self.connect():
            log.error("Failed to connect to Powerwall Gateway")

    # TEDAPI Functions
    def set_debug(self, toggle=True, color=True):
        """Enable or disable verbose logging for TEDAPI."""
        if toggle:
            if color:
                logging.basicConfig(format='\x1b[31;1m%(levelname)s:%(message)s\x1b[0m', level=logging.DEBUG)
            else:
                logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.debug("%s [%s]\n" % (__name__, __version__))
        else:
            log.setLevel(logging.NOTSET)

    def get_din(self, force=False):
        """Get the Device Identification Number (DIN) from the Powerwall Gateway."""
        # Check Cache
        if not force and "din" in self.pwcachetime:
            if time.time() - self.pwcachetime["din"] < self.pwcacheexpire:
                log.debug("Using Cached DIN")
                return self.pwcache["din"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Fetch DIN from Powerwall
        log.debug("Fetching DIN from Powerwall...")
        if self.v1r:
            # When LAN is down, fetch DIN from wifi_host instead
            if self.lan_failed:
                if not self.wifi_session:
                    return None
                try:
                    url = f'https://{self.wifi_host}/tedapi/din'
                    r = self.wifi_session.get(url, timeout=self.timeout)
                    if r.status_code == HTTPStatus.OK:
                        content = decompress_response(r.content)
                        din = content.decode('utf-8').strip()
                        self.pwcachetime["din"] = time.time()
                        self.pwcache["din"] = din
                        return din
                except Exception as e:
                    log.error("get_din WiFi fallback failed: %s", e)
                return None
            din = self.v1r_transport.get_din()
            if din:
                self.pwcachetime["din"] = time.time()
                self.pwcache["din"] = din
            return din
        url = f'https://{self.gw_ip}/tedapi/din'
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code in BUSY_CODES:
            # Rate limited - Switch to cooldown mode for 5 minutes
            self.pwcooldown = time.perf_counter() + 300
            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
            return None
        if r.status_code == HTTPStatus.FORBIDDEN:
            log.error("Access Denied: Check your Gateway Password")
            return None
        if r.status_code != HTTPStatus.OK:
            log.error(f"Error fetching DIN: {r.status_code}")
            return None
        # Firmware 25.42.2+ returns gzip-compressed DIN response
        content = decompress_response(r.content)
        try:
            din = content.decode('utf-8').strip()
        except UnicodeDecodeError as e:
            log.error(f"Error decoding DIN response: {e}")
            return None
        log.debug(f"Connected: Powerwall Gateway DIN: {din}")
        self.pwcachetime["din"] = time.time()
        self.pwcache["din"] = din
        return din


    @uses_api_lock
    def get_config(self, self_function=None, force=False) -> Optional[Dict[Any, Any]]:
        """
        Get the Powerwall Gateway Configuration

        Payload:
        {
            "auto_meter_update": true,
            "battery_blocks": [],
            "bridge_inverter": {},
            "client_protocols": {},
            "credentials": [],
            "customer": {},
            "default_real_mode": "self_consumption",
            "dio": {},
            "enable_inverter_meter_readings": true,
            "freq_shift_load_shed": {},
            "freq_support_parameters": {},
            "industrial_networks": {},
            "installer": {},
            "island_config": {},
            "island_contactor_controller": {},
            "logging": {},
            "meters": [],
            "site_info": {},
            "solar": {},
            "solars": [],
            "strategy": {},
            "test_timers": {},
            "vin": "1232100-00-E--TG11234567890"
        }
        """
        # Check Cache BEFORE acquiring lock
        if not force and "config" in self.pwcachetime:
            age = time.time() - self.pwcachetime["config"]
            if age < self.pwconfigexpire:
                log.debug(f"Using Cached Config (age: {age:.2f}s, expire: {self.pwconfigexpire}s)")
                return self.pwcache["config"]
            else:
                log.debug(f"Cache expired for config (age: {age:.2f}s, expire: {self.pwconfigexpire}s)")
        
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        # Only acquire lock if we need to make an API call
        data = None
        try:
            with acquire_lock_with_backoff(self_function, self.timeout):
                # Double-check cache after acquiring lock (another thread might have updated it)
                if not force and "config" in self.pwcachetime:
                    if time.time() - self.pwcachetime["config"] < self.pwconfigexpire:
                        log.debug("Using Cached Payload (double-check)")
                        return self.pwcache["config"]
            
                # Re-check cooldown after acquiring lock
                if not force and self.pwcooldown > time.perf_counter():
                    log.debug('Rate limit cooldown period - Pausing API calls')
                    return None
                # Check Connection
                if not self.din:
                    if not self.connect():
                        log.error("Not Connected - Unable to get configuration")
                        return None
                # Fetch Configuration from Powerwall
                log.debug("Get Configuration from Powerwall")
                if self.v1r:
                    # v1r uses FileStore protobuf format for config
                    # When LAN is down, fall back to WiFi TEDAPI v1 config path
                    if self.lan_failed and self.wifi_session:
                        log.debug("get_config: LAN down, falling back to WiFi TEDAPI")
                        pb = tedapi_pb2.Message()
                        pb.message.deliveryChannel = 1
                        pb.message.sender.local = 1
                        pb.message.recipient.din = self.din
                        pb.message.config.send.num = 1
                        pb.message.config.send.file = "config.json"
                        pb.tail.value = 1
                        try:
                            raw = self._post_tedapi_wifi(pb.SerializeToString())
                            if raw:
                                tedapi = tedapi_pb2.Message()
                                tedapi.ParseFromString(raw)
                                payload = tedapi.message.config.recv.file.text
                                try:
                                    data = json.loads(payload)
                                except json.JSONDecodeError:
                                    data = {}
                                if 'battery_blocks' not in data:
                                    data["battery_blocks"] = []
                                self.pwcachetime["config"] = time.time()
                                self.pwcache["config"] = data
                        except Exception as e:
                            log.error(f"get_config WiFi fallback error: {e}")
                            data = None
                    else:
                        try:
                            data = self.v1r_transport.get_config_v1r(self.din)
                            if data:
                                log.debug(f"Configuration (v1r): {data}")
                                self.pwcachetime["config"] = time.time()
                                self.pwcache["config"] = data
                        except Exception as e:
                            log.error(f"Error fetching config via v1r: {e}")
                            data = None
                else:
                    # Build Protobuf to fetch config (WiFi v1 format)
                    pb = tedapi_pb2.Message()
                    pb.message.deliveryChannel = 1
                    pb.message.sender.local = 1
                    pb.message.recipient.din = self.din  # DIN of Powerwall
                    pb.message.config.send.num = 1
                    pb.message.config.send.file = "config.json"
                    pb.tail.value = 1
                    url = f'https://{self.gw_ip}/tedapi/v1'
                    try:
                        r = self.session.post(url, data=pb.SerializeToString(), timeout=self.timeout)
                        log.debug(f"Response Code: {r.status_code}")
                        if r.status_code in BUSY_CODES:
                            # Rate limited - Switch to cooldown mode for 5 minutes
                            self.pwcooldown = time.perf_counter() + 300
                            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                            return None
                        if r.status_code != HTTPStatus.OK:
                            log.error(f"Error fetching config: {r.status_code}")
                            return None
                        # Decode response
                        tedapi = tedapi_pb2.Message()
                        tedapi.ParseFromString(decompress_response(r.content))
                        payload = tedapi.message.config.recv.file.text
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError as e:
                            log.error(f"Error Decoding JSON: {e}")
                            data = {}
                        if 'battery_blocks' not in data:
                            data["battery_blocks"] = []
                        log.debug(f"Configuration: {data}")
                        self.pwcachetime["config"] = time.time()
                        self.pwcache["config"] = data
                    except Exception as e:
                        log.error(f"Error fetching config: {e}")
                        data = None
        except TimeoutError:
            log.error('Timeout waiting for API lock - unable to fetch config - '
                      'returning cached data if available')
            return self.pwcache.get("config")
        return data

    def _write_config(self, updates: dict) -> bool:
        """
        Write config.json via v1r filestore updateFileRequest (read-modify-write).

        Args:
            updates: dict of dotted paths to values, e.g. {'site_info.backup_reserve_percent': 5}
        Returns:
            True on success, False on error.
        """
        if not self.v1r or not self.v1r_transport:
            log.error("_write_config requires v1r transport")
            return False
        if not self.din:
            if not self.connect():
                log.error("Not connected - unable to write config")
                return False
        try:
            result = self.v1r_transport.write_config_v1r(self.din, updates)
            if result:
                # Invalidate config cache
                self.pwcache.pop("config", None)
                self.pwcachetime.pop("config", None)
                return True
            return False
        except Exception as e:
            log.error(f"Error writing config: {e}")
            return False

    # ── Max Backup (TEGMessages) ─────────────────────────────────────

    def schedule_max_backup(self, duration_seconds=7200):
        """
        Schedule manual backup event (max backup / storm watch mode).

        Sets reserve to 100% for the specified duration via TEGMessages.
        Automatically cancels any existing backup event first — the gateway
        requires cancel before setting a new one.

        Args:
            duration_seconds: Duration in seconds (default 7200 = 2 hours, min 60)

        Returns:
            True on success, False on error.
        """
        if not self.v1r or not self.v1r_transport:
            log.error("schedule_max_backup requires v1r transport")
            return False
        if not self.din:
            if not self.connect():
                log.error("Not connected - unable to schedule max backup")
                return False
        duration_seconds = max(60, int(duration_seconds))
        try:
            # Must cancel any existing (active or expired) before scheduling new
            self.cancel_max_backup()
            from google.protobuf.timestamp_pb2 import Timestamp  # pylint: disable=no-name-in-module
            teg = combined_pb2.TEGMessages()
            req = teg.schedule_manual_backup_event_request
            req.scheduling_info.start_time.CopyFrom(Timestamp(seconds=int(time.time())))
            req.scheduling_info.duration_seconds = duration_seconds
            req.scheduling_info.priority = (1 << 64) - 1  # MAX_UINT64 = highest priority
            resp = self.v1r_transport.send_teg_message(self.din, teg)
            if resp is None:
                log.error("schedule_max_backup: no response")
                return False
            if resp.HasField('teg') and resp.teg.HasField('schedule_manual_backup_event_response'):
                log.info(f"Max backup scheduled for {duration_seconds}s")
                return True
            log.warning(f"schedule_max_backup: unexpected response payload")
            return False
        except Exception as e:
            log.error(f"schedule_max_backup error: {e}")
            return False

    def cancel_max_backup(self):
        """
        Cancel the current manual backup event.

        Returns:
            True on success, False on error.
        """
        if not self.v1r or not self.v1r_transport:
            log.error("cancel_max_backup requires v1r transport")
            return False
        if not self.din:
            if not self.connect():
                log.error("Not connected - unable to cancel max backup")
                return False
        try:
            teg = combined_pb2.TEGMessages()
            teg.cancel_manual_backup_event_request.SetInParent()
            resp = self.v1r_transport.send_teg_message(self.din, teg)
            if resp is None:
                log.error("cancel_max_backup: no response")
                return False
            if resp.HasField('teg') and resp.teg.HasField('cancel_manual_backup_event_response'):
                log.info("Max backup cancelled")
                return True
            log.warning(f"cancel_max_backup: unexpected response payload")
            return False
        except Exception as e:
            log.error(f"cancel_max_backup error: {e}")
            return False

    def get_backup_events(self):
        """
        Get current backup events.

        Returns:
            Dict with 'manual_backup' (dict or None) and 'backup_events' (list),
            or None on error.
        """
        if not self.v1r or not self.v1r_transport:
            log.error("get_backup_events requires v1r transport")
            return None
        if not self.din:
            if not self.connect():
                log.error("Not connected - unable to get backup events")
                return None
        try:
            teg = combined_pb2.TEGMessages()
            teg.get_backup_events_request.SetInParent()
            resp = self.v1r_transport.send_teg_message(self.din, teg)
            if resp is None:
                log.error("get_backup_events: no response")
                return None
            if resp.HasField('teg') and resp.teg.HasField('get_backup_events_response'):
                events_resp = resp.teg.get_backup_events_response
                result = {
                    'manual_backup': None,
                    'backup_events': []
                }
                # Parse manual backup event if present
                if events_resp.HasField('manual_backup_event'):
                    mbe = events_resp.manual_backup_event
                    si = mbe.scheduling_info
                    end_time = si.start_time.seconds + si.duration_seconds
                    active = int(time.time()) < end_time
                    result['manual_backup'] = {
                        'start_time': si.start_time.seconds,
                        'duration_seconds': si.duration_seconds,
                        'end_time': end_time,
                        'active': active,
                        'priority': si.priority,
                    }
                # Parse scheduled backup events
                for evt in events_resp.backup_events:
                    si = evt.scheduling_info
                    result['backup_events'].append({
                        'id': evt.id,
                        'name': evt.name,
                        'start_time': si.start_time.seconds,
                        'duration_seconds': si.duration_seconds,
                        'priority': si.priority,
                    })
                return result
            log.warning(f"get_backup_events: unexpected response payload")
            return None
        except Exception as e:
            log.error(f"get_backup_events error: {e}")
            return None

    @uses_api_lock
    def get_status(self, self_function=None, force=False) -> Optional[Dict[Any, Any]]:
        """
        Get the Powerwall Gateway Status

        Payload:
        {
            "control": {
                "alerts": {},
                "batteryBlocks": [],
                "islanding": {},
                "meterAggregates": [],
                "pvInverters": [],
                "siteShutdown": {},
                "systemStatus": {}
                },
            "esCan": {
                "bus": {
                    "ISLANDER": {},
                    "MSA": {},
                    "PINV": [],
                    "POD": [],
                    "PVAC": [],
                    "PVS": [],
                    "SYNC": {},
                    "THC": []
                    },
                "enumeration": null,
                "firmwareUpdate": {},
                "inverterSelfTests": null,
                "phaseDetection": null
                },
            "neurio": {
                "isDetectingWiredMeters": false,
                "pairings": [],
                "readings": []
                },
            "pw3Can": {},
            "system": {}
        }
        """
        # Check Cache BEFORE acquiring lock
        if not force and "status" in self.pwcachetime:
            age = time.time() - self.pwcachetime["status"]
            if age < self.pwcacheexpire:
                log.debug(f"Using Cached Payload (age: {age:.2f}s, expire: {self.pwcacheexpire}s)")
                return self.pwcache["status"]
            else:
                log.debug(f"Cache expired for status (age: {age:.2f}s, expire: {self.pwcacheexpire}s)")
        
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        # Only acquire lock if we need to make an API call
        data = None
        try:
            with acquire_lock_with_backoff(self_function, self.timeout):
                # Double-check cache after acquiring lock (another thread might have updated it)
                if not force and "status" in self.pwcachetime:
                    if time.time() - self.pwcachetime["status"] < self.pwcacheexpire:
                        log.debug("Using Cached Payload (double-check)")
                        return self.pwcache["status"]
            
                # Re-check cooldown after acquiring lock
                if not force and self.pwcooldown > time.perf_counter():
                    log.debug('Rate limit cooldown period - Pausing API calls')
                    return None
                # Check Connection
                if not self.din:
                    if not self.connect():
                        log.error("Not Connected - Unable to get status")
                        return None
                # Fetch Current Status from Powerwall
                log.debug("Get Status from Powerwall")

                # Build Protobuf to fetch status
                if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                    request_bytes = self._build_signed_query_request(
                        get_query("device_controller_basic", TEDAPIApiVersion.JUNE_2026))
                else:
                    pb = tedapi_pb2.Message()
                    pb.message.deliveryChannel = 1
                    pb.message.sender.local = 1
                    pb.message.recipient.din = self.din  # DIN of Powerwall
                    pb.message.payload.send.num = 2
                    pb.message.payload.send.payload.value = 1
                    apply_query(pb.message.payload.send, get_query("device_controller_basic"))
                    pb.tail.value = 1
                    request_bytes = pb.SerializeToString()
                try:
                    response = self._post_tedapi(request_bytes)
                    if response is None:
                        return None
                    if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                        payload = self._parse_signed_query_response(response)
                    elif self.v1r:
                        payload = self._parse_v1r_query_response(response)
                    else:
                        # Decode WiFi v1 response
                        tedapi = tedapi_pb2.Message()
                        tedapi.ParseFromString(response)
                        payload = tedapi.message.payload.recv.text
                    try:
                        data = json.loads(payload)
                    except (json.JSONDecodeError, TypeError) as e:
                        log.error(f"Error Decoding JSON: {e}")
                        data = {}
                    log.debug(f"Status: {data}")
                    self.pwcachetime["status"] = time.time()
                    self.pwcache["status"] = data
                except Exception as e:
                    log.error(f"Error fetching status: {e}")
                    data = None
        except TimeoutError:
            log.error('Timeout waiting for API lock - unable to fetch status - '
                      'returning cached data if available')
            return self.pwcache.get("status")
        return data


    @uses_api_lock
    def get_device_controller(self, self_function=None, force=False):
        """
        Get the Powerwall Device Controller Status.
        Similar to get_status but with additional data:
        {
            "components": {}, // Additional data
            "control": {},
            "esCan": {},
            "ieee20305": {}, // Additional data
            "neurio": {},
            "pw3Can": {},
            "system": {},
            "teslaRemoteMeter": {} // Additional data
        }

        TODO: Refactor to combine tedapi queries
        """
        # Check Cache BEFORE acquiring lock
        if not force and "controller" in self.pwcachetime:
            age = time.time() - self.pwcachetime["controller"]
            if age < self.pwcacheexpire:
                log.debug(f"Using Cached Controller (age: {age:.2f}s, expire: {self.pwcacheexpire}s)")
                return self.pwcache["controller"]
            else:
                log.debug(f"Cache expired for controller (age: {age:.2f}s, expire: {self.pwcacheexpire}s)")
        
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        # Only acquire lock if we need to make an API call
        data = None
        try:
            with acquire_lock_with_backoff(self_function, self.timeout):
                # Double-check cache after acquiring lock (another thread might have updated it)
                if not force and "controller" in self.pwcachetime:
                    if time.time() - self.pwcachetime["controller"] < self.pwcacheexpire:
                        log.debug("Using Cached Payload (double-check)")
                        return self.pwcache["controller"]
            
                # Re-check cooldown after acquiring lock
                if not force and self.pwcooldown > time.perf_counter():
                    log.debug('Rate limit cooldown period - Pausing API calls')
                    return None
                # Check Connection
                if not self.din:
                    if not self.connect():
                        log.error("Not Connected - Unable to get controller data")
                        return None
                # Fetch Current Status from Powerwall
                log.debug("Get controller data from Powerwall")

                # Build Protobuf to fetch controller data
                if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                    request_bytes = self._build_signed_query_request(
                        get_query("device_controller_full", TEDAPIApiVersion.JUNE_2026))
                else:
                    pb = tedapi_pb2.Message()
                    pb.message.deliveryChannel = 1
                    pb.message.sender.local = 1
                    pb.message.recipient.din = self.din  # DIN of Powerwall
                    pb.message.payload.send.num = 2
                    pb.message.payload.send.payload.value = 1
                    apply_query(pb.message.payload.send, get_query("device_controller_full"))
                    pb.tail.value = 1
                    request_bytes = pb.SerializeToString()
                try:
                    response = self._post_tedapi(request_bytes)
                    if response is None:
                        return None
                    if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                        payload = self._parse_signed_query_response(response)
                    elif self.v1r:
                        payload = self._parse_v1r_query_response(response)
                    else:
                        tedapi = tedapi_pb2.Message()
                        tedapi.ParseFromString(response)
                        payload = tedapi.message.payload.recv.text
                    log.debug(f"Payload: {payload}")
                    try:
                        data = json.loads(payload)
                    except (json.JSONDecodeError, TypeError) as e:
                        log.error(f"Error Decoding JSON: {e}")
                        data = {}
                    log.debug(f"Status: {data}")
                    self.pwcachetime["controller"] = time.time()
                    self.pwcache["controller"] = data
                except Exception as e:
                    log.error(f"Error fetching controller data: {e}")
                    data = None
        except TimeoutError:
            log.error('Timeout waiting for API lock - unable to fetch controller data - '
                      'returning cached data if available')
            return self.pwcache.get("controller")
        return data


    @uses_api_lock
    def get_firmware_version(self, self_function=None, force=False, details=False):
        """
        Get the Powerwall Firmware Version.
        Args:
            force (bool): Force a refresh of the firmware version
            details (bool): Return additional system information including
                            gateway part number, serial number, and wireless devices
        Example payload (details=True):
            {
                "system": {
                    "gateway": {"partNumber": ..., "serialNumber": ...},
                    "din": ..., "version": {"text": ..., "githash": ...}, ...
                }
            }
        """
        # Check Cache BEFORE acquiring lock
        if not force and "firmware" in self.pwcachetime:
            if time.time() - self.pwcachetime["firmware"] < self.pwcacheexpire:
                log.debug("Using Cached Firmware")
                return self.pwcache["firmware"]
        
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        payload = None
        try:
            with acquire_lock_with_backoff(self_function, self.timeout):
                # Double-check cache after acquiring lock (another thread might have updated it)
                if not force and "firmware" in self.pwcachetime:
                    if time.time() - self.pwcachetime["firmware"] < self.pwcacheexpire:
                        log.debug("Using Cached Firmware (double-check)")
                        return self.pwcache["firmware"]
            
                # Re-check cooldown after acquiring lock
                if not force and self.pwcooldown > time.perf_counter():
                    log.debug('Rate limit cooldown period - Pausing API calls')
                    return None
                # Fetch Current Status from Powerwall
                log.debug("Get Firmware Version from Powerwall")
                # Build Protobuf to fetch firmware
                pb = tedapi_pb2.Message()
                pb.message.deliveryChannel = 1
                pb.message.sender.local = 1
                pb.message.recipient.din = self.din  # DIN of Powerwall
                pb.message.firmware.request = ""
                pb.tail.value = 1
                try:
                    response = self._post_tedapi(pb.SerializeToString())
                    if response is None:
                        return None
                    # Decode response
                    if self.v1r:
                        # v1r response is a MessageEnvelope (not full Message)
                        envelope = tedapi_pb2.MessageEnvelope()
                        envelope.ParseFromString(response)
                        firmware_version = envelope.firmware.system.version.text
                        if details:
                            payload = {
                                "system": {
                                    "gateway": {
                                        "partNumber": envelope.firmware.system.gateway.partNumber,
                                        "serialNumber": envelope.firmware.system.gateway.serialNumber
                                    },
                                    "din": envelope.firmware.system.din,
                                    "version": {
                                        "text": envelope.firmware.system.version.text,
                                        "githash": envelope.firmware.system.version.githash
                                    },
                                    "five": envelope.firmware.system.five,
                                    "six": envelope.firmware.system.six,
                                    "wireless": {"device": []}
                                }
                            }
                        else:
                            payload = firmware_version
                    else:
                        tedapi = tedapi_pb2.Message()
                        tedapi.ParseFromString(response)
                        firmware_version = tedapi.message.firmware.system.version.text
                        if details:
                            payload = {
                                "system": {
                                    "gateway": {
                                        "partNumber": tedapi.message.firmware.system.gateway.partNumber,
                                        "serialNumber": tedapi.message.firmware.system.gateway.serialNumber
                                    },
                                    "din": tedapi.message.firmware.system.din,
                                    "version": {
                                        "text": tedapi.message.firmware.system.version.text,
                                        "githash": tedapi.message.firmware.system.version.githash
                                    },
                                    "five": tedapi.message.firmware.system.five,
                                    "six": tedapi.message.firmware.system.six,
                                    "wireless": {
                                        "device": []
                                    }
                                }
                            }
                            try:
                                for device in tedapi.message.firmware.system.wireless.device:
                                    payload["system"]["wireless"]["device"].append({
                                        "company": device.company.value,
                                        "model": device.model.value,
                                        "fcc_id": device.fcc_id.value,
                                        "ic": device.ic.value
                                    })
                            except Exception as e:
                                log.debug(f"Error parsing wireless devices: {e}")
                            log.debug(f"Firmware Version: {payload}")
                        else:
                            payload = firmware_version
                    log.debug(f"Firmware Version: {firmware_version}")
                    self.pwcachetime["firmware"] = time.time()
                    self.pwcache["firmware"] = firmware_version
                except Exception as e:
                    log.error(f"Error fetching firmware version: {e}")
                    payload = None
        except TimeoutError:
            log.error('Timeout waiting for API lock - unable to fetch firmware version - '
                      'returning cached data if available')
            return self.pwcache.get("firmware")
        return payload


    @uses_api_lock
    def get_components(self, self_function=None, force=False):
        """
        Get Powerwall 3 device component information.
        Example payload:
            {
                "components": {
                    "pch": [...],
                    "bms": [...],
                    ...
                }
            }
        """
        # Check Cache BEFORE acquiring lock
        if not force and "components" in self.pwcachetime:
            cache_age = time.time() - self.pwcachetime["components"]
            if cache_age < self.pwconfigexpire:
                log.debug(f"Using Cached Components (age: {cache_age:.2f}s, expire: {self.pwconfigexpire}s)")
                return self.pwcache["components"]
        
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        components = None
        try:
            with acquire_lock_with_backoff(self_function, self.timeout):
                # Double-check cache after acquiring lock (another thread might have updated it)
                if not force and "components" in self.pwcachetime:
                    cache_age = time.time() - self.pwcachetime["components"]
                    if cache_age < self.pwconfigexpire:
                        log.debug(f"Using Cached Components (age: {cache_age:.2f}s, expire: {self.pwconfigexpire}s) (double-check)")
                        return self.pwcache["components"]
            
                # Re-check cooldown after acquiring lock
                if not force and self.pwcooldown > time.perf_counter():
                    log.debug('Rate limit cooldown period - Pausing API calls')
                    return None
                # Fetch Configuration from Powerwall
                log.debug("Get PW3 Components from Powerwall")

                # Build Protobuf to fetch config
                if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                    request_bytes = self._build_signed_query_request(
                        get_query("components", TEDAPIApiVersion.JUNE_2026))
                else:
                    pb = tedapi_pb2.Message()
                    pb.message.deliveryChannel = 1
                    pb.message.sender.local = 1
                    pb.message.recipient.din = self.din  # DIN of Powerwall
                    pb.message.payload.send.num = 2
                    pb.message.payload.send.payload.value = 1
                    apply_query(pb.message.payload.send, get_query("components"))
                    pb.tail.value = 1
                    request_bytes = pb.SerializeToString()
                try:
                    response = self._post_tedapi(request_bytes)
                    if response is None:
                        return None
                    if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                        payload = self._parse_signed_query_response(response)
                    elif self.v1r:
                        payload = self._parse_v1r_query_response(response)
                    else:
                        tedapi = tedapi_pb2.Message()
                        tedapi.ParseFromString(response)
                        payload = tedapi.message.payload.recv.text
                    log.debug(f"Payload (len={len(payload) if payload else 0}): {payload}")
                    components = json.loads(payload)
                    log.debug(f"Components: {components}")
                    self.pwcachetime["components"] = time.time()
                    self.pwcache["components"] = components
                except Exception as e:
                    log.error(f"Error fetching components: {e}")
                    components = None
        except TimeoutError:
            log.error('Timeout waiting for API lock - unable to fetch components - '
                      'returning cached data if available')
            return self.pwcache.get("components")
        return components


    def get_pw3_vitals(self, force=False):
        """
        Get Powerwall 3 Battery Vitals Data.
        Returns:
        {
            "PVAC--{part}--{sn}" {
                "PVAC_PvState_A": "PV_Active",
                "PVAC_PVCurrent_A": 0.0,
                ...
                "PVAC_PVMeasuredVoltage_A": 0.0,
                ...
                "PVAC_PVMeasuredPower_A": 0.0,
                ...
                "PVAC_Fout": 60.0,
                "PVAC_Pout": 0.0,
                "PVAC_State": X,
                "PVAC_VL1Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL1Ground']),
                "PVAC_VL2Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL2Ground']),
                "PVAC_Vout": lookup(p, ['PVAC_Status', 'PVAC_Vout']),
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
            }.
            "PVS--{part}--{sn}" {
                "PVS_StringA_Connected": true,
                ...
            },
            "TEPOD--{part}--{sn}" {
                "alerts": [],
                "POD_nom_energy_remaining": 0.0,
                "POD_nom_full_pack_energy": 0.0,
                "POD_nom_energy_to_be_charged": 0.0,
            }
        }
        """
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get configuration")
                return None
        # Check Cache
        if not force and "pw3_vitals" in self.pwcachetime:
            cache_age = time.time() - self.pwcachetime["pw3_vitals"]
            if cache_age < self.pwconfigexpire:
                log.debug(f"Using Cached Components (age: {cache_age:.2f}s, expire: {self.pwconfigexpire}s)")
                return self.pwcache["pw3_vitals"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        components = self.get_components(force=force)
        din = self.din
        if not components:
            log.error("Unable to get Powerwall 3 Components")
            return None

        response = {}
        config = self.get_config(force=force)
        if not isinstance(config, dict):
            log.error("Unable to get configuration for Powerwall 3 vitals")
            return None
        battery_blocks = config.get('battery_blocks') or []

        # Check to see if there is only one Powerwall
        single_pw = False
        if battery_blocks and len(battery_blocks) == 1:
            single_pw = True
        # Loop through all the battery blocks (Powerwalls)
        for battery in battery_blocks:
            pw_din = battery['vin'] # 1707000-11-J--TG12xxxxxx3A8Z
            pw_part, pw_serial = pw_din.split('--')
            battery_type = battery['type']
            if "Powerwall3" not in battery_type:
                continue
            # Determine if this is a follower that needs WiFi fallback
            is_follower = (pw_din != self.din)
            use_wifi = False
            if self.v1r and is_follower:
                if not self.wifi_session:
                    log.debug("v1r: Skipping follower %s (no WiFi session)", pw_din)
                    continue
                use_wifi = True
                log.debug("v1r: Querying follower %s via WiFi", pw_din)
            # Fetch Device ComponentsQuery from each Powerwall
            if single_pw:
                url_suffix = '/tedapi/v1'
            else:
                url_suffix = f'/tedapi/device/{pw_din}/v1'
            if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                request_bytes = self._build_signed_query_request(
                    get_query("components", TEDAPIApiVersion.JUNE_2026),
                    recipient_din=pw_din,
                    sender_din=None if single_pw else din,
                    tail=1 if single_pw else 2)
            else:
                pb = tedapi_pb2.Message()
                pb.message.deliveryChannel = 1
                pb.message.sender.local = 1
                pb.message.recipient.din = pw_din  # DIN of Powerwall of Interest
                pb.message.payload.send.num = 2
                pb.message.payload.send.payload.value = 1
                apply_query(pb.message.payload.send, get_query("components"))
                if single_pw:
                    # If only one Powerwall, use basic tedapi URL
                    pb.tail.value = 1
                else:
                    # If multiple Powerwalls, use tedapi/device/{pw_din}/v1
                    pb.tail.value = 2
                    pb.message.sender.din = din  # DIN of Primary Powerwall 3 / System
                request_bytes = pb.SerializeToString()
            if use_wifi:
                # WiFi fallback for follower — use WiFi session (standard protobuf response)
                api_response = self._post_tedapi_wifi(request_bytes, url_suffix=url_suffix)
            else:
                api_response = self._post_tedapi(request_bytes, din=pw_din, url_suffix=url_suffix)
            if api_response is not None:
                if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                    payload = self._parse_signed_query_response(api_response)
                elif self.v1r and not use_wifi:
                    payload = self._parse_v1r_query_response(api_response)
                else:
                    tedapi = tedapi_pb2.Message()
                    tedapi.ParseFromString(api_response)
                    payload = tedapi.message.payload.recv.text
                if payload:
                    # Guard the JSON parse and component access - a malformed or
                    # partial follower payload should not abort the whole vitals call
                    try:
                        data = json.loads(payload)
                        components = data['components']
                        pch_components = components['pch']
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        log.error(f"Error parsing component payload for {pw_din} - skipping: {e}")
                        continue
                    # TEDPOD
                    alerts = []
                    for component in components:
                        if components[component]:
                            for alert in components[component][0]['activeAlerts']:
                                if alert['name'] not in alerts:
                                    alerts.append(alert['name'])
                    # Process all BMS and HVP components to support expansion packs
                    # HVP entries have serial numbers, BMS entries have energy data
                    # They correspond 1:1 by index
                    bms_list = data['components'].get('bms', [])
                    hvp_list = data['components'].get('hvp', [])

                    # Get expansion pack DINs for this battery block
                    expansion_dins = {}
                    for exp in battery.get('battery_expansions', []):
                        exp_din = exp.get('din', '')
                        exp_parts = exp_din.split('--')
                        if len(exp_parts) >= 2 and exp_parts[1]:
                            exp_serial = exp_parts[1]
                            expansion_dins[exp_serial] = exp_din

                    # Process each BMS/HVP pair
                    for bms_idx, bms_component in enumerate(bms_list):
                        signals = bms_component.get('signals', [])
                        nom_energy_remaining = 0
                        nom_full_pack_energy = 0
                        for signal in signals:
                            if signal.get('value') is None:
                                continue
                            if "BMS_nominalEnergyRemaining" == signal['name']:
                                nom_energy_remaining = int(signal['value'] * 1000)  # Convert to Wh
                            elif "BMS_nominalFullPackEnergy" == signal['name']:
                                nom_full_pack_energy = int(signal['value'] * 1000)  # Convert to Wh

                        # Skip entries with no energy data
                        if nom_full_pack_energy == 0:
                            continue

                        # Get corresponding HVP serial (same index)
                        hvp_serial = None
                        if bms_idx < len(hvp_list):
                            hvp_serial = hvp_list[bms_idx].get('serialNumber')

                        # Determine DIN for this BMS entry
                        if bms_idx == 0:
                            # First BMS is the main Powerwall unit
                            pod_din = pw_din
                        elif hvp_serial and hvp_serial in expansion_dins:
                            # This is an expansion pack - use its full DIN
                            pod_din = expansion_dins[hvp_serial]
                        else:
                            # BMS entry doesn't match main unit or known expansion - skip it
                            # (This catches phantom BMS slots on batteries without expansions)
                            continue

                        response[f"TEPOD--{pod_din}"] = {
                            "alerts": alerts,
                            "POD_nom_energy_remaining": nom_energy_remaining,
                            "POD_nom_energy_to_be_charged": nom_full_pack_energy - nom_energy_remaining,
                            "POD_nom_full_pack_energy": nom_full_pack_energy,
                        }
                    # PVAC, PVS and TEPINV
                    response[f"PVAC--{pw_din}"] = {}
                    response[f"PVS--{pw_din}"] = {}
                    response[f"TEPINV--{pw_din}"] = {}
                    # pch_components contain:
                    #   PCH_PvState_A through F - textValue in [Pv_Active, Pv_Active_Parallel, Pv_Standby]
                    #   PCH_PvVoltageA through F - value
                    #   PCH_PvCurrentA through F - value
                    # Loop through and find all the strings - PW3 has 6 strings A-F
                    for n in ["A", "B", "C", "D", "E", "F"]:
                        pv_state = "Unknown"
                        pv_voltage = 0
                        pv_current = 0
                        for component in pch_components: # TODO: Probably better way to do this
                            signals = component['signals']
                            for signal in signals:
                                if f'PCH_PvState_{n}' == signal['name']:
                                    pv_state = signal['textValue']
                                elif f'PCH_PvVoltage{n}' == signal['name']:
                                    pv_voltage = signal['value'] if signal['value'] is not None and signal['value'] > 0 else 0
                                elif f'PCH_PvCurrent{n}' == signal['name']:
                                    pv_current = signal['value'] if signal['value'] is not None and signal['value'] > 0 else 0
                                elif 'PCH_AcFrequency' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_Fout"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_Fout"] = signal['value']
                                elif 'PCH_AcVoltageAN' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_VL1Ground"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_VSplit1"] = signal['value']
                                elif 'PCH_AcVoltageBN' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_VL2Ground"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_VSplit2"] = signal['value']
                                elif 'PCH_AcVoltageAB' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_Vout"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_Vout"] = signal['value']
                                elif 'PCH_BatteryPower' == signal['name']: # not PCH_AcRealPowerAB
                                    response[f"PVAC--{pw_din}"]["PVAC_Pout"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_Pout"] = (signal['value'] or 0) / 1000
                                elif 'PCH_AcMode' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_State"] = signal['textValue']
                                    response[f"TEPINV--{pw_din}"]["PINV_State"] = signal['textValue']
                        pv_power = pv_voltage * pv_current # Calculate power
                        response[f"PVAC--{pw_din}"][f"PVAC_PvState_{n}"] = pv_state
                        response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredVoltage_{n}"] = pv_voltage
                        response[f"PVAC--{pw_din}"][f"PVAC_PVCurrent_{n}"] = pv_current
                        response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredPower_{n}"] = pv_power
                        response[f"PVAC--{pw_din}"]["manufacturer"] = "TESLA"
                        response[f"PVAC--{pw_din}"]["partNumber"] = pw_part
                        response[f"PVAC--{pw_din}"]["serialNumber"] = pw_serial
                        response[f"PVS--{pw_din}"][f"PVS_String{n}_Connected"] = ("Pv_Active" in pv_state)
                else:
                    log.debug(f"No payload for {pw_din}")
            else:
                log.debug(f"No response for {pw_din}")
        return response


    def get_battery_blocks(self, force=False):
        """Return Powerwall battery blocks from configuration."""
        config = self.get_config(force=force)
        if not isinstance(config, dict):
            log.error("Unable to get configuration for battery blocks")
            return []
        battery_blocks = config.get('battery_blocks') or []
        return battery_blocks


    @uses_api_lock
    def get_battery_block(self, self_function=None, din=None, force=False):
        """
        Get the Powerwall 3 Battery Block Information.
        Args:
            din (str): DIN of Powerwall 3 to query
            force (bool): Force a refresh of the battery block
        Note: Provides 404 response for previous Powerwall versions
        """
        # Make sure we have a DIN
        if not din:
            log.error("No DIN specified - Unable to get battery block")
            return None
        # v1r cannot route queries to follower Powerwalls — use WiFi fallback
        use_wifi = False
        if self.v1r and din != self.din:
            if not self.wifi_session:
                log.debug("v1r: Cannot query follower battery block %s (no WiFi session)", din)
                return None
            use_wifi = True
            log.debug("v1r: Querying follower battery block %s via WiFi", din)

        # Check Cache BEFORE acquiring lock
        if not force and din in self.pwcachetime:
            if time.time() - self.pwcachetime[din] < self.pwcacheexpire:
                log.debug("Using Cached Battery Block")
                return self.pwcache[din]
        
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        data = None
        try:
            with acquire_lock_with_backoff(self_function, self.timeout):
                # Double-check cache after acquiring lock (another thread might have updated it)
                if not force and din in self.pwcachetime:
                    if time.time() - self.pwcachetime[din] < self.pwcacheexpire:
                        log.debug("Using Cached Battery Block (double-check)")
                        return self.pwcache[din]
            
                # Re-check cooldown after acquiring lock
                if not force and self.pwcooldown > time.perf_counter():
                    log.debug('Rate limit cooldown period - Pausing API calls')
                    return None
                # Fetch Battery Block from Powerwall
                log.debug(f"Get Battery Block from Powerwall ({din})")

                # Build Protobuf to fetch config
                if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                    request_bytes = self._build_signed_query_request(
                        get_query("components", TEDAPIApiVersion.JUNE_2026),
                        recipient_din=din, sender_din=self.din, tail=2)
                else:
                    pb = tedapi_pb2.Message()
                    pb.message.deliveryChannel = 1
                    pb.message.sender.local = 1
                    pb.message.sender.din = self.din  # DIN of Primary Powerwall 3 / System
                    pb.message.recipient.din = din  # DIN of Powerwall of Interest
                    pb.message.payload.send.num = 2
                    pb.message.payload.send.payload.value = 1
                    apply_query(pb.message.payload.send, get_query("components"))
                    pb.tail.value = 2
                    request_bytes = pb.SerializeToString()
                try:
                    url_suffix = f'/tedapi/device/{din}/v1'
                    if use_wifi:
                        response = self._post_tedapi_wifi(request_bytes, url_suffix=url_suffix)
                    else:
                        response = self._post_tedapi(request_bytes, din=din,
                                                     url_suffix=url_suffix)
                    if response is None:
                        return None
                    if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                        payload_text = self._parse_signed_query_response(response)
                        data = json.loads(payload_text) if payload_text else {}
                    elif self.v1r and not use_wifi:
                        # v1r battery block config — try parsing as query response first
                        payload_text = self._parse_v1r_query_response(response)
                        if payload_text:
                            data = json.loads(payload_text)
                        else:
                            data = {}
                    else:
                        tedapi = tedapi_pb2.Message()
                        tedapi.ParseFromString(response)
                        payload = tedapi.message.config.recv.file.text
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError as e:
                            log.error(f"Error Decoding JSON: {e}")
                            data = {}
                    log.debug(f"Configuration: {data}")
                    self.pwcachetime[din] = time.time()
                    self.pwcache[din] = data
                except Exception as e:
                    log.error(f"Error fetching device: {e}")
                    data = None
        except TimeoutError:
            log.error('Timeout waiting for API lock - unable to fetch battery block - '
                      'returning cached data if available')
            return self.pwcache.get(din)
        return data

    def _init_session(self):
        """Initialize and return a requests.Session for TEDAPI communication."""
        session = requests.Session()
        if self.poolmaxsize > 0:
            retries = urllib3.Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=RETRY_FORCE_CODES,
                raise_on_status=False
            )
            adapter = HTTPAdapter(max_retries=retries, pool_connections=self.poolmaxsize, pool_maxsize=self.poolmaxsize, pool_block=True)
            session.mount("https://", adapter)
        else:
            session.headers.update({'Connection': 'close'})  # This disables keep-alive
        session.verify = False
        session.auth = ('Tesla_Energy_Device', self.gw_pwd)
        session.headers.update({'Content-type': 'application/octet-string'})
        return session

    def _init_wifi_session(self, gw_pwd: str):
        """Initialize WiFi TEDAPI session for follower queries in v1r mode."""
        session = requests.Session()
        if self.poolmaxsize > 0:
            retries = urllib3.Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=RETRY_FORCE_CODES,
                raise_on_status=False
            )
            adapter = HTTPAdapter(max_retries=retries, pool_connections=self.poolmaxsize, pool_maxsize=self.poolmaxsize, pool_block=True)
            session.mount("https://", adapter)
        else:
            session.headers.update({'Connection': 'close'})
        session.verify = False
        session.auth = ('Tesla_Energy_Device', gw_pwd)
        session.headers.update({'Content-type': 'application/octet-string'})
        self.wifi_session = session
        log.debug(f"WiFi fallback session initialized for {self.wifi_host}")

    def _test_wifi_path(self):
        """Test WiFi TEDAPI connectivity by fetching DIN. Non-blocking."""
        if not self.wifi_session:
            return
        try:
            url = f'https://{self.wifi_host}/tedapi/din'
            r = self.wifi_session.get(url, timeout=self.timeout)
            if r.status_code == HTTPStatus.OK:
                self.wifi_available = True
                self.wifi_last_success = time.time()
                log.info("WiFi follower path verified (%s)", self.wifi_host)
            else:
                self.wifi_available = False
                log.warning("WiFi path returned status %d, followers will be skipped", r.status_code)
        except Exception as e:
            self.wifi_available = False
            log.warning("WiFi path unreachable (%s), followers will be skipped: %s", self.wifi_host, e)

    def _post_tedapi_wifi(self, pb_bytes: bytes, url_suffix: str = '/tedapi/v1') -> Optional[bytes]:
        """
        POST protobuf bytes via WiFi TEDAPI (used for follower queries in v1r mode).

        Args:
            pb_bytes: Serialized protobuf payload (full tedapi_pb2.Message).
            url_suffix: URL suffix (e.g., '/tedapi/v1' or '/tedapi/device/{din}/v1')

        Returns:
            Raw response content bytes, or None on error.
        """
        if not self.wifi_session:
            return None
        # Exponential backoff for follower WiFi failures (60s * 2^fail_count, max 128 min)
        # Use a lock so concurrent threads don't all increment fail_count simultaneously
        # and spike the backoff to maximum in one burst (issue #310).
        with self._wifi_lock:
            if self.wifi_cooldown > time.time():
                remaining = self.wifi_cooldown - time.time()
                log.debug("WiFi cooldown active (%.0fs remaining), skipping", remaining)
                return None
        # Re-test WiFi if previously unavailable and cooldown has expired
        if not self.wifi_available:
            self._test_wifi_path()
            if not self.wifi_available:
                with self._wifi_lock:
                    # Re-check cooldown: another thread may have set one while we tested
                    if self.wifi_cooldown <= time.time():
                        self.wifi_fail_count += 1
                        backoff = min(60 * (2 ** self.wifi_fail_count), 7680)  # caps at ~128 min
                        self.wifi_cooldown = time.time() + backoff
                        log.debug("WiFi unavailable, next retry in %.0fs (failure #%d)",
                                   backoff, self.wifi_fail_count)
                return None
        url = f'https://{self.wifi_host}{url_suffix}'
        try:
            r = self.wifi_session.post(url, data=pb_bytes, timeout=self.timeout)
            if r.status_code in BUSY_CODES:
                log.warning("WiFi TEDAPI rate limited, activating 60s cooldown")
                with self._wifi_lock:
                    if self.wifi_cooldown <= time.time():
                        self.wifi_fail_count += 1
                        self.wifi_cooldown = time.time() + 60
                return None
            if r.status_code != HTTPStatus.OK:
                log.error("WiFi TEDAPI error for %s: %s", url_suffix, r.status_code)
                with self._wifi_lock:
                    if self.wifi_cooldown <= time.time():
                        self.wifi_fail_count += 1
                        backoff = min(60 * (2 ** self.wifi_fail_count), 7680)
                        self.wifi_cooldown = time.time() + backoff
                self.wifi_available = False
                return None
            # Success — reset failure tracking
            self.wifi_available = True
            with self._wifi_lock:
                self.wifi_fail_count = 0
                self.wifi_last_success = time.time()
            return decompress_response(r.content)
        except Exception as e:
            log.error("WiFi TEDAPI request failed: %s", e)
            with self._wifi_lock:
                if self.wifi_cooldown <= time.time():
                    self.wifi_fail_count += 1
                    backoff = min(60 * (2 ** self.wifi_fail_count), 7680)
                    self.wifi_cooldown = time.time() + backoff
            self.wifi_available = False
            return None

    def connect(self, force=False):
        """Connect to the Powerwall Gateway and retrieve the DIN.

        If a DIN is already known and a session exists, this is a no-op that
        returns the cached DIN - startup used to reconnect up to 3 times
        (TEDAPI.__init__, PyPowerwallTEDAPI.__init__ and authenticate()).
        Pass force=True to tear down the session and reconnect.
        """
        if not force and self.din:
            if self.v1r or getattr(self, 'session', None) is not None:
                log.debug("Already connected to Powerwall Gateway - skipping reconnect")
                return self.din
        if self.v1r:
            return self._connect_v1r()
        # Test IP Connection to Powerwall Gateway
        log.debug(f"Testing Connection to Powerwall Gateway: {self.gw_ip}")
        url = f'https://{self.gw_ip}'
        self.din = None
        # Close any previous session before replacing it - reconnects used to
        # leak the old session's pooled connections
        old_session = getattr(self, 'session', None)
        if old_session is not None:
            try:
                old_session.close()
            except Exception as e:
                log.debug(f"Error closing previous session: {e}")
        self.session = self._init_session()
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != HTTPStatus.OK:
                # PW2/+ gateways serve their web portal on GET / (HTTP 200);
                # Powerwall 3 has no local web portal and responds with an
                # error (403/404 depending on firmware) - any non-200 means
                # PW3, EXCEPT transient/retryable codes (429/5xx), which must
                # not flip PW3 detection (a busy PW2 is still a PW2), so the
                # prior value is kept for those.
                if resp.status_code in BUSY_CODES or resp.status_code in RETRY_FORCE_CODES:
                    log.debug(f"Transient response {resp.status_code} from gateway - "
                              f"keeping PW3 detection as {self.pw3}")
                else:
                    log.debug("Detected Powerwall 3 Gateway")
                    self.pw3 = True
            self.din = self.get_din()
        except Exception as e:
            log.error(f"Unable to connect to Powerwall Gateway {self.gw_ip}")
            log.error("Please verify your your host has a route to the Gateway.")
            log.error(f"Error Details: {e}")
        return self.din

    def _connect_v1r(self):
        """Connect via v1r transport (RSA-signed LAN access)."""
        log.debug(f"v1r: Connecting to Powerwall Gateway: {self.gw_ip}")
        self.din = None
        self.pw3 = True  # v1r is PW3-only
        try:
            if not self.v1r_transport.login():
                log.error("v1r: Login failed")
                return None
            self.din = self.v1r_transport.get_din()
            if not self.din:
                log.error("v1r: Failed to get DIN")
                return None
            log.debug(f"v1r: Connected, DIN={self.din}")
            # On successful LAN connect, clear any prior failure state
            self.lan_failed = False
            self.lan_fail_count = 0
            self.lan_recover_after = 0
            # Test WiFi fallback path if configured
            if self.wifi_session:
                self._test_wifi_path()
        except Exception as e:
            log.error(f"v1r: Connection error: {e}")
        return self.din

    def close_session(self):
        """Close the underlying requests.Session objects to the Gateway."""
        for attr in ('session', 'wifi_session'):
            s = getattr(self, attr, None)
            if s is not None:
                try:
                    s.close()
                except Exception as e:
                    log.debug(f"Error closing {attr}: {e}")
        v1r_session = getattr(self.v1r_transport, 'session', None) if self.v1r_transport else None
        if v1r_session is not None:
            try:
                v1r_session.close()
            except Exception as e:
                log.debug(f"Error closing v1r session: {e}")

    def _build_signed_query_request(self, query, *, recipient_din: str = None,
                                    sender_din: str = None, tail: int = 1) -> bytes:
        """Build a june_2026 SIGNED GraphQL request: the energy_device
        MessageEnvelope (graphql.queryRequest, format=SIGNED) wrapped in the
        v2 transport Message + Tail. `query` is a june_2026 TEDAPIQuery whose
        signed_bytes/code carry the Tesla-signed SignedGraphQLQuery + signature.

        Returns full Message bytes (same shape as the legacy path); _post_tedapi
        extracts the bare envelope for v1r."""
        from .protobuf.june_2026 import tedapi_v2_transport_pb2 as tx
        from .protobuf.june_2026 import tedapi_v2_energy_device_pb2 as ed
        pb = tx.Message()
        pb.message.deliveryChannel = ed.DELIVERY_CHANNEL_LOCAL_HTTPS
        if sender_din:
            pb.message.sender.din = sender_din
        else:
            pb.message.sender.local = ed.LOCAL_PARTICIPANT_INSTALLER
        pb.message.recipient.din = recipient_din or self.din
        gq = pb.message.graphql.queryRequest
        gq.format = ed.GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1
        gq.query = query.signed_bytes
        gq.signature = query.code
        gq.variablesJson.value = query.b_value
        pb.tail.value = tail
        return pb.SerializeToString()

    def _parse_signed_query_response(self, response: bytes) -> Optional[str]:
        """Extract the JSON payload from a june_2026 GraphQLAPIQueryResponse.

        Basic mode returns a full transport Message; v1r returns a bare
        energy_device MessageEnvelope. Returns the JSON text, or None."""
        if not response:
            return None
        from .protobuf.june_2026 import tedapi_v2_transport_pb2 as tx
        from .protobuf.june_2026 import tedapi_v2_energy_device_pb2 as ed
        try:
            if self.v1r:
                env = ed.MessageEnvelope()
                env.ParseFromString(response)
            else:
                m = tx.Message()
                m.ParseFromString(response)
                env = m.message
        except Exception as e:
            log.error(f"Error parsing june_2026 response: {e}")
            return None
        resp = env.graphql.queryResponse
        if resp.errors:
            log.error("GraphQL errors: %s",
                      [(er.code, er.message) for er in resp.errors])
            # A june_2026 query carries a Tesla-signed SignedGraphQLQuery. If the
            # gateway rejects every query after a firmware update, Tesla has most
            # likely rotated the query signing keys and the bundled signatures no
            # longer validate. Point the user at the legacy fallback so a total
            # june_2026 outage is diagnosable rather than a silent empty payload.
            log.warning(
                "june_2026 signed query rejected by the gateway. If this persists "
                "after a firmware update, Tesla may have rotated the query signing "
                'keys; fall back with tedapi_api_version="june_2024" '
                "(CLI: -tedapi_api_version=june_2024)."
            )
        return resp.data or None

    def _post_tedapi(self, pb_bytes: bytes, din: str = None, url_suffix: str = '/tedapi/v1') -> Optional[bytes]:
        """
        Transport abstraction: POST protobuf bytes to the appropriate TEDAPI endpoint.

        WiFi mode: POST to /tedapi/v1 with HTTP Basic auth session.
        v1r mode:  Wrap in RSA-signed RoutableMessage and POST to /tedapi/v1r.

        Args:
            pb_bytes: Serialized protobuf payload. For WiFi: full tedapi_pb2.Message.
                      For v1r: can be either full Message or just MessageEnvelope bytes.
            din: DIN for v1r envelope (ignored in WiFi mode)
            url_suffix: URL suffix for WiFi mode (e.g., '/tedapi/v1' or '/tedapi/device/{din}/v1')

        Returns:
            Raw response content bytes, or None on error.
            For WiFi: the raw HTTP response body (protobuf)
            For v1r: the inner protobuf_message_as_bytes from the RoutableMessage response
        """
        if self.v1r:
            # ── LAN recovery probe ────────────────────────────────────────────
            # If LAN was marked failed but recovery window has passed, attempt
            # a reconnect before routing this request over WiFi.
            if self.lan_failed and time.time() >= self.lan_recover_after:
                log.info("v1r: LAN recovery window reached — attempting reconnect")
                if self._connect_v1r():  # clears lan_failed on success
                    log.info("v1r: LAN recovered — resuming wired transport")
                else:
                    # Still down — extend backoff and continue on WiFi
                    self.lan_fail_count += 1
                    backoff = min(60 * (2 ** self.lan_fail_count), 7680)
                    self.lan_recover_after = time.time() + backoff
                    log.warning("v1r: LAN still unreachable, next retry in %.0fs", backoff)

            # ── LAN failed → full WiFi TEDAPI v1 fallback ────────────────────
            if self.lan_failed:
                if not self.wifi_session:
                    log.error("v1r: LAN down and no WiFi fallback configured")
                    return None
                log.debug("v1r: LAN down — routing primary query via WiFi TEDAPI")
                return self._post_tedapi_wifi(pb_bytes, url_suffix)

            # ── Normal v1r LAN path ───────────────────────────────────────────
            # v1r requires just the MessageEnvelope bytes (NOT the full Message
            # wrapper with tail). Extract the envelope from the full Message.
            try:
                if self.tedapi_api_version == TEDAPIApiVersion.JUNE_2026:
                    # Parse with the v2 transport proto so the field-16 graphql
                    # payload survives the re-extract (legacy proto would drop it).
                    from .protobuf.june_2026 import tedapi_v2_transport_pb2 as _tx
                    msg = _tx.Message()
                else:
                    msg = tedapi_pb2.Message()
                msg.ParseFromString(pb_bytes)
                envelope_bytes = msg.message.SerializeToString()
            except Exception:
                # If parsing fails, assume pb_bytes is already envelope bytes
                envelope_bytes = pb_bytes
            # Always sign with leader DIN (self.din) — the RSA key is registered
            # on the leader only. The follower DIN is in the envelope's recipient
            # field for routing, but TLV personalization must match the leader.
            inner = self.v1r_transport.post_v1r(envelope_bytes, self.din)
            if inner is None:
                # LAN call failed — track for failover
                self.lan_fail_count += 1
                if self.lan_fail_count >= 3:
                    self.lan_failed = True
                    backoff = min(60 * (2 ** self.lan_fail_count), 7680)
                    self.lan_recover_after = time.time() + backoff
                    log.warning(
                        "v1r: LAN failed %d consecutive times — switching to WiFi TEDAPI fallback"
                        " (retry LAN in %.0fs)",
                        self.lan_fail_count, backoff
                    )
            else:
                # Successful LAN call — reset counter and record timestamp
                self.lan_fail_count = 0
                self.lan_last_success = time.time()
            return inner
        else:
            url = f'https://{self.gw_ip}{url_suffix}'
            r = self.session.post(url, data=pb_bytes, timeout=self.timeout)
            if r.status_code in BUSY_CODES:
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall - Activating 5 minute cooldown')
                return None
            if r.status_code != HTTPStatus.OK:
                log.error(f"Error posting to {url_suffix}: {r.status_code}")
                return None
            return decompress_response(r.content)

    def _parse_v1r_query_response(self, inner_bytes: bytes) -> Optional[str]:
        """
        Parse v1r query response to extract the JSON text payload.

        For v1r, the response is a MessageEnvelope (not a full Message with tail).
        The JSON payload is in envelope.payload.recv.text.
        """
        if not inner_bytes:
            return None
        # v1r returns MessageEnvelope directly (no outer Message wrapper)
        try:
            envelope = tedapi_pb2.MessageEnvelope()
            envelope.ParseFromString(inner_bytes)
            if envelope.HasField('payload'):
                return envelope.payload.recv.text
        except Exception:
            pass
        # Fallback: try as full Message
        try:
            resp = tedapi_pb2.Message()
            resp.ParseFromString(inner_bytes)
            return resp.message.payload.recv.text
        except Exception:
            pass
        # Last resort: find JSON in raw bytes
        try:
            text = inner_bytes.decode('utf-8', errors='replace')
            json_start = text.find('{')
            if json_start >= 0:
                depth = 0
                for i, ch in enumerate(text[json_start:], json_start):
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            return text[json_start:i + 1]
        except Exception as e:
            log.error(f"v1r response parse error: {e}")
        return None

    # Handy Function to access Powerwall Status
    def current_power(self, location: Optional[str] = None, force: bool = False) -> Optional[Union[float, Dict[str, float]]]:
        """
        Get the current power in watts for a specific location or all locations.
        Args:
            location: Power location to query. Valid values: BATTERY, SITE, LOAD,
                    SOLAR, SOLAR_RGM, GENERATOR, CONDUCTOR. Case-insensitive.
            force: Force refresh of status data
        Returns:
            If location specified: Real power in watts (float) or None if not found
            If no location: Dictionary mapping locations to power values
        """
        status = self.get_status(force=force)
        meter_aggregates = lookup(status, ['control', 'meterAggregates'])

        if not isinstance(meter_aggregates, list):
            return None

        # Create mapping of location -> power for efficiency
        power_map = {
            meter.get('location', '').upper(): meter.get('realPowerW')
            for meter in meter_aggregates
            if meter.get('location') is not None
        }

        if location is None:
            return power_map

        return power_map.get(location.upper())


    def backup_time_remaining(self, force=False):
        """Get the time remaining in hours."""
        status = self.get_status(force=force)
        nominalEnergyRemainingWh = lookup(status, ['control', 'systemStatus', 'nominalEnergyRemainingWh'])
        load = self.current_power('LOAD', force)
        if not nominalEnergyRemainingWh or not load:
            return None
        time_remaining = nominalEnergyRemainingWh / load
        return time_remaining


    def battery_level(self, force=False):
        """Get the battery level as a percentage."""
        status = self.get_status(force=force)
        nominalEnergyRemainingWh = lookup(status, ['control', 'systemStatus', 'nominalEnergyRemainingWh'])
        nominalFullPackEnergyWh = lookup(status, ['control', 'systemStatus', 'nominalFullPackEnergyWh'])
        if not nominalEnergyRemainingWh or not nominalFullPackEnergyWh:
            log.debug(f"battery_level: Missing battery data - remaining={nominalEnergyRemainingWh}, full={nominalFullPackEnergyWh}")
            return None
        battery_level = nominalEnergyRemainingWh / nominalFullPackEnergyWh * 100
        return battery_level


    # Helper Function
    def extract_fan_speeds(self, data) -> Dict[str, Dict[str, str]]:
        """Extract fan speed signals from device controller data."""
        if not isinstance(data, dict):
            return {}

        fan_speed_signal_names = {"PVAC_Fan_Speed_Actual_RPM", "PVAC_Fan_Speed_Target_RPM"}

        # List to store the valid fan speed values  
        result = {}

        # Iterate over each component in the "msa" list
        components = data.get("components", {})
        if isinstance(components, dict):
            for component in components.get("msa", []):
                signals = component.get("signals", [])
                fan_speeds = {
                    signal["name"]: signal["value"]
                    for signal in signals
                    if signal.get("name") in fan_speed_signal_names and signal.get("value") is not None
                }
                if not fan_speeds:
                    continue
                componentPartNumber = component.get("partNumber")
                componentSerialNumber = component.get("serialNumber")
                result[f"PVAC--{componentPartNumber}--{componentSerialNumber}"] = fan_speeds
        return result

    def get_fan_speeds(self, force=False):
        """Get the fan speeds for the Powerwall or inverter."""
        return self.extract_fan_speeds(self.get_device_controller(force=force))
      

    def derive_meter_config(self, config) -> dict:
        """Build a lookup dictionary for Neurio meter configuration from config."""
        # Build meter Lookup if available
        meter_config = {}
        if not "meters" in config:
            return meter_config
        # Loop through each meter and use device_serial as the key
        for meter in config['meters']:
            if meter.get('type') != "neurio_w2_tcp":
                continue
            device_serial = lookup(meter, ['connection', 'device_serial'])
            if not device_serial:
                continue
            # Check to see if we already have this meter in meter_config
            if device_serial in meter_config:
                cts = meter.get('cts', [False] * 4)
                if not isinstance(cts, list):
                    cts = [False] * 4
                for i, ct in enumerate(cts):
                    if not ct:
                        continue
                    meter_config[device_serial]['cts'][i] = True
                    meter_config[device_serial]['location'][i] = meter.get('location', "")
            else:
                # New meter, add to meter_config
                cts = meter.get('cts', [False] * 4)

                if not isinstance(cts, list):
                    cts = [False] * 4
                location = meter.get('location', "")
                meter_config[device_serial] = {
                    "type": meter.get('type'),
                    "location": [location] * 4,
                    "cts": cts,
                    "inverted": meter.get('inverted'),
                    "connection": meter.get('connection'),
                    "real_power_scale_factor": meter.get('real_power_scale_factor', 1)
                }
        return meter_config


    def aggregate_neurio_data(self, config_data, status_data, meter_config_data) -> Tuple[dict, dict]:
        """Aggregate Neurio data from status and config into flat and hierarchical forms."""
        # Create NEURIO block
        neurio_flat = {}
        neurio_hierarchy = {}
        # Loop through each Neurio device serial number
        for c, n in enumerate(lookup(status_data, ['neurio', 'readings']) or {}, start=1000):
            # Loop through each CT on the Neurio device
            sn = n.get('serial', str(c))
            cts_flat = {}
            for i, ct in enumerate(n['dataRead'] or {}):
                # Only show if we have a meter configuration and cts[i] is true
                cts_bool = lookup(meter_config_data, [sn, 'cts'])
                if isinstance(cts_bool, list) and i < len(cts_bool):
                    if not cts_bool[i]:
                        # Skip this CT
                        continue
                factor = lookup(meter_config_data, [sn, 'real_power_scale_factor']) or 1
                location = lookup(meter_config_data, [sn, 'location'])
                ct_hierarchy = {
                    "Index": i,
                    "InstRealPower": ct.get('realPowerW', 0) * factor,
                    "InstReactivePower": ct.get('reactivePowerVAR'),
                    "InstVoltage": ct.get('voltageV'),
                    "InstCurrent": ct.get('currentA'),
                    "Location": location[i] if location and len(location) > i else None
                }
                neurio_hierarchy[f"CT{i}"] = ct_hierarchy
                cts_flat.update({f"NEURIO_CT{i}_" + key: value for key, value in ct_hierarchy.items() if key != "Index"})
            meter_manufacturer = "NEURIO" if lookup(meter_config_data, [sn, "type"]) == "neurio_w2_tcp" else None
            rest = {
                "componentParentDin": lookup(config_data, ['vin']),
                "firmwareVersion": None,
                "lastCommunicationTime": lookup(n, ['timestamp']),
                "manufacturer": meter_manufacturer,
                "meterAttributes": {
                    "meterLocation": []
                },
                "serialNumber": sn
            }
            neurio_flat[f"NEURIO--{sn}"] = {**cts_flat, **rest}
        return (neurio_flat, neurio_hierarchy)

    # Vitals API Mapping Function
    def vitals(self, force=False):
        """Create a vitals API dictionary using TEDAPI data."""
        def calculate_ac_power(Vpeak, Ipeak):
            Vrms = Vpeak / math.sqrt(2)
            Irms = Ipeak / math.sqrt(2)
            power = Vrms * Irms
            return power

        def calculate_dc_power(V, I):
            power = V * I
            return power

        # status = self.get_status(force)
        config = self.get_config(force=force)
        status = self.get_device_controller(force=force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None

        # Create Header
        tesla = {}
        header = {}
        header["VITALS"] = {
            "text": "Device vitals generated from Tesla Powerwall Gateway TEDAPI",
            "timestamp": time.time(),
            "gateway": self.gw_ip,
            "pyPowerwall": __version__,
        }
        neurio = self.aggregate_neurio_data(
            config_data=config,
            status_data=status,
            meter_config_data=self.derive_meter_config(config)
        )[0]

        # Create PVAC, PVS, and TESLA blocks - Assume the are aligned
        pvac = {}
        pvs = {}
        tesla = {}
        num = len(lookup(status, ['esCan', 'bus', 'PVAC']) or {})
        if num != len(lookup(status, ['esCan', 'bus', 'PVS']) or {}):
            log.debug("PVAC and PVS device count mismatch in TEDAPI")
        # Loop through each device serial number
        fan_speeds = self.extract_fan_speeds(status)
        for i, p in enumerate(lookup(status, ['esCan', 'bus', 'PVAC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            pvac_name = f"PVAC--{packagePartNumber}--{packageSerialNumber}"
            pvac_logging = p['PVAC_Logging']
            V_A = pvac_logging['PVAC_PVMeasuredVoltage_A']
            V_B = pvac_logging['PVAC_PVMeasuredVoltage_B']
            V_C = pvac_logging['PVAC_PVMeasuredVoltage_C']
            V_D = pvac_logging['PVAC_PVMeasuredVoltage_D']
            I_A = pvac_logging['PVAC_PVCurrent_A']
            I_B = pvac_logging['PVAC_PVCurrent_B']
            I_C = pvac_logging['PVAC_PVCurrent_C']
            I_D = pvac_logging['PVAC_PVCurrent_D']
            P_A = calculate_dc_power(V_A, I_A)
            P_B = calculate_dc_power(V_B, I_B)
            P_C = calculate_dc_power(V_C, I_C)
            P_D = calculate_dc_power(V_D, I_D)
            pvac[pvac_name] = {
                "PVAC_Fout": lookup(p, ['PVAC_Status', 'PVAC_Fout']),
                "PVAC_GridState": None,
                "PVAC_InvState": None,
                "PVAC_Iout": None,
                "PVAC_LifetimeEnergyPV_Total": None,
                "PVAC_PVCurrent_A": I_A,
                "PVAC_PVCurrent_B": I_B,
                "PVAC_PVCurrent_C": I_C,
                "PVAC_PVCurrent_D": I_D,
                "PVAC_PVMeasuredPower_A": P_A, # computed
                "PVAC_PVMeasuredPower_B": P_B, # computed
                "PVAC_PVMeasuredPower_C": P_C, # computed
                "PVAC_PVMeasuredPower_D": P_D, # computed
                "PVAC_PVMeasuredVoltage_A": V_A,
                "PVAC_PVMeasuredVoltage_B": V_B,
                "PVAC_PVMeasuredVoltage_C": V_C,
                "PVAC_PVMeasuredVoltage_D": V_D,
                "PVAC_Pout": lookup(p, ['PVAC_Status', 'PVAC_Pout']),
                "PVAC_PvState_A": None, # These are placeholders
                "PVAC_PvState_B": None, # Compute from PVS below
                "PVAC_PvState_C": None, # PV_Disabled, PV_Active, PV_Active_Parallel
                "PVAC_PvState_D": None, # Not available in TEDAPI
                "PVAC_Qout": None,
                "PVAC_State": lookup(p, ['PVAC_Status', 'PVAC_State']),
                "PVAC_VHvMinusChassisDC": None,
                "PVAC_VL1Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL1Ground']),
                "PVAC_VL2Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL2Ground']),
                "PVAC_Vout": lookup(p, ['PVAC_Status', 'PVAC_Vout']),
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "PVI-PowerStatusSetpoint": None,
                "componentParentDin": None, # TODO: map to TETHC
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 296
                }
            }
            pvac_fans = fan_speeds.get(pvac_name, {})
            if pvac_fans:
                pvac[pvac_name].update({
                    "PVAC_Fan_Speed_Actual_RPM": pvac_fans["PVAC_Fan_Speed_Actual_RPM"],
                    "PVAC_Fan_Speed_Target_RPM": pvac_fans["PVAC_Fan_Speed_Target_RPM"]
                })

            pvs_name = f"PVS--{packagePartNumber}--{packageSerialNumber}"
            pvs_data = lookup(status, ['esCan', 'bus', 'PVS'])
            if i < len(pvs_data):
                pvs_data = pvs_data[i]
                # Set String Connected states
                string_a = lookup(pvs_data, ['PVS_Status', 'PVS_StringA_Connected'])
                string_b = lookup(pvs_data, ['PVS_Status', 'PVS_StringB_Connected'])
                string_c = lookup(pvs_data, ['PVS_Status', 'PVS_StringC_Connected'])
                string_d = lookup(pvs_data, ['PVS_Status', 'PVS_StringD_Connected'])
                # Set PVAC PvState based on PVS String Connected states
                pvac[pvac_name]["PVAC_PvState_A"] = "PV_Active" if string_a else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_B"] = "PV_Active" if string_b else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_C"] = "PV_Active" if string_c else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_D"] = "PV_Active" if string_d else "PV_Disabled"
                pvs[pvs_name] = {
                    "PVS_EnableOutput": None,
                    "PVS_SelfTestState": lookup(pvs_data, ['PVS_Status', 'PVS_SelfTestState']),
                    "PVS_State": lookup(pvs_data, ['PVS_Status', 'PVS_State']),
                    "PVS_StringA_Connected": string_a,
                    "PVS_StringB_Connected": string_b,
                    "PVS_StringC_Connected": string_c,
                    "PVS_StringD_Connected": string_d,
                    "PVS_vLL": lookup(pvs_data, ['PVS_Status', 'PVS_vLL']),
                    "alerts": lookup(pvs_data, ['alerts', 'active']) or [],
                    "componentParentDin": pvac_name,
                    "firmwareVersion": None,
                    "lastCommunicationTime": None,
                    "manufacturer": "TESLA",
                    "partNumber": packagePartNumber,
                    "serialNumber": packageSerialNumber,
                    "teslaEnergyEcuAttributes": {
                        "ecuType": 297
                    }
                }
            tesla_name = f"TESLA--{packagePartNumber}--{packageSerialNumber}"
            if "solars" in config and i < len(config.get('solars', [{}])):
                tesla_nameplate = config['solars'][i].get('power_rating_watts', None)
                brand = config['solars'][i].get('brand', None)
            else:
                tesla_nameplate = None
                brand = None
            tesla[tesla_name] = {
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": brand.upper() if brand else "TESLA",
                "pvInverterAttributes": {
                    "nameplateRealPowerW": tesla_nameplate,
                },
                "serialNumber": f"{packagePartNumber}--{packageSerialNumber}",
            }

        # Create STSTSM block
        name = f"STSTSM--{lookup(config, ['vin'])}"
        ststsm = {}
        ststsm[name] =  {
            "STSTSM-Location": "Gateway",
            "alerts": lookup(status, ['control', 'alerts', 'active']) or [],
            "firmwareVersion": None,
            "lastCommunicationTime": None,
            "manufacturer": "TESLA",
            "partNumber": lookup(config, ['vin']).split('--')[0],
            "serialNumber": lookup(config, ['vin']).split('--')[-1],
            "teslaEnergyEcuAttributes": {
                "ecuType": 207
            }
        }

        # Get Dictionary of Powerwall Temperatures
        temp_sensors = {}
        for i in lookup(status, ['components', 'msa']) or []:
            if "signals" in i and "serialNumber" in i and i["serialNumber"]:
                for s in i["signals"]:
                    if "name" in s and s["name"] == "THC_AmbientTemp" and "value" in s:
                        temp_sensors[i["serialNumber"]] = s["value"]

        # Create TETHC, TEPINV and TEPOD blocks
        tethc = {} # parent
        tepinv = {}
        tepod = {}
        # Loop through each THC device serial number
        for i, p in enumerate(lookup(status, ['esCan', 'bus', 'THC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # TETHC block
            parent_name = f"TETHC--{packagePartNumber}--{packageSerialNumber}"
            tethc[parent_name] = {
                "THC_AmbientTemp": temp_sensors.get(packageSerialNumber, None),
                "THC_State": None,
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 224
                }
            }
            # TEPOD block
            name = f"TEPOD--{packagePartNumber}--{packageSerialNumber}"
            # POD list can be missing or shorter than the THC list - default to {}
            pod_data = lookup(status, ['esCan', 'bus', 'POD']) or []
            pod = pod_data[i] if i < len(pod_data) else {}
            energy_remaining = lookup(pod, ['POD_EnergyStatus', 'POD_nom_energy_remaining'])
            full_pack_energy = lookup(pod, ['POD_EnergyStatus', 'POD_nom_full_pack_energy'])
            if energy_remaining and full_pack_energy:
                energy_to_be_charged = full_pack_energy - energy_remaining
            else:
                energy_to_be_charged = None
            tepod[name] = {
                "POD_ActiveHeating": None,
                "POD_CCVhold": None,
                "POD_ChargeComplete": None,
                "POD_ChargeRequest": None,
                "POD_DischargeComplete": None,
                "POD_PermanentlyFaulted": None,
                "POD_PersistentlyFaulted": None,
                "POD_available_charge_power": None,
                "POD_available_dischg_power": None,
                "POD_enable_line": None,
                "POD_nom_energy_remaining": energy_remaining,
                "POD_nom_energy_to_be_charged": energy_to_be_charged, #computed
                "POD_nom_full_pack_energy": full_pack_energy,
                "POD_state": None,
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "componentParentDin": parent_name,
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 226
                }
            }
            # TEPINV block
            name = f"TEPINV--{packagePartNumber}--{packageSerialNumber}"
            # PINV list can be missing or shorter than the THC list - default to {}
            pinv_data = lookup(status, ['esCan', 'bus', 'PINV']) or []
            pinv = pinv_data[i] if i < len(pinv_data) else {}
            tepinv[name] = {
                "PINV_EnergyCharged": None,
                "PINV_EnergyDischarged": None,
                "PINV_Fout": lookup(pinv, ['PINV_Status', 'PINV_Fout']),
                "PINV_GridState": lookup(pinv, ['PINV_Status', 'PINV_GridState']),
                "PINV_HardwareEnableLine": None,
                "PINV_PllFrequency": None,
                "PINV_PllLocked": None,
                "PINV_Pnom": lookup(pinv, ['PINV_PowerCapability', 'PINV_Pnom']),
                "PINV_Pout": lookup(pinv, ['PINV_Status', 'PINV_Pout']),
                "PINV_PowerLimiter": None,
                "PINV_Qout": None,
                "PINV_ReadyForGridForming": None,
                "PINV_State": lookup(pinv, ['PINV_Status', 'PINV_State']),
                "PINV_VSplit1": lookup(pinv, ['PINV_AcMeasurements', 'PINV_VSplit1']),
                "PINV_VSplit2": lookup(pinv, ['PINV_AcMeasurements', 'PINV_VSplit2']),
                "PINV_Vout": lookup(pinv, ['PINV_Status', 'PINV_Vout']),
                "alerts": lookup(pinv, ['alerts', 'active']) or [],
                "componentParentDin": parent_name,
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 253
                }
            }

        # Create TESYNC block
        tesync = {}
        sync = lookup(status, ['esCan', 'bus', 'SYNC']) or {}
        islander = lookup(status, ['esCan', 'bus', 'ISLANDER']) or {}
        packagePartNumber = sync.get('packagePartNumber', None)
        packageSerialNumber = sync.get('packageSerialNumber', None)
        # NOTE: these blocks are emitted even when the SYNC bus is absent and
        # the serial is None (typical PW3, yielding "TESYNC--None--None" /
        # "TESLA--None" names) - the TESLA block's componentParentDin
        # (STSTSM--<vin>) is the only place the gateway DIN/serial appears in
        # TEDAPI vitals and consumers depend on it. Frozen behavior - do not
        # guard these blocks on the serial number.
        name = f"TESYNC--{packagePartNumber}--{packageSerialNumber}"
        tesync[name] = {
            "ISLAND_FreqL1_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL1_Load']),
            "ISLAND_FreqL1_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL1_Main']),
            "ISLAND_FreqL2_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL2_Load']),
            "ISLAND_FreqL2_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL2_Main']),
            "ISLAND_FreqL3_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL3_Load']),
            "ISLAND_FreqL3_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL3_Main']),
            "ISLAND_GridConnected": lookup(islander, ['ISLAND_GridConnection', 'ISLAND_GridConnected']),
            "ISLAND_GridState": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_GridState']),
            "ISLAND_L1L2PhaseDelta":lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1L2PhaseDelta']),
            "ISLAND_L1L3PhaseDelta": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1L3PhaseDelta']),
            "ISLAND_L1MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1MicrogridOk']),
            "ISLAND_L2L3PhaseDelta": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L2L3PhaseDelta']),
            "ISLAND_L2MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L2MicrogridOk']),
            "ISLAND_L3MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L3MicrogridOk']),
            "ISLAND_PhaseL1_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL1_Main_Load']),
            "ISLAND_PhaseL2_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL2_Main_Load']),
            "ISLAND_PhaseL3_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL3_Main_Load']),
            "ISLAND_ReadyForSynchronization": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_ReadyForSynchronization']),
            "ISLAND_VL1N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL1N_Load']),
            "ISLAND_VL1N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL1N_Main']),
            "ISLAND_VL2N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL2N_Load']),
            "ISLAND_VL2N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL2N_Main']),
            "ISLAND_VL3N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL3N_Load']),
            "ISLAND_VL3N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL3N_Main']),
            "METER_X_CTA_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_I']),
            "METER_X_CTA_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_InstReactivePower']),
            "METER_X_CTA_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_InstRealPower']),
            "METER_X_CTB_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_I']),
            "METER_X_CTB_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_InstReactivePower']),
            "METER_X_CTB_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_InstRealPower']),
            "METER_X_CTC_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_I']),
            "METER_X_CTC_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_InstReactivePower']),
            "METER_X_CTC_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_InstRealPower']),
            "METER_X_LifetimeEnergyExport": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_LifetimeEnergyExport']),
            "METER_X_LifetimeEnergyImport": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_LifetimeEnergyImport']),
            "METER_X_VL1N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL1N']),
            "METER_X_VL2N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL2N']),
            "METER_X_VL3N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL3N']),
            "METER_Y_CTA_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_I']),
            "METER_Y_CTA_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_InstReactivePower']),
            "METER_Y_CTA_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_InstRealPower']),
            "METER_Y_CTB_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_I']),
            "METER_Y_CTB_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_InstReactivePower']),
            "METER_Y_CTB_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_InstRealPower']),
            "METER_Y_CTC_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_I']),
            "METER_Y_CTC_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_InstReactivePower']),
            "METER_Y_CTC_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_InstRealPower']),
            "METER_Y_LifetimeEnergyExport": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_LifetimeEnergyExport']),
            "METER_Y_LifetimeEnergyImport": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_LifetimeEnergyImport']),
            "METER_Y_VL1N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL1N']),
            "METER_Y_VL2N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL2N']),
            "METER_Y_VL3N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL3N']),
            "SYNC_ExternallyPowered": None,
            "SYNC_SiteSwitchEnabled": None,
            "alerts": lookup(sync, ['alerts', 'active']) or [],
            "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
            "firmwareVersion": None,
            "manufacturer": "TESLA",
            "partNumber": packagePartNumber,
            "serialNumber": packageSerialNumber,
            "teslaEnergyEcuAttributes": {
                "ecuType": 259
            }
        }

        # Create TEMSA block - Backup Switch
        temsa = {}
        msa = lookup(status, ['esCan', 'bus', 'MSA']) or {}
        packagePartNumber = msa.get('packagePartNumber', None)
        packageSerialNumber = msa.get('packageSerialNumber', None)

        # For Powerwall 3, MSA data comes from components.msa with signals format
        if not packageSerialNumber:
            for component in lookup(status, ['components', 'msa']) or []:
                if component.get('serialNumber') and any(
                    s.get('name', '').startswith('METER_Z') for s in component.get('signals', [])
                ):
                    packagePartNumber = component.get('partNumber')
                    packageSerialNumber = component.get('serialNumber')
                    # Convert signals array to dict keyed by name
                    signals_dict = {s['name']: s.get('value') for s in component.get('signals', []) if 'name' in s}
                    # Create a fake METER_Z_AcMeasurements structure for compatibility
                    # PW3 uses VL1G/VL2G (ground-ref), map to VL1N/VL2N for consistency
                    msa = {
                        'packagePartNumber': packagePartNumber,
                        'packageSerialNumber': packageSerialNumber,
                        'METER_Z_AcMeasurements': {
                            'METER_Z_CTA_I': signals_dict.get('METER_Z_CTA_I'),
                            'METER_Z_CTA_InstReactivePower': signals_dict.get('METER_Z_CTA_InstReactivePower'),
                            'METER_Z_CTA_InstRealPower': signals_dict.get('METER_Z_CTA_InstRealPower'),
                            'METER_Z_CTB_I': signals_dict.get('METER_Z_CTB_I'),
                            'METER_Z_CTB_InstReactivePower': signals_dict.get('METER_Z_CTB_InstReactivePower'),
                            'METER_Z_CTB_InstRealPower': signals_dict.get('METER_Z_CTB_InstRealPower'),
                            'METER_Z_CTC_I': signals_dict.get('METER_Z_CTC_I'),
                            'METER_Z_CTC_InstReactivePower': signals_dict.get('METER_Z_CTC_InstReactivePower'),
                            'METER_Z_CTC_InstRealPower': signals_dict.get('METER_Z_CTC_InstRealPower'),
                            'METER_Z_VL1N': signals_dict.get('METER_Z_VL1G'),
                            'METER_Z_VL2N': signals_dict.get('METER_Z_VL2G'),
                            'METER_Z_VL3N': signals_dict.get('METER_Z_VL3G'),
                            'METER_Z_LifetimeEnergyExport': signals_dict.get('METER_Z_LifetimeEnergyExport'),
                            'METER_Z_LifetimeEnergyImport': signals_dict.get('METER_Z_LifetimeEnergyImport'),
                        }
                    }
                    break

        if packageSerialNumber:
            name = f"TEMSA--{packagePartNumber}--{packageSerialNumber}"
            temsa[name] = {
                "METER_Z_CTA_I": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTA_I']),
                "METER_Z_CTA_InstReactivePower": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTA_InstReactivePower']),
                "METER_Z_CTA_InstRealPower": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTA_InstRealPower']),
                "METER_Z_CTB_I": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTB_I']),
                "METER_Z_CTB_InstReactivePower": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTB_InstReactivePower']),
                "METER_Z_CTB_InstRealPower": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTB_InstRealPower']),
                "METER_Z_CTC_I": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTC_I']),
                "METER_Z_CTC_InstReactivePower": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTC_InstReactivePower']),
                "METER_Z_CTC_InstRealPower": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_CTC_InstRealPower']),
                "METER_Z_LifetimeEnergyExport": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_LifetimeEnergyExport']),
                "METER_Z_LifetimeEnergyImport": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_LifetimeEnergyImport']),
                "METER_Z_VL1N": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_VL1N']),
                "METER_Z_VL2N": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_VL2N']),
                "METER_Z_VL3N": lookup(msa, ['METER_Z_AcMeasurements', 'METER_Z_VL3N']),
                "alerts": lookup(msa, ['alerts', 'active']) or [],
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 300
                }
            }

        # Create TESLA block - tied to TESYNC
        name = f"TESLA--{packageSerialNumber}"
        tesla[name] = {
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "meterAttributes": {
                    "meterLocation": [
                        1
                    ]
                },
                "serialNumber": packageSerialNumber
            }

        # Create Vitals Dictionary
        vitals = {
            **header,
            **neurio,
            **pvac,
            **pvs,
            **ststsm,
            **tepinv,
            **tepod,
            **tesla,
            **tesync,
            **tethc,
            **temsa,
        }
        # Merge in the Powerwall 3 data if available
        if self.pw3:
            pw3_data = self.get_pw3_vitals(force) or {}
            vitals.update(pw3_data)

        return vitals


    def get_blocks(self, force=False):
        """
        Get the list of battery blocks from the Powerwall Gateway.
        
        This includes both regular Powerwall units (with inverters) and battery 
        expansion packs (battery-only units without inverters).
        """
        vitals = self.vitals(force=force)
        if not isinstance(vitals, dict):
            return None
        block = {}

        # Walk through the vitals dictionary and create blocks for Powerwall units with inverters
        for key, _ in vitals.items():
            if key.startswith("TEPINV--"):
                # Extract the part and serial numbers from the key
                parts = key.split("--")
                if len(parts) < 3:
                    continue
                packagePartNumber = parts[1]
                packageSerialNumber = parts[2]
                name = f"{packagePartNumber}--{packageSerialNumber}"
                # Extract key information from TEPINV
                f_out = lookup(vitals, [key, 'PINV_Fout'])
                pinv_state = lookup(vitals, [key, 'PINV_State'])
                pinv_grid_state = lookup(vitals, [key, 'PINV_GridState'])
                p_out = lookup(vitals, [key, 'PINV_Pout'])
                v_out = lookup(vitals, [key, 'PINV_Vout'])
                block[name] = {
                    "Type": "",
                    "PackagePartNumber": packagePartNumber,
                    "PackageSerialNumber": packageSerialNumber,
                    "disabled_reasons": [],
                    "pinv_state": pinv_state,
                    "pinv_grid_state": pinv_grid_state,
                    "nominal_energy_remaining": None,
                    "nominal_full_pack_energy": None,
                    "p_out": p_out,
                    "q_out": None,
                    "v_out": v_out,
                    "f_out": f_out,
                    "i_out": None,
                    "energy_charged": None,
                    "energy_discharged": None,
                    "off_grid": None,
                    "vf_mode": None,
                    "wobble_detected": None,
                    "charge_power_clamped": None,
                    "backup_ready": None,
                    "OpSeqState": None,
                    "version": None
                }
                # See if there is a TEPOD block for this TEPINV
                tepod_key = f"TEPOD--{packagePartNumber}--{packageSerialNumber}"
                if tepod_key in vitals:
                    nominal_energy_remaining = lookup(vitals, [tepod_key, 'POD_nom_energy_remaining'])
                    nominal_full_pack_energy = lookup(vitals, [tepod_key, 'POD_nom_full_pack_energy'])
                    block[name].update({
                        "nominal_energy_remaining": nominal_energy_remaining,
                        "nominal_full_pack_energy": nominal_full_pack_energy,
                    })

        # Add battery expansion packs (battery-only units without inverters)
        # Expansion pack energy is now included in vitals() as TEPOD entries
        config = self.get_config(force=force)
        if config and 'battery_blocks' in config:
            for battery in config['battery_blocks']:
                if 'battery_expansions' in battery and battery['battery_expansions']:
                    for expansion in battery['battery_expansions']:
                        exp_din = expansion.get('din')
                        if not exp_din:
                            continue

                        # Extract part and serial from DIN (format: "1807000-10-B--TG125035000A5E")
                        exp_parts = exp_din.split('--')
                        if len(exp_parts) < 2:
                            log.debug(f"Skipping battery expansion with invalid DIN format: {exp_din}")
                            continue
                        exp_part = exp_parts[0]
                        exp_serial = exp_parts[1]
                        exp_name = exp_serial  # Use serial number as key

                        # Look up energy from vitals TEPOD entry
                        tepod_key = f"TEPOD--{exp_din}"
                        nominal_energy_remaining = lookup(vitals, [tepod_key, 'POD_nom_energy_remaining'])
                        nominal_full_pack_energy = lookup(vitals, [tepod_key, 'POD_nom_full_pack_energy'])

                        # Add expansion to blocks (expansions don't have inverter data)
                        block[exp_name] = {
                            "Type": "BatteryExpansion",
                            "PackagePartNumber": exp_part,
                            "PackageSerialNumber": exp_serial,
                            "disabled_reasons": [],
                            "pinv_state": None,
                            "pinv_grid_state": None,
                            "nominal_energy_remaining": nominal_energy_remaining,
                            "nominal_full_pack_energy": nominal_full_pack_energy,
                            "p_out": None,
                            "q_out": None,
                            "v_out": None,
                            "f_out": None,
                            "i_out": None,
                            "energy_charged": None,
                            "energy_discharged": None,
                            "off_grid": None,
                            "vf_mode": None,
                            "wobble_detected": None,
                            "charge_power_clamped": None,
                            "backup_ready": None,
                            "OpSeqState": None,
                            "version": None
                        }

        return block

    # End of TEDAPI Class

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
import datetime
import json
import logging
import os
import resource
import signal
import ssl
import sys
import time
from enum import StrEnum, auto
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any, Dict, Final, Optional, Set
from urllib.parse import parse_qs, urlparse

from transform import get_static, inject_js

import pypowerwall
from pypowerwall import parse_version

BUILD = "t67"

ALLOWLIST = Set[str] = set([
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
])

DISABLED = Set[str] = set([
    '/api/customer/registration',
])
WEB_ROOT: Final[str] = os.path.join(os.path.dirname(__file__), "web")



    # bind_address = os.getenv("PW_BIND_ADDRESS", "")
    # password = os.getenv("PW_PASSWORD", "")
    # email = os.getenv("PW_EMAIL", "email@example.com")
    # host = os.getenv("PW_HOST", "")
    # timezone = os.getenv("PW_TIMEZONE", "America/Los_Angeles")
    # debugmode = os.getenv("PW_DEBUG", "no").lower() == "yes"
    # cache_expire = int(os.getenv("PW_CACHE_EXPIRE", "5"))
    # browser_cache = int(os.getenv("PW_BROWSER_CACHE", "0"))
    # timeout = int(os.getenv("PW_TIMEOUT", "5"))
    # pool_maxsize = int(os.getenv("PW_POOL_MAXSIZE", "15"))
    # https_mode = os.getenv("PW_HTTPS", "no")
    # port = int(os.getenv("PW_PORT", "8675"))
    # style = os.getenv("PW_STYLE", "clear") + ".js"
    # siteid = os.getenv("PW_SITEID", None)
    # authpath = os.getenv("PW_AUTH_PATH", "")
    # authmode = os.getenv("PW_AUTH_MODE", "cookie")
    # cf = ".powerwall"
    # if authpath:
    #     cf = os.path.join(authpath, ".powerwall")
    # cachefile = os.getenv("PW_CACHE_FILE", cf)
    # control_secret = os.getenv("PW_CONTROL_SECRET", "")
    # gw_pwd = os.getenv("PW_GW_PWD", None)
    # neg_solar = os.getenv("PW_NEG_SOLAR", "yes").lower() == "yes"
    
class CONFIG_TYPE(StrEnum):
    """_summary_

    Args:
        StrEnum (_type_): _description_
    """
    PW_AUTH_MODE = auto()
    PW_AUTH_PATH = auto()
    PW_AUTH_PATH = auto()
    PW_BIND_ADDRESS = auto()
    PW_BROWSER_CACHE = auto()
    PW_CACHE_EXPIRE = auto()
    PW_CACHE_FILE = auto()
    PW_CONTROL_SECRET = auto()
    PW_COOKIE_SUFFIX = auto()
    PW_DEBUG = auto()
    PW_EMAIL = auto()
    PW_GW_PWD = auto()
    PW_HOST = auto()
    PW_HTTP_TYPE = auto()
    PW_HTTPS = auto()
    PW_NEG_SOLAR = auto()
    PW_PASSWORD = auto()
    PW_POOL_MAXSIZE = auto()
    PW_PORT = auto()
    PW_SITEID = auto()
    PW_STYLE = auto()
    PW_TIMEOUT = auto()
    PW_TIMEZONE = auto()

# Configuration for Proxy - Check for environmental variables
#    and always use those if available (required for Docker)
# Configuration - Environment variables
type PROXY_CONFIG = Dict[CONFIG_TYPE, str | int | bool | None]
CONFIG: PROXY_CONFIG = {
    CONFIG_TYPE.PW_AUTH_MODE: os.getenv(CONFIG_TYPE.PW_AUTH_MODE, "cookie"),
    CONFIG_TYPE.PW_AUTH_PATH: os.getenv(CONFIG_TYPE.PW_AUTH_PATH, ""),
    CONFIG_TYPE.PW_BIND_ADDRESS: os.getenv(CONFIG_TYPE.PW_BIND_ADDRESS, ""),
    CONFIG_TYPE.PW_BROWSER_CACHE: int(os.getenv(CONFIG_TYPE.PW_BROWSER_CACHE, "0")),
    CONFIG_TYPE.PW_CACHE_EXPIRE: int(os.getenv(CONFIG_TYPE.PW_CACHE_EXPIRE, "5")),
    CONFIG_TYPE.PW_CONTROL_SECRET: os.getenv(CONFIG_TYPE.PW_CONTROL_SECRET, ""),
    CONFIG_TYPE.PW_DEBUG: bool(os.getenv(CONFIG_TYPE.PW_DEBUG, "no").lower() == "yes"),
    CONFIG_TYPE.PW_EMAIL: os.getenv(CONFIG_TYPE.PW_EMAIL, "email@example.com"),
    CONFIG_TYPE.PW_GW_PWD: os.getenv(CONFIG_TYPE.PW_GW_PWD, None),
    CONFIG_TYPE.PW_HOST: os.getenv(CONFIG_TYPE.PW_HOST, ""),
    CONFIG_TYPE.PW_HTTPS: os.getenv(CONFIG_TYPE.PW_HTTPS, "no"),
    CONFIG_TYPE.PW_NEG_SOLAR: bool(os.getenv(CONFIG_TYPE.PW_NEG_SOLAR, "yes").lower() == "yes"),
    CONFIG_TYPE.PW_PASSWORD: os.getenv(CONFIG_TYPE.PW_PASSWORD, ""),
    CONFIG_TYPE.PW_POOL_MAXSIZE: int(os.getenv(CONFIG_TYPE.PW_POOL_MAXSIZE, "15")),
    CONFIG_TYPE.PW_PORT: int(os.getenv(CONFIG_TYPE.PW_PORT, "8675")),
    CONFIG_TYPE.PW_SITEID: os.getenv(CONFIG_TYPE.PW_SITEID, None),
    CONFIG_TYPE.PW_STYLE: os.getenv(CONFIG_TYPE.PW_STYLE, "clear") + ".js",
    CONFIG_TYPE.PW_TIMEOUT: int(os.getenv(CONFIG_TYPE.PW_TIMEOUT, "5")),
    CONFIG_TYPE.PW_TIMEZONE: os.getenv(CONFIG_TYPE.PW_TIMEZONE, "America/Los_Angeles")
}

# Cache file
CONFIG[CONFIG_TYPE.PW_CACHE_FILE] = os.getenv(
    CONFIG_TYPE.PW_CACHE_FILE,
    os.path.join(CONFIG[CONFIG_TYPE.PW_AUTH_PATH], ".powerwall") if CONFIG[CONFIG_TYPE.PW_AUTH_PATH] else ".powerwall"
)

# HTTP/S configuration
if CONFIG[CONFIG_TYPE.PW_HTTPS].lower() == "yes":
    CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX] = "path=/;SameSite=None;Secure;"
    CONFIG[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTPS"
elif CONFIG[CONFIG_TYPE.PW_HTTPS].lower() == "http":
    CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX] = "path=/;SameSite=None;Secure;"
    CONFIG[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTP"
else:
    CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX] = "path=/;"
    CONFIG[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTP"

# Logging configuration
log = logging.getLogger("proxy")
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
log.setLevel(logging.DEBUG if CONFIG[CONFIG_TYPE.PW_DEBUG] else logging.INFO)

if CONFIG[CONFIG_TYPE.PW_DEBUG]:
    pypowerwall.set_debug(True)

# Signal handler - Exit on SIGTERM
# noinspection PyUnusedLocal
def sig_term_handle(signum, frame):
    raise SystemExit

signal.signal(signal.SIGTERM, sig_term_handle)


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


# Global Stats
proxystats: Dict[PROXY_STATS_TYPE, str | int | bool | None | Dict[Any, Any]] = {
    PROXY_STATS_TYPE.CF: CONFIG[CONFIG_TYPE.PW_CACHE_FILE],
    PROXY_STATS_TYPE.CLEAR: int(time.time()),
    PROXY_STATS_TYPE.CLOUDMODE: False,
    PROXY_STATS_TYPE.CONFIG: CONFIG.copy(),
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

log.info(
    f"pyPowerwall [{pypowerwall.version}] Proxy Server [{BUILD}] - {CONFIG[CONFIG_TYPE.PW_HTTP_TYPE]} Port {CONFIG['PW_PORT']}{' - DEBUG' if CONFIG[CONFIG_TYPE.PW_DEBUG] else ''}"
)
log.info("pyPowerwall Proxy Started")

# Check for cache expire time limit below 5s
if CONFIG['PW_CACHE_EXPIRE'] < 5:
    log.warning(f"Cache expiration set below 5s (PW_CACHE_EXPIRE={CONFIG['PW_CACHE_EXPIRE']})")

# Get Value Function - Key to Value or Return Null
def get_value(a, key):
    value = a.get(key)
    if value is None:
        log.debug(f"Missing key in payload [{key}]")
    return value

site_name = pw.site_name() or "Unknown"
if pw.cloudmode or pw.fleetapi:
    if pw.fleetapi:
        proxystats[PROXY_STATS_TYPE.MODE] = "FleetAPI"
        log.info("pyPowerwall Proxy Server - FleetAPI Mode")
    else:
        proxystats[PROXY_STATS_TYPE.MODE] = "Cloud"
        log.info("pyPowerwall Proxy Server - Cloud Mode")
    log.info(f"Connected to Site ID {pw.client.siteid} ({site_name.strip()})")
    if CONFIG[CONFIG_TYPE.PW_SITEID] is not None and CONFIG[CONFIG_TYPE.PW_SITEID] != str(pw.client.siteid):
        log.info("Switch to Site ID %s" % CONFIG[CONFIG_TYPE.PW_SITEID])
        if not pw.client.change_site(CONFIG[CONFIG_TYPE.PW_SITEID]):
            log.error("Fatal Error: Unable to connect. Please fix config and restart.")
            while True:
                try:
                    time.sleep(5)  # Infinite loop to keep container running
                except (KeyboardInterrupt, SystemExit):
                    sys.exit(0)
else:
    proxystats[PROXY_STATS_TYPE.MODE] = "Local"
    log.info("pyPowerwall Proxy Server - Local Mode")
    log.info(f"Connected to Energy Gateway {CONFIG[CONFIG_TYPE.PW_HOST]} ({site_name.strip()})")
    if pw.tedapi:
        proxystats[PROXY_STATS_TYPE.TEDAPI] = True
        proxystats[PROXY_STATS_TYPE.TEDAPI_MODE] = pw.tedapi_mode
        proxystats[PROXY_STATS_TYPE.PW3] = pw.tedapi.pw3
        log.info(f"TEDAPI Mode Enabled for Device Vitals ({pw.tedapi_mode})")

def configure_pw_control(pw):
    if not CONFIG[CONFIG_TYPE.PW_CONTROL_SECRET]:
        return None

    log.info("Control Commands Activating - WARNING: Use with caution!")
    try:
        if pw.cloudmode or pw.fleetapi:
            pw_control = pw
        else:
            pw_control = pypowerwall.Powerwall(
                "",
                CONFIG['PW_PASSWORD'],
                CONFIG['PW_EMAIL'],
                siteid=CONFIG['PW_SITEID'],
                authpath=CONFIG['PW_AUTH_PATH'],
                authmode=CONFIG['PW_AUTH_MODE'],
                cachefile=CONFIG['PW_CACHE_FILE'],
                auto_select=True
            )
    except Exception as e:
        log.error("Control Mode Failed: Unable to connect to cloud - Run Setup")
        CONFIG[CONFIG_TYPE.PW_CONTROL_SECRET] = None
        return None

    if pw_control:
        log.info(f"Control Mode Enabled: Cloud Mode ({pw_control.mode}) Connected")
    else:
        log.error("Control Mode Failed: Unable to connect to cloud - Run Setup")
        CONFIG[CONFIG_TYPE.PW_CONTROL_SECRET] = None
        return None

    return pw_control

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# pylint: disable=arguments-differ,global-variable-not-assigned
# noinspection PyPep8Naming
class Handler(BaseHTTPRequestHandler):
    def log_message(self, log_format, *args):
        if CONFIG[CONFIG_TYPE.PW_DEBUG]:
            log.debug("%s %s" % (self.address_string(), log_format % args))

    def address_string(self):
        # replace function to avoid lookup delays
        hostaddr, hostport = self.client_address[:2]
        return hostaddr
    
    def send_json_response(self, data, status_code=HTTPStatus.OK, content_type='application/json'):
        response = json.dumps(data)
        try:
            self.send_response(status_code)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(response)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode("utf8"))
        except Exception as exc:
            log.debug("Error sending response: %s", exc)

    def do_POST(self):
        global proxystats
        contenttype = 'application/json'
        message = '{"error": "Invalid Request"}'
        if self.path.startswith('/control'):
            # curl -X POST -d "value=20&token=1234" http://localhost:8675/control/reserve
            # curl -X POST -d "value=backup&token=1234" http://localhost:8675/control/mode
            message = None
            if not CONFIG[CONFIG_TYPE.PW_CONTROL_SECRET]:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                try:
                    action = urlparse(self.path).path.split('/')[2]
                    post_data = self.rfile.read(int(self.headers['Content-Length']))
                    query_params = parse_qs(post_data.decode('utf-8'))
                    value = query_params.get('value', [''])[0]
                    token = query_params.get('token', [''])[0]
                except Exception as er:
                    message = '{"error": "Control Command Error: Invalid Request"}'
                    log.error(f"Control Command Error: {er}")
                if not message:
                    # Check if unable to connect to cloud
                    if pw_control.client is None:
                        message = '{"error": "Control Command Error: Unable to connect to cloud mode - Run Setup"}'
                        log.error("Control Command Error: Unable to connect to cloud mode - Run Setup")
                    else:
                        if token == CONFIG[CONFIG_TYPE.PW_CONTROL_SECRET]:
                            if action == 'reserve':
                                # ensure value is an integer
                                if not value:
                                    # return current reserve level in json string
                                    message = '{"reserve": %s}' % pw_control.get_reserve()
                                elif value.isdigit():
                                    message = json.dumps(pw_control.set_reserve(int(value)))
                                    log.info(f"Control Command: Set Reserve to {value}")
                                else:
                                    message = '{"error": "Control Command Value Invalid"}'
                            elif action == 'mode':
                                if not value:
                                    # return current mode in json string
                                    message = '{"mode": "%s"}' % pw_control.get_mode()
                                elif value in ['self_consumption', 'backup', 'autonomous']:
                                    message = json.dumps(pw_control.set_mode(value))
                                    log.info(f"Control Command: Set Mode to {value}")
                                else:
                                    message = '{"error": "Control Command Value Invalid"}'
                            else:
                                message = '{"error": "Invalid Command Action"}'
                        else:
                            message = '{"unauthorized": "Control Command Token Invalid"}'
        if "error" in message:
            self.send_response(HTTPStatus.BAD_REQUEST)
            proxystats[PROXY_STATS_TYPE.ERRORS] += 1
        elif "unauthorized" in message:
            self.send_response(HTTPStatus.UNAUTHORIZED)
        else:
            self.send_response(HTTPStatus.OK)
            proxystats[PROXY_STATS_TYPE.POSTS] += 1
        self.send_header('Content-type', contenttype)
        self.send_header('Content-Length', str(len(message)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(message.encode("utf8"))

    def do_GET(self):
        """Handle GET requests."""
        proxystats[PROXY_STATS_TYPE.GETS] += 1
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Map paths to handler functions
        path_handlers = {
            '/aggregates': self.handle_aggregates,
            '/api/meters/aggregates': self.handle_aggregates,
            '/soe': self.handle_soe,
            '/api/system_status/soe': self.handle_soe_scaled,
            '/api/system_status/grid_status': self.handle_grid_status,
            '/csv': self.handle_csv,
            '/vitals': self.handle_vitals,
            '/strings': self.handle_strings,
            '/stats': self.handle_stats,
            '/stats/clear': self.handle_stats_clear,
            '/temps': self.handle_temps,
            '/temps/pw': self.handle_temps_pw,
            '/alerts': self.handle_alerts,
            '/alerts/pw': self.handle_alerts_pw,
            '/freq': self.handle_freq,
            '/pod': self.handle_pod,
            '/version': self.handle_version,
            '/help': self.handle_help,
            '/api/troubleshooting/problems': self.handle_problems,
        }
        
        if path in path_handlers:
            path_handlers[path]()
        elif path in DISABLED:
            self.send_json_response(
                {"status": "404 Response - API Disabled"},
                status_code=HTTPStatus.NOT_FOUND
            )
        elif path in ALLOWLIST:
            self.handle_allowlist(path)
        elif path.startswith('/tedapi'):
            self.handle_tedapi(path)
        elif path.startswith('/cloud'):
            self.handle_cloud(path)
        elif path.startswith('/fleetapi'):
            self.handle_fleetapi(path)
        else:
            self.handle_static_content()

    def handle_aggregates(self):
        # Meters - JSON
        aggregates = pw.poll('/api/meters/aggregates')
        if not CONFIG[CONFIG_TYPE.PW_NEG_SOLAR] and aggregates and 'solar' in aggregates:
            solar = aggregates['solar']
            if solar and 'instant_power' in solar and solar['instant_power'] < 0:
                solar['instant_power'] = 0
                # Shift energy from solar to load
                if 'load' in aggregates and 'instant_power' in aggregates['load']:
                    aggregates['load']['instant_power'] -= solar['instant_power']
        self.send_json_response(aggregates)

    
    def handle_soe(self):
        soe = pw.poll('/api/system_status/soe', jsonformat=True)
        self.send_json_response(json.loads(soe))
        
    def handle_soe(self):
        soe = pw.poll('/api/system_status/soe', jsonformat=True)
        self.send_json_response(json.loads(soe))

    def handle_grid_status(self):
        grid_status = pw.poll('/api/system_status/grid_status', jsonformat=True)
        self.send_json_response(json.loads(grid_status))

    def handle_csv(self):
        # Grid,Home,Solar,Battery,Level - CSV
        contenttype = 'text/plain; charset=utf-8'
        batterylevel = pw.level() or 0
        grid = pw.grid() or 0
        solar = pw.solar() or 0
        battery = pw.battery() or 0
        home = pw.home() or 0
        if not CONFIG[CONFIG_TYPE.PW_NEG_SOLAR] and solar < 0:
            solar = 0
            # Shift energy from solar to load
            home -= solar
        message = f"{grid:.2f},{home:.2f},{solar:.2f},{battery:.2f},{batterylevel:.2f}\n"
        self.send_json_response(message)
        
    def handle_vitals(self):
        vitals = pw.vitals(jsonformat=True) or {}
        self.send_json_response(json.loads(vitals))

    def handle_strings(self):
        strings = pw.strings(jsonformat=True) or {}
        self.send_json_response(json.loads(strings))
        
    def handle_stats(self):
        proxystats.update({
            PROXY_STATS_TYPE.TS: int(time.time()),
            PROXY_STATS_TYPE.UPTIME: str(datetime.timedelta(seconds=(proxystats[PROXY_STATS_TYPE.TS] - proxystats[PROXY_STATS_TYPE.START]))),
            PROXY_STATS_TYPE.MEM: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            PROXY_STATS_TYPE.SITE_NAME: pw.site_name(),
            PROXY_STATS_TYPE.CLOUDMODE: pw.cloudmode,
            PROXY_STATS_TYPE.FLEETAPI: pw.fleetapi,
            PROXY_STATS_TYPE.AUTH_MODE: pw.authmode
        })
        if (pw.cloudmode or pw.fleetapi) and pw.client:
            proxystats[PROXY_STATS_TYPE.SITEID] = pw.client.siteid
            proxystats[PROXY_STATS_TYPE.COUNTER] = pw.client.counter
        self.send_json_response(proxystats)

    def handle_stats_clear(self):
        # Clear Internal Stats
        log.debug("Clear internal stats")
        proxystats.update({
            PROXY_STATS_TYPE.GETS: 0,
            PROXY_STATS_TYPE.ERRORS: 0,
            PROXY_STATS_TYPE.URI: {},
            PROXY_STATS_TYPE.CLEAR: int(time.time()),
        })
        self.send_json_response(proxystats)

    def handle_temps(self):
        temps = pw.temps(jsonformat=True) or {}
        self.send_json_response(json.loads(temps))
        
    def handle_temps_pw(self):
        temps = pw.temps() or {}
        pw_temp = {f"PW{idx}_temp": temp for idx, temp in enumerate(temps.values(), 1)}
        self.send_json_response(pw_temp)
        
    def handle_alerts(self):
        alerts = pw.alerts(jsonformat=True) or []
        self.send_json_response(alerts)

    def handle_alerts_pw(self):
        alerts = pw.alerts() or []
        pw_alerts = {alert: 1 for alert in alerts}
        self.send_json_response(pw_alerts)
        
    def handle_freq(self):
        fcv = {}
        system_status = pw.system_status() or {}
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
        vitals = pw.vitals() or {}
        for idx, (device, data) in enumerate(vitals.items()):
            if device.startswith('TEPINV'):
                fcv.update({
                    f"PW{idx}_name": device,
                    f"PW{idx}_PINV_Fout": get_value(data, 'PINV_Fout'),
                    f"PW{idx}_PINV_VSplit1": get_value(data, 'PINV_VSplit1'),
                    f"PW{idx}_PINV_VSplit2": get_value(data, 'PINV_VSplit2')    
                })
            if device.startswith(('TESYNC', 'TEMSA')):
                fcv.update({key: value for key, value in data.items() if key.startswith(('ISLAND', 'METER'))})
        fcv["grid_status"] = pw.grid_status(type="numeric")
        self.send_json_response(fcv)

    def handle_pod(self):
        # Powerwall Battery Data
        pod = {}
        # Get Individual Powerwall Battery Data
        system_status = pw.system_status() or {}
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

        vitals = pw.vitals() or {}
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
            "time_remaining_hours": pw.get_time_remaining(),
            "backup_reserve_percent": pw.get_reserve()
        })
        self.send_json_response(pod)

    def handle_version(self):
        version = pw.version()
        r = {"version": "SolarOnly", "vint": 0} if version is None else {"version": version, "vint": parse_version(version)}
        self.send_json_response(r)

        elif self.path == '/help':
            # Display friendly help screen link and stats
            proxystats[PROXY_STATS_TYPE.TS] = int(time.time())
            delta = proxystats[PROXY_STATS_TYPE.TS] - proxystats[PROXY_STATS_TYPE.START]
            proxystats[PROXY_STATS_TYPE.UPTIME] = str(datetime.timedelta(seconds=delta))
            proxystats[PROXY_STATS_TYPE.MEM] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            proxystats[PROXY_STATS_TYPE.SITE_NAME] = pw.site_name()
            proxystats[PROXY_STATS_TYPE.CLOUDMODE] = pw.cloudmode
            proxystats[PROXY_STATS_TYPE.FLEETAPI] = pw.fleetapi
            if (pw.cloudmode or pw.fleetapi) and pw.client is not None:
                proxystats[PROXY_STATS_TYPE.SITEID] = pw.client.siteid
                proxystats[PROXY_STATS_TYPE.COUNTER] = pw.client.counter
            proxystats[PROXY_STATS_TYPE.AUTH_MODE] = pw.authmode
            contenttype = 'text/html'
            message: str = """
            <html>\n<head><meta http-equiv="refresh" content="5" />\n
            <style>p, td, th { font-family: Helvetica, Arial, sans-serif; font-size: 10px;}</style>\n
            <style>h1 { font-family: Helvetica, Arial, sans-serif; font-size: 20px;}</style>\n
            </head>\n<body>\n<h1>pyPowerwall [%VER%] Proxy [%BUILD%] </h1>\n\n
            <p><a href="https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md">
            Click here for API help.</a></p>\n\n
            <table>\n<tr><th align ="left">Stat</th><th align ="left">Value</th></tr>
            """
            message = message.replace('%VER%', pypowerwall.version).replace('%BUILD%', BUILD)
            for i in proxystats:
                if i != PROXY_STATS_TYPE.URI and i != PROXY_STATS_TYPE.CONFIG:
                    message += f'<tr><td align="left">{i}</td><td align ="left">{proxystats[i]}</td></tr>\n'
            for i in proxystats[PROXY_STATS_TYPE.URI]:
                message += f'<tr><td align="left">URI: {i}</td><td align ="left">{proxystats[PROXY_STATS_TYPE.URI][i]}</td></tr>\n'
            message += """
            <tr>
                <td align="left">Config:</td>
                <td align="left">
                    <details id="config-details">
                        <summary>Click to view</summary>
                        <table>
            """
            for i in proxystats[PROXY_STATS_TYPE.CONFIG]:
                message += f'<tr><td align="left">{i}</td><td align ="left">{proxystats[PROXY_STATS_TYPE.CONFIG][i]}</td></tr>\n'
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
        elif self.path == '/api/troubleshooting/problems':
            # Simulate old API call and respond with empty list
            message = '{"problems": []}'
            # message = pw.poll('/api/troubleshooting/problems') or '{"problems": []}'
        elif self.path.startswith('/tedapi'):
            # TEDAPI Specific Calls
            if pw.tedapi:
                message = '{"error": "Use /tedapi/config, /tedapi/status, /tedapi/components, /tedapi/battery, /tedapi/controller"}'
                if self.path == '/tedapi/config':
                    message = json.dumps(pw.tedapi.get_config())
                if self.path == '/tedapi/status':
                    message = json.dumps(pw.tedapi.get_status())
                if self.path == '/tedapi/components':
                    message = json.dumps(pw.tedapi.get_components())
                if self.path == '/tedapi/battery':
                    message = json.dumps(pw.tedapi.get_battery_blocks())
                if self.path == '/tedapi/controller':
                    message = json.dumps(pw.tedapi.get_device_controller())
            else:
                message = '{"error": "TEDAPI not enabled"}'
        elif self.path.startswith('/cloud'):
            # Cloud API Specific Calls
            if pw.cloudmode and not pw.fleetapi:
                message = '{"error": "Use /cloud/battery, /cloud/power, /cloud/config"}'
                if self.path == '/cloud/battery':
                    message = json.dumps(pw.client.get_battery())
                if self.path == '/cloud/power':
                    message = json.dumps(pw.client.get_site_power())
                if self.path == '/cloud/config':
                    message = json.dumps(pw.client.get_site_config())
            else:
                message = '{"error": "Cloud API not enabled"}'
        elif self.path.startswith('/fleetapi'):
            # FleetAPI Specific Calls
            if pw.fleetapi:
                message = '{"error": "Use /fleetapi/info, /fleetapi/status"}'
                if self.path == '/fleetapi/info':
                    message = json.dumps(pw.client.get_site_info())
                if self.path == '/fleetapi/status':
                    message = json.dumps(pw.client.get_live_status())
            else:
                message = '{"error": "FleetAPI not enabled"}'
        elif self.path in DISABLED:
            # Disabled API Calls
            message = '{"status": "404 Response - API Disabled"}'
        elif self.path in ALLOWLIST:
            # Allowed API Calls - Proxy to Powerwall
            message: str = pw.poll(self.path, jsonformat=True)
        elif self.path.startswith('/control/reserve'):
            # Current battery reserve level
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"reserve": %s}' % pw_control.get_reserve()
        elif self.path.startswith('/control/mode'):
            # Current operating mode
            if not pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"mode": "%s"}' % pw_control.get_mode()
        else:
            # Everything else - Set auth headers required for web application
            proxystats[PROXY_STATS_TYPE.GETS] += 1
            if pw.authmode == "token":
                # Create bogus cookies
                self.send_header("Set-Cookie", f"AuthCookie=1234567890;{CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
                self.send_header("Set-Cookie", f"UserRecord=1234567890;{CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
            else:
                self.send_header("Set-Cookie", f"AuthCookie={pw.client.auth['AuthCookie']};{CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
                self.send_header("Set-Cookie", f"UserRecord={pw.client.auth['UserRecord']};{CONFIG[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")

            # Serve static assets from web root first, if found.
            # pylint: disable=attribute-defined-outside-init
            if self.path == "/" or self.path == "":
                self.path = "/index.html"
                fcontent, ftype = get_static(WEB_ROOT, self.path)
                # Replace {VARS} with current data
                status = pw.status()
                # convert fcontent to string
                fcontent = fcontent.decode("utf-8")
                # fix the following variables that if they are None, return ""
                fcontent = fcontent.replace("{VERSION}", status["version"] or "")
                fcontent = fcontent.replace("{HASH}", status["git_hash"] or "")
                fcontent = fcontent.replace("{EMAIL}", CONFIG[CONFIG_TYPE.PW_EMAIL])
                fcontent = fcontent.replace("{STYLE}", CONFIG[CONFIG_TYPE.PW_STYLE])
                # convert fcontent back to bytes
                fcontent = bytes(fcontent, 'utf-8')
            else:
                fcontent, ftype = get_static(WEB_ROOT, self.path)
            if fcontent:
                log.debug("Served from local web root: {} type {}".format(self.path, ftype))
            # If not found, serve from Powerwall web server
            elif pw.cloudmode or pw.fleetapi:
                log.debug("Cloud Mode - File not found: {}".format(self.path))
                fcontent = bytes("Not Found", 'utf-8')
                ftype = "text/plain"
            else:
                # Proxy request to Powerwall web server.
                proxy_path = self.path
                if proxy_path.startswith("/"):
                    proxy_path = proxy_path[1:]
                pw_url = f"https://{pw.host}/{proxy_path}"
                log.debug(f"Proxy request to: {pw_url}")
                try:
                    if pw.authmode == "token":
                        r = pw.client.session.get(
                            url=pw_url,
                            headers=pw.auth,
                            verify=False,
                            stream=True,
                            timeout=pw.timeout
                        )
                    else:
                        r = pw.client.session.get(
                            url=pw_url,
                            cookies=pw.auth,
                            verify=False,
                            stream=True,
                            timeout=pw.timeout
                        )
                    fcontent = r.content
                    ftype = r.headers['content-type']
                except AttributeError:
                    # Display 404
                    log.debug("File not found: {}".format(self.path))
                    fcontent = bytes("Not Found", 'utf-8')
                    ftype = "text/plain"

            # Allow browser caching, if user permits, only for CSS, JavaScript and PNG images...
            if CONFIG[CONFIG_TYPE.PW_BROWSER_CACHE] > 0 and (ftype == 'text/css' or ftype == 'application/javascript' or ftype == 'image/png'):
                self.send_header("Cache-Control", "max-age={}".format(CONFIG[CONFIG_TYPE.PW_BROWSER_CACHE]))
            else:
                self.send_header("Cache-Control", "no-cache, no-store")

                # Inject transformations
            if self.path.split('?')[0] == "/":
                if os.path.exists(os.path.join(WEB_ROOT, CONFIG[CONFIG_TYPE.PW_STYLE])):
                    fcontent = bytes(inject_js(fcontent, CONFIG[CONFIG_TYPE.PW_STYLE]), 'utf-8')

            self.send_header('Content-type', '{}'.format(ftype))
            self.end_headers()
            try:
                self.wfile.write(fcontent)
            except Exception as exc:
                if "Broken pipe" in str(exc):
                    log.debug(f"Client disconnected before payload sent [doGET]: {exc}")
                    return
                log.error(f"Error occured while sending PROXY response to client [doGET]: {exc}")
            return

        # Count
        if message is None:
            proxystats[PROXY_STATS_TYPE.TIMEOUT] += 1
            message = "TIMEOUT!"
        elif message == "ERROR!":
            proxystats[PROXY_STATS_TYPE.ERRORS] += 1
            message = "ERROR!"
        else:
            proxystats[PROXY_STATS_TYPE.GETS] += 1
            if self.path in proxystats[PROXY_STATS_TYPE.URI]:
                proxystats[PROXY_STATS_TYPE.URI][self.path] += 1
            else:
                proxystats[PROXY_STATS_TYPE.URI][self.path] = 1

        # Send headers and payload
        try:
            self.send_header('Content-type', contenttype)
            self.send_header('Content-Length', str(len(message)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(message.encode("utf8"))
        except Exception as exc:
            log.debug(f"Socket broken sending API response to client [doGET]: {exc}")

if __name__ == '__main__':
    # Connect to Powerwall
    # TODO: Add support for multiple Powerwalls
    try:
        pw = pypowerwall.Powerwall(
            host=CONFIG[CONFIG_TYPE.PW_HOST],
            password=CONFIG[CONFIG_TYPE.PW_PASSWORD],
            email=CONFIG[CONFIG_TYPE.PW_EMAIL],
            timezone=CONFIG[CONFIG_TYPE.PW_TIMEZONE],
            cache_expire=CONFIG[CONFIG_TYPE.PW_CACHE_EXPIRE],
            timeout=CONFIG[CONFIG_TYPE.PW_TIMEOUT],
            pool_maxsize=CONFIG[CONFIG_TYPE.PW_POOL_MAXSIZE],
            siteid=CONFIG[CONFIG_TYPE.PW_SITEID],
            authpath=CONFIG[CONFIG_TYPE.PW_AUTH_PATH],
            authmode=CONFIG[CONFIG_TYPE.PW_AUTH_MODE],
            cachefile=CONFIG[CONFIG_TYPE.PW_CACHE_FILE],
            auto_select=True,
            retry_modes=True,
            gw_pwd=CONFIG[CONFIG_TYPE.PW_GW_PWD]
        )
    except Exception as e:
        log.error(e)
        log.error("Fatal Error: Unable to connect. Please fix config and restart.")
        while True:
            try:
                time.sleep(5)  # Infinite loop to keep container running
            except (KeyboardInterrupt, SystemExit):
                sys.exit(0)

    pw_control = configure_pw_control(pw)

    # noinspection PyTypeChecker
    with ThreadingHTTPServer((CONFIG[CONFIG_TYPE.PW_BIND_ADDRESS], CONFIG[CONFIG_TYPE.PW_PORT]), Handler) as server:
        if CONFIG[CONFIG_TYPE.PW_HTTPS] == "yes":
            # Activate HTTPS
            log.debug("Activating HTTPS")
            # pylint: disable=deprecated-method
            server.socket = ssl.wrap_socket(
                server.socket,
                certfile=os.path.join(os.path.dirname(__file__), 'localhost.pem'),
                server_side=True,
                ssl_version=ssl.PROTOCOL_TLSv1_2,
                ca_certs=None,
                do_handshake_on_connect=True
            )

        # noinspection PyBroadException
        try:
            server.serve_forever()
        except (Exception, KeyboardInterrupt, SystemExit):
            print(' CANCEL \n')

        log.info("pyPowerwall Proxy Stopped")
        sys.exit(0)

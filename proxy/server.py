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
import threading
from enum import StrEnum, auto
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Final, Set, List, Tuple
from urllib.parse import parse_qs, urlparse
from pathlib import Path

from transform import get_static, inject_js

import pypowerwall
from pypowerwall import parse_version

BUILD: Final[str] = "t67"
UTF_8: Final[str] = "utf-8"

ALLOWLIST = Final[Set[str]] = set([
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

DISABLED = Final[Set[str]] = set([
    '/api/customer/registration',
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


class CONFIGURATION_SOURCE(StrEnum):
    ENVIRONMENT_VARIABLES = auto()
    CONFIGURATION_FILE = auto()


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

# Configuration for Proxy - Check for environmental variables
#    and always use those if available (required for Docker)
# Configuration - Environment variables
type PROXY_CONFIG = Dict[CONFIG_TYPE, str | int | bool | None]
type PROXY_STATS = Dict[PROXY_STATS_TYPE, str | int | bool | None | PROXY_CONFIG | Dict[str, int]]

# Get Value Function - Key to Value or Return Null
def get_value(a, key):
    value = a.get(key)
    if value is None:
        log.debug(f"Missing key in payload [{key}]")
    return value


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
                configuration['PW_PASSWORD'],
                configuration['PW_EMAIL'],
                siteid=configuration['PW_SITEID'],
                authpath=configuration['PW_AUTH_PATH'],
                authmode=configuration['PW_AUTH_MODE'],
                cachefile=configuration['PW_CACHE_FILE'],
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
    def __init__(self, *args, configuration: PROXY_CONFIG, pw: pypowerwall.Powerwall, pw_control: pypowerwall.Powerwall, **kwargs):
        self.configuration = configuration
        self.pw = pw
        self.pw_control = pw_control

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
        self.proxystats = proxystats

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

        super().__init__(*args, **kwargs)

    def log_message(self, log_format, *args):
        if self.configuration[CONFIG_TYPE.PW_DEBUG]:
            log.debug(f"{self.address_string()} {log_format % args}")

    def address_string(self):
        # replace function to avoid lookup delays
        hostaddr, hostport = self.client_address[:2]
        return hostaddr

    def send_json_response(self, data, status_code=HTTPStatus.OK, content_type='application/json') -> bool:
        response = json.dumps(data)
        try:
            self.send_response(status_code)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(response)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.wfile.write(response.encode(UTF_8)) > 0:
                return True
        except Exception as exc:
            log.debug(f"Error sending response: {exc}")
            self.proxystats[PROXY_STATS_TYPE.ERRORS] += 1
        return False


    def handle_control_post(self) -> bool:
        """Handle control POST requests."""
        if not self.pw_control:
            self.proxystats[PROXY_STATS_TYPE.ERRORS] += 1
            self.send_json_response(
                {"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"},
                status_code=HTTPStatus.BAD_REQUEST
            )
            return False

        try:
            action = urlparse(self.path).path.split('/')[2]
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

        if token != self.configuration['PW_CONTROL_SECRET']:
            self.send_json_response(
                {"unauthorized": "Control Command Token Invalid"},
                status_code=HTTPStatus.UNAUTHORIZED
            )
            return False

        if action == 'reserve':
            if not value:
                self.send_json_response({"reserve": self.pw_control.get_reserve()})
                return True
            elif value.isdigit():
                result = self.pw_control.set_reserve(int(value))
                log.info(f"Control Command: Set Reserve to {value}")
                self.send_json_response(result)
                return True
            else:
                self.send_json_response(
                    {"error": "Control Command Value Invalid"},
                    status_code=HTTPStatus.BAD_REQUEST
                )
        elif action == 'mode':
            if not value:
                self.send_json_response({"mode": self.pw_control.get_mode()})
                return True
            elif value in ['self_consumption', 'backup', 'autonomous']:
                result = self.pw_control.set_mode(value)
                log.info(f"Control Command: Set Mode to {value}")
                self.send_json_response(result)
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
            stat = PROXY_STATS_TYPE.POSTS if self.handle_control_post() else PROXY_STATS_TYPE.ERRORS
            self.proxystats[stat] += 1
        else:
            self.send_json_response(
                {"error": "Invalid Request"},
                status_code=HTTPStatus.BAD_REQUEST
            )


    def do_GET(self):
        """Handle GET requests."""
        self.proxystats[PROXY_STATS_TYPE.GETS] += 1
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
        elif self.path.startswith('/control/reserve'):
            # Current battery reserve level
            if not self.pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"reserve": %s}' % self.pw_control.get_reserve()
            self.send_json_response(json.loads(message))
        elif self.path.startswith('/control/mode'):
            # Current operating mode
            if not self.pw_control:
                message = '{"error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable"}'
            else:
                message = '{"mode": "%s"}' % self.pw_control.get_mode()
            self.send_json_response(json.loads(message))
        else:
            self.handle_static_content()

            # # Count
    # if message is None:
    #     proxystats[PROXY_STATS_TYPE.TIMEOUT] += 1
    #     message = "TIMEOUT!"
    # elif message == "ERROR!":
    #     proxystats[PROXY_STATS_TYPE.ERRORS] += 1
    #     message = "ERROR!"
    # else:
    #     proxystats[PROXY_STATS_TYPE.GETS] += 1
    #     if self.path in proxystats[PROXY_STATS_TYPE.URI]:
    #         proxystats[PROXY_STATS_TYPE.URI][self.path] += 1
    #     else:
    #         proxystats[PROXY_STATS_TYPE.URI][self.path] = 1

    def handle_aggregates(self):
        # Meters - JSON
        aggregates = self.pw.poll('/api/meters/aggregates')
        if not self.configuration[CONFIG_TYPE.PW_NEG_SOLAR] and aggregates and 'solar' in aggregates:
            solar = aggregates['solar']
            if solar and 'instant_power' in solar and solar['instant_power'] < 0:
                solar['instant_power'] = 0
                # Shift energy from solar to load
                if 'load' in aggregates and 'instant_power' in aggregates['load']:
                    aggregates['load']['instant_power'] -= solar['instant_power']
        self.send_json_response(aggregates)


    def handle_soe(self) -> bool:
        soe = self.pw.poll('/api/system_status/soe', jsonformat=True)
        return self.send_json_response(json.loads(soe))


    def handle_soe_scaled(self) -> bool:
        level = self.pw.level(scale=True)
        return self.send_json_response({"percentage": level})


    def handle_grid_status(self):
        grid_status = self.pw.poll('/api/system_status/grid_status', jsonformat=True)
        self.send_json_response(json.loads(grid_status))


    def handle_csv(self):
        # Grid,Home,Solar,Battery,Level - CSV
        batterylevel = self.pw.level() or 0
        grid = self.pw.grid() or 0
        solar = self.pw.solar() or 0
        battery = self.pw.battery() or 0
        home = self.pw.home() or 0
        if not self.configuration[CONFIG_TYPE.PW_NEG_SOLAR] and solar < 0:
            solar = 0
            # Shift energy from solar to load
            home -= solar
        message = f"{grid:.2f},{home:.2f},{solar:.2f},{battery:.2f},{batterylevel:.2f}\n"
        self.send_json_response(message)


    def handle_vitals(self):
        vitals = self.pw.vitals(jsonformat=True) or {}
        self.send_json_response(json.loads(vitals))


    def handle_strings(self):
        strings = self.pw.strings(jsonformat=True) or {}
        self.send_json_response(json.loads(strings))


    def handle_stats(self):
        self.proxystats.update({
            PROXY_STATS_TYPE.TS: int(time.time()),
            PROXY_STATS_TYPE.UPTIME: str(datetime.timedelta(seconds=(self.proxystats[PROXY_STATS_TYPE.TS] - self.proxystats[PROXY_STATS_TYPE.START]))),
            PROXY_STATS_TYPE.MEM: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            PROXY_STATS_TYPE.SITE_NAME: self.pw.site_name(),
            PROXY_STATS_TYPE.CLOUDMODE: self.pw.cloudmode,
            PROXY_STATS_TYPE.FLEETAPI: self.pw.fleetapi,
            PROXY_STATS_TYPE.AUTH_MODE: self.pw.authmode
        })
        if (self.pw.cloudmode or self.pw.fleetapi) and self.pw.client:
            self.proxystats[PROXY_STATS_TYPE.SITEID] = self.pw.client.siteid
            self.proxystats[PROXY_STATS_TYPE.COUNTER] = self.pw.client.counter
        self.send_json_response(self.proxystats)


    def handle_stats_clear(self):
        # Clear Internal Stats
        log.debug("Clear internal stats")
        self.proxystats.update({
            PROXY_STATS_TYPE.GETS: 0,
            PROXY_STATS_TYPE.ERRORS: 0,
            PROXY_STATS_TYPE.URI: {},
            PROXY_STATS_TYPE.CLEAR: int(time.time()),
        })
        self.send_json_response(self.proxystats)


    def handle_temps(self):
        temps = self.pw.temps(jsonformat=True) or {}
        self.send_json_response(json.loads(temps))


    def handle_temps_pw(self):
        temps = self.pw.temps() or {}
        pw_temp = {f"PW{idx}_temp": temp for idx, temp in enumerate(temps.values(), 1)}
        self.send_json_response(pw_temp)


    def handle_alerts(self):
        alerts = self.pw.alerts(jsonformat=True) or []
        self.send_json_response(alerts)


    def handle_alerts_pw(self):
        alerts = self.pw.alerts() or []
        pw_alerts = {alert: 1 for alert in alerts}
        self.send_json_response(pw_alerts)


    def handle_freq(self):
        fcv = {}
        system_status = self.pw.system_status() or {}
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
        vitals = self.pw.vitals() or {}
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
        fcv["grid_status"] = self.pw.grid_status(type="numeric")
        self.send_json_response(fcv)


    def handle_pod(self):
        # Powerwall Battery Data
        pod = {}
        # Get Individual Powerwall Battery Data
        system_status = self.pw.system_status() or {}
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

        vitals = self.pw.vitals() or {}
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
            "time_remaining_hours": self.pw.get_time_remaining(),
            "backup_reserve_percent": self.pw.get_reserve()
        })
        self.send_json_response(pod)


    def handle_version(self):
        version = self.pw.version()
        r = {"version": "SolarOnly", "vint": 0} if version is None else {"version": version, "vint": parse_version(version)}
        self.send_json_response(r)


    def handle_help(self):
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        # Display friendly help screen link and stats

        self.proxystats.update({
            PROXY_STATS_TYPE.TS: int(time.time()),
            PROXY_STATS_TYPE.UPTIME: str(datetime.timedelta(seconds=int(time.time()) - self.proxystats[PROXY_STATS_TYPE.START])),
            PROXY_STATS_TYPE.MEM: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            PROXY_STATS_TYPE.SITE_NAME: self.pw.site_name(),
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
        self.wfile.write(message.encode(UTF_8))


    def handle_problems(self):
        self.send_json_response({"problems": []})

    def handle_allowlist(self, path) -> bool:
        response = self.pw.poll(path, jsonformat=True)
        return self.send_json_response(json.loads(response))

    def handle_tedapi(self, path):
        if not self.pw.tedapi:
            self.send_json_response({"error": "TEDAPI not enabled"}, status_code=HTTPStatus.BAD_REQUEST)
            return

        commands = {
            '/tedapi/config': self.pw.tedapi.get_config,
            '/tedapi/status': self.pw.tedapi.get_status,
            '/tedapi/components': self.pw.tedapi.get_components,
            '/tedapi/battery': self.pw.tedapi.get_battery_blocks,
            '/tedapi/controller': self.pw.tedapi.get_device_controller,
        }
        command = commands.get(path)
        if command:
            self.send_json_response(command())
        else:
            self.send_json_response(
                {"error": "Use /tedapi/config, /tedapi/status, /tedapi/components, /tedapi/battery, /tedapi/controller"},
                status_code=HTTPStatus.BAD_REQUEST
            )


    def handle_cloud(self, path):
        if not self.pw.cloudmode or self.pw.fleetapi:
            self.send_json_response({"error": "Cloud API not enabled"}, status_code=HTTPStatus.BAD_REQUEST)
            return

        commands = {
            '/cloud/battery': self.pw.client.get_battery,
            '/cloud/power': self.pw.client.get_site_power,
            '/cloud/config': self.pw.client.get_site_config,
        }
        command = commands.get(path)
        if command:
            self.send_json_response(command())
        else:
            self.send_json_response({"error": "Use /cloud/battery, /cloud/power, /cloud/config"}, status_code=HTTPStatus.BAD_REQUEST)


    def handle_fleetapi(self, path):
        if not self.pw.fleetapi:
            self.send_json_response({"error": "FleetAPI not enabled"}, status_code=HTTPStatus.BAD_REQUEST)
            return

        commands = {
            '/fleetapi/info': self.pw.client.get_site_info,
            '/fleetapi/status': self.pw.client.get_live_status,
        }
        command = commands.get(path)
        if command:
            self.send_json_response(command())
        else:
            self.send_json_response({"error": "Use /fleetapi/info, /fleetapi/status"}, status_code=HTTPStatus.BAD_REQUEST)


    def handle_static_content(self):
        self.proxystats[PROXY_STATS_TYPE.GETS] += 1
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-type', 'text/html')
        if self.pw.authmode == "token":
            self.send_header("Set-Cookie", f"AuthCookie=1234567890;{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
            self.send_header("Set-Cookie", f"UserRecord=1234567890;{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
        else:
            auth = self.pw.client.auth
            self.send_header("Set-Cookie", f"AuthCookie={auth['AuthCookie']};{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")
            self.send_header("Set-Cookie", f"UserRecord={auth['UserRecord']};{self.configuration[CONFIG_TYPE.PW_COOKIE_SUFFIX]}")

        if self.path == "/" or self.path == "":
            self.path = "/index.html"
            content, content_type = get_static(WEB_ROOT, self.path)
            status = self.pw.status()
            content = content.decode(UTF_8).format(
                VERSION=status.get("version", ""),
                HASH=status.get("git_hash", ""),
                EMAIL=self.configuration['PW_EMAIL'],
                STYLE=self.configuration['PW_STYLE'],
            ).encode(UTF_8)
        else:
            content, content_type = get_static(WEB_ROOT, self.path)

        if content:
            log.debug("Served from local web root: {} type {}".format(self.path, content_type))
        # If not found, serve from Powerwall web server
        elif self.pw.cloudmode or self.pw.fleetapi:
            log.debug(f"Cloud Mode - File not found: {self.path}")
            content = b"Not Found"
            content_type = "text/plain"
        else:
            # Proxy request to Powerwall web server.
            pw_url = f"https://{self.pw.host}/{self.path.lstrip('/')}"
            log.debug("Proxy request to: %s", pw_url)
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
                content_type = response.headers.get('content-type', 'text/html')
            except Exception as exc:
                log.error("Error proxying request: %s", exc)
                content = b"Error during proxy"
                content_type = "text/plain"

        if self.configuration['PW_BROWSER_CACHE'] > 0 and content_type in ['text/css', 'application/javascript', 'image/png']:
            self.send_header("Cache-Control", f"max-age={self.configuration[CONFIG_TYPE.PW_BROWSER_CACHE]}")
        else:
            self.send_header("Cache-Control", "no-cache, no-store")

        if self.path.split('?')[0] == "/":
            if os.path.exists(os.path.join(WEB_ROOT, self.configuration[CONFIG_TYPE.PW_STYLE])):
                content = bytes(inject_js(content, self.configuration[CONFIG_TYPE.PW_STYLE]), UTF_8)

        self.send_header('Content-type', content_type)
        self.end_headers()
        try:
            self.wfile.write(content)
        except Exception as exc:
            if "Broken pipe" in str(exc):
                log.debug(f"Client disconnected before payload sent [doGET]: {exc}")
                return
            log.error(f"Error occured while sending PROXY response to client [doGET]: {exc}")


def read_env_config() -> PROXY_CONFIG:
    config: PROXY_CONFIG = {
        CONFIG_TYPE.PW_AUTH_MODE: os.getenv(CONFIG_TYPE.PW_AUTH_MODE, "cookie"),
        CONFIG_TYPE.PW_AUTH_PATH: os.getenv(CONFIG_TYPE.PW_AUTH_PATH, ""),
        CONFIG_TYPE.PW_BIND_ADDRESS: os.getenv(CONFIG_TYPE.PW_BIND_ADDRESS, ""),
        CONFIG_TYPE.PW_BROWSER_CACHE: int(os.getenv(CONFIG_TYPE.PW_BROWSER_CACHE, "0")),
        CONFIG_TYPE.PW_CACHE_EXPIRE: int(os.getenv(CONFIG_TYPE.PW_CACHE_EXPIRE, "5")),
        CONFIG_TYPE.PW_CONTROL_SECRET: os.getenv(CONFIG_TYPE.PW_CONTROL_SECRET, ""),
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
        CONFIG_TYPE.PW_TIMEZONE: os.getenv(CONFIG_TYPE.PW_TIMEZONE, "America/Los_Angeles"),
        CONFIG_TYPE.PW_CACHE_FILE: os.getenv(CONFIG_TYPE.PW_CACHE_FILE, "")
    }
    return config


def read_config_file(file_path: Path) -> List[PROXY_CONFIG]:
    configs: List[PROXY_CONFIG] = []
    current_config: PROXY_CONFIG = {}

    # Read the file and parse lines
    try:
        with file_path.open('r') as file:
            for line in file:
                # Ignore comments and empty lines
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Detect new configuration block
                if line.startswith("[Powerwall"):
                    if current_config:
                        configs.append(current_config)
                    current_config = {}

                # Split key and value
                elif "=" in line:
                    key, value = line.split("=", 1)
                    def aggressive_strip(v: str) -> str:
                        return v.strip().strip("'").strip('"')
                    key, value = aggressive_strip(key), aggressive_strip(value)

                    # Ensure the key is valid
                    if not hasattr(CONFIG_TYPE, key):
                        print(f"Warning: Invalid configuration key '{key}' ignored.")
                        continue

                    # Handle boolean values
                    if value.lower() in ["yes", "no"]:
                        value = value.lower() == "yes"

                    # Assign to current configuration dictionary
                    current_config[key] = value

            # Add the last configuration block
            if current_config:
                configs.append(current_config)
    except FileNotFoundError:
        print(f"Configuration file '{file_path}' not found.")
        
import yaml

#WIP, loading configuration as yaml.


# powerwalls:
#   powerwall_1:                      # Configuration for Powerwall 1
#     PW_AUTH_MODE: "cookie"          # Authentication mode, default is "cookie"
#     PW_AUTH_PATH: ""                # Path for authentication, default is empty
#     PW_BIND_ADDRESS: ""             # Address to bind, default is empty
#     PW_BROWSER_CACHE: 0             # Enable browser cache: 0 = disabled, 1 = enabled
#     PW_CACHE_EXPIRE: 5              # Cache expiration in minutes
#     PW_CONTROL_SECRET: ""           # Secret key for secure control
#     PW_EMAIL: "email1@example.com"  # Email address for notifications
#     PW_GW_PWD: null                 # Gateway password (if required)
#     PW_HOST: "192.168.1.10"         # Host address of the Tesla Powerwall
#     PW_HTTPS: "no"                  # Use HTTPS (yes/no)
#     PW_NEG_SOLAR: true              # Allow negative solar values (true/false)
#     PW_PASSWORD: ""                 # Password for authentication
#     PW_POOL_MAXSIZE: 15             # Maximum size of the connection pool
#     PW_PORT: 8675                   # Port number for the connection
#     PW_SITEID: "site_1"             # Site ID (if required)
#     PW_STYLE: "clear.js"            # JavaScript file for UI style
#     PW_TIMEOUT: 5                   # Connection timeout in seconds
#     PW_TIMEZONE: "America/Los_Angeles" # Default timezone
#     PW_CACHE_FILE: ""               # Path to cache file

#   powerwall_2:                      # Configuration for Powerwall 2
#     PW_AUTH_MODE: "cookie"
#     PW_AUTH_PATH: ""
#     PW_BIND_ADDRESS: ""
#     PW_BROWSER_CACHE: 0
#     PW_CACHE_EXPIRE: 5
#     PW_CONTROL_SECRET: ""
#     PW_EMAIL: "email2@example.com"
#     PW_GW_PWD: null
#     PW_HOST: "192.168.1.11"
#     PW_HTTPS: "no"
#     PW_NEG_SOLAR: true
#     PW_PASSWORD: ""
#     PW_POOL_MAXSIZE: 15
#     PW_PORT: 8675
#     PW_SITEID: "site_2"
#     PW_STYLE: "clear.js"
#     PW_TIMEOUT: 5
#     PW_TIMEZONE: "America/New_York"
#     PW_CACHE_FILE: ""

#   powerwall_3:                      # Configuration for Powerwall 3
#     PW_AUTH_MODE: "cookie"
#     PW_AUTH_PATH: ""
#     PW_BIND_ADDRESS: ""
#     PW_BROWSER_CACHE: 0
#     PW_CACHE_EXPIRE: 5
#     PW_CONTROL_SECRET: ""
#     PW_EMAIL: "email3@example.com"
#     PW_GW_PWD: null
#     PW_HOST: "192.168.1.12"
#     PW_HTTPS: "no"
#     PW_NEG_SOLAR: true
#     PW_PASSWORD: ""
#     PW_POOL_MAXSIZE: 15
#     PW_PORT: 8675
#     PW_SITEID: "site_3"
#     PW_STYLE: "clear.js"
#     PW_TIMEOUT: 5
#     PW_TIMEZONE: "Europe/London"
#     PW_CACHE_FILE: ""

def load_powerwall_config(file_path):
    """
    Loads a YAML configuration file with multiple Powerwall configurations 
    into a list of dictionaries.

    Args:
        file_path (str): Path to the YAML configuration file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a Powerwall configuration.
    """
    try:
        with open(file_path, 'r') as file:
            # Load the YAML data
            config = yaml.safe_load(file)
        
        # Convert the named sections to a list of dictionaries
        powerwalls = config.get('powerwalls', {})
        return [
            {"name": name, **details}
            for name, details in powerwalls.items()
        ]
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return []

# Example usage
if __name__ == "__main__":
    file_path = "powerwall_config.yaml"  # Replace with your YAML file path
    powerwall_list = load_powerwall_config(file_path)
    for powerwall in powerwall_list:
        print(powerwall)


def build_configuration() -> List[PROXY_CONFIG]:
    COOKIE_SUFFIX: Final[str] = "path=/;SameSite=None;Secure;"
    configuration_source: Final[CONFIGURATION_SOURCE] = CONFIGURATION_SOURCE(os.getenv("PW_CONFIGURATION_SOURCE", CONFIGURATION_SOURCE.ENVIRONMENT_VARIABLES))
    configs: List[PROXY_CONFIG] = []

    if configuration_source == CONFIGURATION_SOURCE.ENVIRONMENT_VARIABLES:
        configs.append(read_env_config())
    elif configuration_source == CONFIGURATION_SOURCE.CONFIGURATION_FILE:
        configs.extend(read_config_file(Path("pypowerwall.env")))
    else:
        log.error("Configuration source misconfigured. This should never happen.")
        exit(0)

    for config in configs:
        # HTTP/S configuration
        if config[CONFIG_TYPE.PW_HTTPS].lower() == "yes":
            config[CONFIG_TYPE.PW_COOKIE_SUFFIX] = COOKIE_SUFFIX
            config[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTPS"
        elif config[CONFIG_TYPE.PW_HTTPS].lower() == "http":
            config[CONFIG_TYPE.PW_COOKIE_SUFFIX] = COOKIE_SUFFIX
            config[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTP"
        else:
            config[CONFIG_TYPE.PW_COOKIE_SUFFIX] = "path=/;"
            config[CONFIG_TYPE.PW_HTTP_TYPE] = "HTTP"

        if config[CONFIG_TYPE.PW_CACHE_FILE] == "":
            config[CONFIG_TYPE.PW_CACHE_FILE] = os.path.join(config[CONFIG_TYPE.PW_AUTH_PATH], ".powerwall") if config[CONFIG_TYPE.PW_AUTH_PATH] else ".powerwall"

        # Check for cache expire time limit below 5s
        if config['PW_CACHE_EXPIRE'] < 5:
            log.warning(f"Cache expiration set below 5s for host:port={config[CONFIG_TYPE.PW_HOST]}:{config[CONFIG_TYPE.PW_PORT]} (PW_CACHE_EXPIRE={config[CONFIG_TYPE.PW_CACHE_EXPIRE]})")

    return configs


def run_server(host, port, handler, enable_https=False):
    with ThreadingHTTPServer((host, port), handler) as server:
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
            server.serve_forever()
        except (Exception, KeyboardInterrupt, SystemExit):
            log.info(f"Server on {host}:{port} stopped")
            sys.exit(0)


def main() -> None:
    servers: List[Tuple[PROXY_CONFIG, threading.Thread]] = []
    configs = build_configuration()

    for config in configs:
        try:
            pw = pypowerwall.Powerwall(
                host=config[CONFIG_TYPE.PW_HOST],
                password=config[CONFIG_TYPE.PW_PASSWORD],
                email=config[CONFIG_TYPE.PW_EMAIL],
                timezone=config[CONFIG_TYPE.PW_TIMEZONE],
                cache_expire=config[CONFIG_TYPE.PW_CACHE_EXPIRE],
                timeout=config[CONFIG_TYPE.PW_TIMEOUT],
                pool_maxsize=config[CONFIG_TYPE.PW_POOL_MAXSIZE],
                siteid=config[CONFIG_TYPE.PW_SITEID],
                authpath=config[CONFIG_TYPE.PW_AUTH_PATH],
                authmode=config[CONFIG_TYPE.PW_AUTH_MODE],
                cachefile=config[CONFIG_TYPE.PW_CACHE_FILE],
                auto_select=True,
                retry_modes=True,
                gw_pwd=config[CONFIG_TYPE.PW_GW_PWD]
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
        handler = Handler(configuration=config, pw=pw, pw_control=pw_control)

        server = threading.Thread(
            target=run_server,
            args=(
                config[CONFIG_TYPE.PW_BIND_ADDRESS],  # Host
                config[CONFIG_TYPE.PW_PORT],          # Port
                handler,                              # Handler
                config[CONFIG_TYPE.PW_HTTPS] == "yes" # HTTPS
            )
        )
        servers.append(server)

    # Start all server threads
    for config, server in zip(configs, servers):
        log.info(
            f"pyPowerwall [{pypowerwall.version}] Proxy Server [{BUILD}] - {config[CONFIG_TYPE.PW_HTTP_TYPE]} Port {config['PW_PORT']}{' - DEBUG' if config[CONFIG_TYPE.PW_DEBUG] else ''}"
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

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
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

import pypowerwall
from pypowerwall import parse_version
from transform import get_static, inject_js

BUILD = "t52"
ALLOWLIST = [
    '/api/status', '/api/site_info/site_name', '/api/meters/site',
    '/api/meters/solar', '/api/sitemaster', '/api/powerwalls',
    '/api/customer/registration', '/api/system_status', '/api/system_status/grid_status',
    '/api/system/update/status', '/api/site_info', '/api/system_status/grid_faults',
    '/api/operation', '/api/site_info/grid_codes', '/api/solars', '/api/solars/brands',
    '/api/customer', '/api/meters', '/api/installer', '/api/networks',
    '/api/system/networks', '/api/meters/readings', '/api/synchrometer/ct_voltage_references',
    '/api/troubleshooting/problems', '/api/auth/toggle/supported', '/api/solar_powerwall',
]
web_root = os.path.join(os.path.dirname(__file__), "web")

# Configuration for Proxy - Check for environmental variables 
#    and always use those if available (required for Docker)
bind_address = os.getenv("PW_BIND_ADDRESS", "")
password = os.getenv("PW_PASSWORD", "password")
email = os.getenv("PW_EMAIL", "email@example.com")
host = os.getenv("PW_HOST", "")
timezone = os.getenv("PW_TIMEZONE", "America/Los_Angeles")
debugmode = os.getenv("PW_DEBUG", "no")
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

# Global Stats
proxystats = {
    'pypowerwall': "%s Proxy %s" % (pypowerwall.version, BUILD),
    'gets': 0,
    'errors': 0,
    'timeout': 0,
    'uri': {},
    'ts': int(time.time()),
    'start': int(time.time()),
    'clear': int(time.time()),
    'uptime': "",
    'mem': 0,
    'site_name': "",
    'cloudmode': False,
    'siteid': None,
    'counter': 0
}

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
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
log.setLevel(logging.INFO)

if debugmode == "yes":
    log.info("pyPowerwall [%s] Proxy Server [%s] - %s Port %d - DEBUG" %
             (pypowerwall.version, BUILD, httptype, port))
    pypowerwall.set_debug(True)
    log.setLevel(logging.DEBUG)
else:
    log.info("pyPowerwall [%s] Proxy Server [%s] - %s Port %d" %
             (pypowerwall.version, BUILD, httptype, port))
log.info("pyPowerwall Proxy Started")


# Signal handler - Exit on SIGTERM
# noinspection PyUnusedLocal
def sig_term_handle(signum, frame):
    raise SystemExit


signal.signal(signal.SIGTERM, sig_term_handle)


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
    pw = pypowerwall.Powerwall(host, password, email, timezone, cache_expire,
                               timeout, pool_maxsize, siteid=siteid,
                               authpath=authpath, authmode=authmode,
                               cachefile=cachefile)
except Exception as e:
    log.error(e)
    log.error("Fatal Error: Unable to connect. Please fix config and restart.")
    while True:
        try:
            time.sleep(5)  # Infinite loop to keep container running
        except (KeyboardInterrupt, SystemExit):
            sys.exit(0)
if pw.cloudmode:
    log.info("pyPowerwall Proxy Server - Cloud Mode")
    log.info("Connected to Site ID %s (%s)" % (pw.client.siteid, pw.site_name().strip()))
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
    log.info("Connected to Energy Gateway %s (%s)" % (host, pw.site_name().strip()))


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    pass


# noinspection PyPep8Naming
class Handler(BaseHTTPRequestHandler):
    def log_message(self, log_format, *args):
        if debugmode == "yes":
            log.debug("%s %s" % (self.address_string(), log_format % args))
        else:
            pass

    def address_string(self):
        # replace function to avoid lookup delays
        hostaddr, hostport = self.client_address[:2]
        return hostaddr

    def do_GET(self):
        global proxystats
        self.send_response(200)
        contenttype = 'application/json'

        if self.path == '/aggregates' or self.path == '/api/meters/aggregates':
            # Meters - JSON
            message: str = pw.poll('/api/meters/aggregates', jsonformat=True)
        elif self.path == '/soe':
            # Battery Level - JSON
            message: str = pw.poll('/api/system_status/soe', jsonformat=True)
        elif self.path == '/api/system_status/soe':
            # Force 95% Scale
            level = pw.level(scale=True)
            message: str = json.dumps({"percentage": level})
        elif self.path == '/api/system_status/grid_status':
            # Grid Status - JSON
            message: str = pw.poll('/api/system_status/grid_status', jsonformat=True)
        elif self.path == '/csv':
            # Grid,Home,Solar,Battery,Level - CSV
            contenttype = 'text/plain; charset=utf-8'
            batterylevel = pw.level()
            grid = pw.grid() or 0
            solar = pw.solar() or 0
            battery = pw.battery() or 0
            home = pw.home() or 0
            message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" \
                      % (grid, home, solar, battery, batterylevel)
        elif self.path == '/vitals':
            # Vitals Data - JSON
            message: str = pw.vitals(jsonformat=True) or json.dumps({})
        elif self.path == '/strings':
            # Strings Data - JSON
            message: str = pw.strings(jsonformat=True) or json.dumps({})
        elif self.path == '/stats':
            # Give Internal Stats
            proxystats['ts'] = int(time.time())
            delta = proxystats['ts'] - proxystats['start']
            proxystats['uptime'] = str(datetime.timedelta(seconds=delta))
            proxystats['mem'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            proxystats['site_name'] = pw.site_name()
            proxystats['cloudmode'] = pw.cloudmode
            if pw.cloudmode and pw.client is not None:
                proxystats['siteid'] = pw.client.siteid
                proxystats['counter'] = pw.client.counter
            proxystats['authmode'] = pw.authmode
            message: str = json.dumps(proxystats)
        elif self.path == '/stats/clear':
            # Clear Internal Stats
            log.debug("Clear internal stats")
            proxystats['gets'] = 0
            proxystats['errors'] = 0
            proxystats['uri'] = {}
            proxystats['clear'] = int(time.time())
            message: str = json.dumps(proxystats)
        elif self.path == '/temps':
            # Temps of Powerwalls 
            message: str = pw.temps(jsonformat=True) or json.dumps({})
        elif self.path == '/temps/pw':
            # Temps of Powerwalls with Simple Keys
            pwtemp = {}
            idx = 1
            temps = pw.temps()
            for i in temps:
                key = "PW%d_temp" % idx
                pwtemp[key] = temps[i]
                idx = idx + 1
            message: str = json.dumps(pwtemp)
        elif self.path == '/alerts':
            # Alerts
            message: str = pw.alerts(jsonformat=True) or json.dumps([])
        elif self.path == '/alerts/pw':
            # Alerts in dictionary/object format
            pwalerts = {}
            alerts = pw.alerts()
            if alerts is None:
                message: Optional[str] = None
            else:
                for alert in alerts:
                    pwalerts[alert] = 1
                message: str = json.dumps(pwalerts) or json.dumps({})
        elif self.path == '/freq':
            # Frequency, Current, Voltage and Grid Status
            fcv = {}
            idx = 1
            # Pull freq, current, voltage of each Powerwall via system_status
            d = pw.system_status() or {}
            if "battery_blocks" in d:
                for block in d["battery_blocks"]:
                    fcv["PW%d_name" % idx] = None  # Placeholder for vitals
                    fcv["PW%d_PINV_Fout" % idx] = get_value(block, "f_out")
                    fcv["PW%d_PINV_VSplit1" % idx] = None  # Placeholder for vitals
                    fcv["PW%d_PINV_VSplit2" % idx] = None  # Placeholder for vitals
                    fcv["PW%d_PackagePartNumber" % idx] = get_value(block, "PackagePartNumber")
                    fcv["PW%d_PackageSerialNumber" % idx] = get_value(block, "PackageSerialNumber")
                    fcv["PW%d_p_out" % idx] = get_value(block, "p_out")
                    fcv["PW%d_q_out" % idx] = get_value(block, "q_out")
                    fcv["PW%d_v_out" % idx] = get_value(block, "v_out")
                    fcv["PW%d_f_out" % idx] = get_value(block, "f_out")
                    fcv["PW%d_i_out" % idx] = get_value(block, "i_out")
                    idx = idx + 1
            # Pull freq, current, voltage of each Powerwall via vitals if available
            vitals = pw.vitals() or {}
            idx = 1
            for device in vitals:
                d = vitals[device]
                if device.startswith('TEPINV'):
                    # PW freq
                    fcv["PW%d_name" % idx] = device
                    fcv["PW%d_PINV_Fout" % idx] = get_value(d, 'PINV_Fout')
                    fcv["PW%d_PINV_VSplit1" % idx] = get_value(d, 'PINV_VSplit1')
                    fcv["PW%d_PINV_VSplit2" % idx] = get_value(d, 'PINV_VSplit2')
                    idx = idx + 1
                if device.startswith('TESYNC') or device.startswith('TEMSA'):
                    # Island and Meter Metrics from Backup Gateway or Backup Switch
                    for i in d:
                        if i.startswith('ISLAND') or i.startswith('METER'):
                            fcv[i] = d[i]
            fcv["grid_status"] = pw.grid_status(type="numeric")
            message: str = json.dumps(fcv)
        elif self.path == '/pod':
            # Powerwall Battery Data
            pod = {}
            # Get Individual Powerwall Battery Data
            d = pw.system_status() or {}
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
                    pod["PW%d_POD_nom_energy_remaining" % idx] = get_value(block, "nominal_energy_remaining")  # map
                    pod["PW%d_POD_nom_full_pack_energy" % idx] = get_value(block, "nominal_full_pack_energy")  # map
                    pod["PW%d_PackagePartNumber" % idx] = get_value(block, "PackagePartNumber")
                    pod["PW%d_PackageSerialNumber" % idx] = get_value(block, "PackageSerialNumber")
                    pod["PW%d_pinv_state" % idx] = get_value(block, "pinv_state")
                    pod["PW%d_pinv_grid_state" % idx] = get_value(block, "pinv_grid_state")
                    pod["PW%d_p_out" % idx] = get_value(block, "p_out")
                    pod["PW%d_q_out" % idx] = get_value(block, "q_out")
                    pod["PW%d_v_out" % idx] = get_value(block, "v_out")
                    pod["PW%d_f_out" % idx] = get_value(block, "f_out")
                    pod["PW%d_i_out" % idx] = get_value(block, "i_out")
                    pod["PW%d_energy_charged" % idx] = get_value(block, "energy_charged")
                    pod["PW%d_energy_discharged" % idx] = get_value(block, "energy_discharged")
                    pod["PW%d_off_grid" % idx] = int(get_value(block, "off_grid"))
                    pod["PW%d_vf_mode" % idx] = int(get_value(block, "vf_mode"))
                    pod["PW%d_wobble_detected" % idx] = int(get_value(block, "wobble_detected"))
                    pod["PW%d_charge_power_clamped" % idx] = int(get_value(block, "charge_power_clamped"))
                    pod["PW%d_backup_ready" % idx] = int(get_value(block, "backup_ready"))
                    pod["PW%d_OpSeqState" % idx] = get_value(block, "OpSeqState")
                    pod["PW%d_version" % idx] = get_value(block, "version")
                    idx = idx + 1
            # Augment with Vitals Data if available
            vitals = pw.vitals() or {}
            idx = 1
            for device in vitals:
                v = vitals[device]
                if device.startswith('TEPOD'):
                    pod["PW%d_name" % idx] = device
                    pod["PW%d_POD_ActiveHeating" % idx] = int(get_value(v, 'POD_ActiveHeating'))
                    pod["PW%d_POD_ChargeComplete" % idx] = int(get_value(v, 'POD_ChargeComplete'))
                    pod["PW%d_POD_ChargeRequest" % idx] = int(get_value(v, 'POD_ChargeRequest'))
                    pod["PW%d_POD_DischargeComplete" % idx] = int(get_value(v, 'POD_DischargeComplete'))
                    pod["PW%d_POD_PermanentlyFaulted" % idx] = int(get_value(v, 'POD_PermanentlyFaulted'))
                    pod["PW%d_POD_PersistentlyFaulted" % idx] = int(get_value(v, 'POD_PersistentlyFaulted'))
                    pod["PW%d_POD_enable_line" % idx] = int(get_value(v, 'POD_enable_line'))
                    pod["PW%d_POD_available_charge_power" % idx] = get_value(v, 'POD_available_charge_power')
                    pod["PW%d_POD_available_dischg_power" % idx] = get_value(v, 'POD_available_dischg_power')
                    pod["PW%d_POD_nom_energy_remaining" % idx] = get_value(v, 'POD_nom_energy_remaining')
                    pod["PW%d_POD_nom_energy_to_be_charged" % idx] = get_value(v, 'POD_nom_energy_to_be_charged')
                    pod["PW%d_POD_nom_full_pack_energy" % idx] = get_value(v, 'POD_nom_full_pack_energy')
                    idx = idx + 1
            # Aggregate data
            if pod:
                # Only poll if we have battery data
                pod["time_remaining_hours"] = pw.get_time_remaining()
                pod["backup_reserve_percent"] = pw.get_reserve()
                pod["nominal_full_pack_energy"] = get_value(d, 'nominal_full_pack_energy')
                pod["nominal_energy_remaining"] = get_value(d, 'nominal_energy_remaining')
            message: str = json.dumps(pod)
        elif self.path == '/version':
            # Firmware Version
            version = pw.version()
            v = {}
            if version is None:
                v["version"] = "SolarOnly"
                v["vint"] = 0
                message: str = json.dumps(v)
            else:
                v["version"] = version
                v["vint"] = parse_version(version)
                message: str = json.dumps(v)
        elif self.path == '/help':
            # Display friendly help screen link and stats
            proxystats['ts'] = int(time.time())
            delta = proxystats['ts'] - proxystats['start']
            proxystats['uptime'] = str(datetime.timedelta(seconds=delta))
            proxystats['mem'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            proxystats['site_name'] = pw.site_name()
            proxystats['cloudmode'] = pw.cloudmode
            if pw.cloudmode and pw.client is not None:
                proxystats['siteid'] = pw.client.siteid
                proxystats['counter'] = pw.client.counter
            proxystats['authmode'] = pw.authmode
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
                if i != 'uri':
                    message += f'<tr><td align="left">{i}</td><td align ="left">{proxystats[i]}</td></tr>\n'
            for i in proxystats['uri']:
                message += f'<tr><td align="left">URI: {i}</td><td align ="left">{proxystats["uri"][i]}</td></tr>\n'
            message += "</table>\n"
            message += f'\n<p>Page refresh: {str(datetime.datetime.fromtimestamp(time.time()))}</p>\n</body>\n</html>'
        elif self.path == '/api/troubleshooting/problems':
            # Simulate old API call and respond with empty list
            message = '{"problems": []}'
            # message = pw.poll('/api/troubleshooting/problems') or '{"problems": []}'
        elif self.path in ALLOWLIST:
            # Allowed API Calls - Proxy to Powerwall
            message: str = pw.poll(self.path, jsonformat=True)
        else:
            # Everything else - Set auth headers required for web application
            proxystats['gets'] = proxystats['gets'] + 1
            if pw.authmode == "token":
                # Create bogus cookies
                self.send_header("Set-Cookie", f"AuthCookie=1234567890;{cookiesuffix}")
                self.send_header("Set-Cookie", f"UserRecord=1234567890;{cookiesuffix}")
            else:
                self.send_header("Set-Cookie", f"AuthCookie={pw.client.auth['AuthCookie']};{cookiesuffix}")
                self.send_header("Set-Cookie", f"UserRecord={pw.client.auth['UserRecord']};{cookiesuffix}")

            # Serve static assets from web root first, if found.
            if self.path == "/" or self.path == "":
                self.path = "/index.html"
                fcontent, ftype = get_static(web_root, self.path)
                # Replace {VARS} with current data
                status = pw.status()
                # convert fcontent to string
                fcontent = fcontent.decode("utf-8")
                # fix the following variables that if they are None, return ""
                fcontent = fcontent.replace("{VERSION}", status["version"] or "")
                fcontent = fcontent.replace("{HASH}", status["git_hash"] or "")
                fcontent = fcontent.replace("{EMAIL}", email)
                fcontent = fcontent.replace("{STYLE}", style)
                # convert fcontent back to bytes
                fcontent = bytes(fcontent, 'utf-8')
            else:
                fcontent, ftype = get_static(web_root, self.path)
            if fcontent:
                log.debug("Served from local web root: {} type {}".format(self.path, ftype))
            # If not found, serve from Powerwall web server
            elif pw.cloudmode:
                log.debug("Cloud Mode - File not found: {}".format(self.path))
                fcontent = bytes("Not Found", 'utf-8')
                ftype = "text/plain"
            else:
                # Proxy request to Powerwall web server.
                proxy_path = self.path
                if proxy_path.startswith("/"):
                    proxy_path = proxy_path[1:]
                pw_url = "https://{}/{}".format(pw.host, proxy_path)
                log.debug("Proxy request to: {}".format(pw_url))
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

            # Allow browser caching, if user permits, only for CSS, JavaScript and PNG images...
            if browser_cache > 0 and (ftype == 'text/css' or ftype == 'application/javascript' or ftype == 'image/png'):
                self.send_header("Cache-Control", "max-age={}".format(browser_cache))
            else:
                self.send_header("Cache-Control", "no-cache, no-store")

                # Inject transformations
            if self.path.split('?')[0] == "/":
                if os.path.exists(os.path.join(web_root, style)):
                    fcontent = bytes(inject_js(fcontent, style), 'utf-8')

            self.send_header('Content-type', '{}'.format(ftype))
            self.end_headers()
            try:
                self.wfile.write(fcontent)
            except Exception as exc:
                log.debug(f"Socket broken sending PROXY response to client [doGET]: {exc}")
            return

        # Count
        if message is None:
            proxystats['timeout'] = proxystats['timeout'] + 1
            message = "TIMEOUT!"
        elif message == "ERROR!":
            proxystats['errors'] = proxystats['errors'] + 1
            message = "ERROR!"
        else:
            proxystats['gets'] = proxystats['gets'] + 1
            if self.path in proxystats['uri']:
                proxystats['uri'][self.path] = proxystats['uri'][self.path] + 1
            else:
                proxystats['uri'][self.path] = 1

        # Send headers and payload
        try:
            self.send_header('Content-type', contenttype)
            self.send_header('Content-Length', str(len(message)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(message.encode("utf8"))
        except Exception as exc:
            log.error(f"Socket broken sending API response to client [doGET]: {exc}")


# noinspection PyTypeChecker
with ThreadingHTTPServer((bind_address, port), Handler) as server:
    if https_mode == "yes":
        # Activate HTTPS
        log.debug("Activating HTTPS")
        server.socket = ssl.wrap_socket(server.socket,
                                        certfile=os.path.join(os.path.dirname(__file__), 'localhost.pem'),
                                        server_side=True, ssl_version=ssl.PROTOCOL_TLSv1_2, ca_certs=None,
                                        do_handshake_on_connect=True)

    # noinspection PyBroadException
    try:
        server.serve_forever()        
    except (Exception, KeyboardInterrupt, SystemExit):
        print(' CANCEL \n')

    log.info("pyPowerwall Proxy Stopped")
    sys.exit(0)

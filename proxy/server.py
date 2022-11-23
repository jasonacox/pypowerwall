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

    This proxy also supports pyPowerwall data for /vitals and /strings 

"""
import pypowerwall
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from socketserver import ThreadingMixIn 
import os
import json
import time
import logging
import resource
import datetime
import ssl
from transform import get_static, inject_js

BUILD = "t21"
ALLOWLIST = [
    '/api/status', '/api/site_info/site_name', '/api/meters/site',
    '/api/meters/solar', '/api/sitemaster', '/api/powerwalls', 
    '/api/customer/registration', '/api/system_status', '/api/system_status/grid_status',
    '/api/system/update/status', '/api/site_info', '/api/system_status/grid_faults',
    '/api/operation', '/api/site_info/grid_codes', '/api/solars', '/api/solars/brands',
    '/api/customer', '/api/meters', '/api/installer', '/api/networks', 
    '/api/system/networks', '/api/meters/readings', '/api/synchrometer/ct_voltage_references',
    '/api/troubleshooting/problems', '/api/auth/toggle/supported'
    ]
web_root = os.path.join(os.path.dirname(__file__), "web")

# Configuration for Proxy - Check for environmental variables 
#    and always use those if available (required for Docker)
bind_address = os.getenv("PW_BIND_ADDRESS", "")
password = os.getenv("PW_PASSWORD", "password")
email = os.getenv("PW_EMAIL", "email@example.com")
host = os.getenv("PW_HOST", "hostname")
timezone = os.getenv("PW_TIMEZONE", "America/Los_Angeles")
debugmode = os.getenv("PW_DEBUG", "no")
cache_expire = int(os.getenv("PW_CACHE_EXPIRE", "5"))
timeout = int(os.getenv("PW_TIMEOUT", "10"))
pool_maxsize = int(os.getenv("PW_POOL_MAXSIZE", "10"))
https_mode = os.getenv("PW_HTTPS", "no")
port = int(os.getenv("PW_PORT", "8675"))
style = os.getenv("PW_STYLE", "clear") + ".js"

# Global Stats
proxystats = {}
proxystats['pypowerwall'] = "%s Proxy %s" % (pypowerwall.version, BUILD)
proxystats['gets'] = 0
proxystats['errors'] = 0
proxystats['timeout'] = 0
proxystats['uri'] = {}
proxystats['ts'] = int(time.time())         # Timestamp for Now
proxystats['start'] = int(time.time())      # Timestamp for Start 
proxystats['clear'] = int(time.time())      # Timestamp of lLast Stats Clear
proxystats['uptime'] = ""

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
logging.basicConfig(format='%(levelname)s:%(message)s',level=logging.INFO)
log.setLevel(logging.INFO)

if(debugmode == "yes"):
    log.info("pyPowerwall [%s] Proxy Server [%s] - %s Port %d - DEBUG" % 
        (pypowerwall.version, BUILD, httptype, port))
    pypowerwall.set_debug(True)
    log.setLevel(logging.DEBUG)
else:
    log.info("pyPowerwall [%s] Proxy Server [%s] - %s Port %d" % 
        (pypowerwall.version, BUILD, httptype, port))
log.info("pyPowerwall Proxy Started")

# Get Value Function - Key to Value or Return Null
def get_value(a, key):
    if key in a:
        return a[key]
    else:
        log.error("Missing key in payload [%s]" % key)
        return None

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone,cache_expire,timeout,pool_maxsize)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    pass

class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if debugmode == "yes":
            log.debug("%s %s" %
                         (self.address_string(),
                          format%args))
        else:
            pass
    def address_string(self):
        # replace function to avoid lookup delays
        host, hostport = self.client_address[:2]
        return host
    def do_GET(self):
        global proxystats
        self.send_response(200)
        message = "ERROR!"
        contenttype = 'application/json'

        if self.path == '/aggregates' or self.path == '/api/meters/aggregates':
            # Meters - JSON
            message = pw.poll('/api/meters/aggregates')
        elif self.path == '/soe':
            # Battery Level - JSON
            message = pw.poll('/api/system_status/soe')
        elif self.path == '/api/system_status/soe':
            # Force 95% Scale
            level = pw.level(scale=True)
            message = json.dumps({"percentage":level})
        elif self.path == '/csv':
            # Grid,Home,Solar,Battery,Level - CSV
            contenttype = 'text/plain; charset=utf-8'
            batterylevel = pw.level()
            grid = pw.grid()
            solar = pw.solar()
            battery = pw.battery()
            home = pw.home()
            message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" \
                % (grid, home, solar, battery, batterylevel)
        elif self.path == '/vitals':
            # Vitals Data - JSON
            message = pw.vitals(jsonformat=True)
        elif self.path == '/strings':
            # Strings Data - JSON
            message = pw.strings(jsonformat=True)  
        elif self.path == '/stats':
            # Give Internal Stats
            proxystats['ts'] = int(time.time())
            delta = proxystats['ts'] - proxystats['start']
            proxystats['uptime'] = str(datetime.timedelta(seconds=delta))
            proxystats['mem'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            message = json.dumps(proxystats)
        elif self.path == '/stats/clear':
            # Clear Internal Stats
            log.debug("Clear internal stats")
            proxystats['gets'] = 0
            proxystats['errors'] = 0
            proxystats['uri'] = {}
            proxystats['clear'] = int(time.time())
            message = json.dumps(proxystats)
        elif self.path == '/temps':
            # Temps of Powerwalls 
            message = pw.temps(jsonformat=True)
        elif self.path == '/temps/pw':
            # Temps of Powerwalls with Simple Keys
            pwtemp = {}
            idx = 1
            temps = pw.temps()
            for i in temps:
                key = "PW%d_temp" % idx
                pwtemp[key] = temps[i]
                idx = idx + 1
            message = json.dumps(pwtemp)
        elif self.path == '/alerts':
            # Alerts
            message = pw.alerts(jsonformat=True)
        elif self.path == '/freq':
            # Frequency, Current, Voltage and Grid Status
            fcv = {}
            idx = 1
            vitals = pw.vitals()
            for device in vitals:
                d = vitals[device]
                if  device.startswith('TEPINV'):
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
            message = json.dumps(fcv)
        elif self.path == '/pod':
            # Battery Data
            pod = {}
            idx = 1
            vitals = pw.vitals()
            for device in vitals:
                d = vitals[device]
                if  device.startswith('TEPOD'):
                    pod["PW%d_name" % idx] = device
                    pod["PW%d_POD_ActiveHeating" % idx] = int(get_value(d, 'POD_ActiveHeating'))
                    pod["PW%d_POD_ChargeComplete" % idx] = int(get_value(d, 'POD_ChargeComplete'))
                    pod["PW%d_POD_ChargeRequest" % idx] = int(get_value(d, 'POD_ChargeRequest'))
                    pod["PW%d_POD_DischargeComplete" % idx] = int(get_value(d, 'POD_DischargeComplete'))
                    pod["PW%d_POD_PermanentlyFaulted" % idx] = int(get_value(d, 'POD_PermanentlyFaulted'))
                    pod["PW%d_POD_PersistentlyFaulted" % idx] = int(get_value(d, 'POD_PersistentlyFaulted'))
                    pod["PW%d_POD_enable_line" % idx] = int(get_value(d,'POD_enable_line'))
                    pod["PW%d_POD_available_charge_power" % idx] = get_value(d,'POD_available_charge_power')
                    pod["PW%d_POD_available_dischg_power" % idx] = get_value(d, 'POD_available_dischg_power')
                    pod["PW%d_POD_nom_energy_remaining" % idx] = get_value(d, 'POD_nom_energy_remaining')
                    pod["PW%d_POD_nom_energy_to_be_charged" % idx] = get_value(d, 'POD_nom_energy_to_be_charged')
                    pod["PW%d_POD_nom_full_pack_energy" % idx] = get_value(d, 'POD_nom_full_pack_energy')
                    idx = idx + 1
            pod["backup_reserve_percent"] = pw.get_reserve()
            message = json.dumps(pod) 
        elif self.path == '/version':
            # Firmware Version
            v = {}
            v["version"] = pw.version()
            val = pw.version().split(" ")[0]
            val = ''.join(i for i in val if i.isdigit() or i in './\\')
            while len(val.split('.')) < 3:
                val = val + ".0"
            l = [int(x, 10) for x in val.split('.')]
            l.reverse()
            v["vint"] = sum(x * (100 ** i) for i, x in enumerate(l))
            message = json.dumps(v)
        elif self.path == '/help':
            # Display friendly help screen link and stats
            proxystats['ts'] = int(time.time())
            delta = proxystats['ts'] - proxystats['start']
            proxystats['uptime'] = str(datetime.timedelta(seconds=delta))
            contenttype = 'text/html'
            message = '<html>\n<head><meta http-equiv="refresh" content="5" />\n'
            message += '<style>p, td, th { font-family: Helvetica, Arial, sans-serif; font-size: 10px;}</style>\n' 
            message += '<style>h1 { font-family: Helvetica, Arial, sans-serif; font-size: 20px;}</style>\n' 
            message += '</head>\n<body>\n<h1>pyPowerwall [%s] Proxy [%s] </h1>\n\n' % (pypowerwall.version, BUILD)
            message += '<p><a href="https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md">Click here for API help.</a></p>\n\n'
            message = message + '<table>\n<tr><th align ="left">Stat</th><th align ="left">Value</th></tr>'
            for i in proxystats:
                if i != 'uri':
                    message = message + '<tr><td align ="left">%s</td><td align ="left">%s</td></tr>\n' % (i,proxystats[i])
            for i in proxystats['uri']:
                    message = message + '<tr><td align ="left">URI: %s</td><td align ="left">%s</td></tr>\n' % (i,proxystats['uri'][i])
            message = message + "</table>\n"
            message = message + '\n<p>Page refresh: %s</p>\n</body>\n</html>' % (
                str(datetime.datetime.fromtimestamp(time.time())))
        elif self.path in ALLOWLIST:
            # Allowed API Call
            message = pw.poll(self.path)
        else:
            # Everything else - Set auth headers required for web application
            proxystats['gets'] = proxystats['gets'] + 1
            self.send_header("Set-Cookie", "AuthCookie={};{}".format(pw.auth['AuthCookie'], cookiesuffix))
            self.send_header("Set-Cookie", "UserRecord={};{}".format(pw.auth['UserRecord'], cookiesuffix))

            # Serve static assets from web root first, if found.
            fcontent, ftype = get_static(web_root, self.path)
            if fcontent:
                log.debug("Served from local web root: {}".format(self.path))
                self.send_header('Content-type','{}'.format(ftype))
                self.end_headers()
                self.wfile.write(fcontent)
                return

            # Proxy request to Powerwall web server.
            self.send_header("Set-Cookie", "Cache-Control: no-cache")
            proxy_path = self.path
            if proxy_path.startswith("/"):
                proxy_path = proxy_path[1:]
            pw_url = "https://{}/{}".format(pw.host, proxy_path)
            log.debug("Proxy request to: {}".format(pw_url))
            r = pw.session.get(
                url=pw_url,
                cookies=pw.auth,
                verify=False,
                stream=True,
                timeout=pw.timeout
            )
            fcontent = r.content
            ftype = r.headers['content-type']

            # Inject transformations
            if self.path.split('?')[0] == "/":
                if os.path.exists(os.path.join(web_root, style)):
                    fcontent = bytes(inject_js(fcontent, style), 'utf-8')

            self.send_header('Content-type','{}'.format(ftype))
            self.end_headers()
            self.wfile.write(fcontent)
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
            self.send_header('Content-type',contenttype)
            self.send_header('Content-Length', str(len(message)))
            self.end_headers()
            self.wfile.write(bytes(message, "utf8"))
        except:
            log.error("Socket broken sending response [doGET]")

with ThreadingHTTPServer((bind_address, port), handler) as server:
    if(https_mode == "yes"):
        # Activate HTTPS
        log.debug("Activating HTTPS")
        server.socket = ssl.wrap_socket (server.socket, 
            certfile=os.path.join(os.path.dirname(__file__), 'localhost.pem'), 
            server_side=True, ssl_version=ssl.PROTOCOL_TLSv1_2, ca_certs=None, 
            do_handshake_on_connect=True)

    try:
        server.serve_forever()
    except:
        print(' CANCEL \n')
        
    log.info("pyPowerwall Proxy Stopped")
    os._exit(0)

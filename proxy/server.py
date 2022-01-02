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
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import json

PORT = 8675

# Credentials for your Powerwall - Check for environmental variables 
#    and always use those if available (required for Docker)
password = os.getenv("PW_PASSWORD", "password")
email = os.getenv("PW_EMAIL", "email@example.com")
host = os.getenv("PW_HOST", "hostname")
timezone = os.getenv("PW_TIMEZONE", "America/Los_Angeles")
debugmode = os.getenv("PW_DEBUG", "no")
cache_expire = os.getenv("PW_CACHE_EXPIRE", "5")

# Global Stats
proxystats = {}
proxystats['gets'] = 0
proxystats['errors'] = 0
proxystats['uri'] = {}

if(debugmode == "yes"):
    pypowerwall.set_debug(True)

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Set Timeout in Seconds
pw.pwcacheexpire = int(cache_expire)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global proxy
        self.send_response(200)
        message = "ERROR!"
        if self.path == '/aggregates' or self.path == '/api/meters/aggregates':
            # Meters - JSON
            message = pw.poll('/api/meters/aggregates')
        if self.path == '/soe' or self.path == '/api/system_status/soe':
            # Battery Level - JSON
            message = pw.poll('/api/system_status/soe')
        if self.path == '/csv':
            # Grid,Home,Solar,Battery,Level - CSV
            batterylevel = pw.level()
            grid = pw.grid()
            solar = pw.solar()
            battery = pw.battery()
            home = pw.home()
            message = "%0.2f,%0.2f,%0.2f,%0.2f,%0.2f\n" \
                % (grid, home, solar, battery, batterylevel)
        if self.path == '/vitals':
            # Vitals Data - JSON
            message = pw.vitals(jsonformat=True)
        if self.path == '/strings':
            # Strings Data - JSON
            message = pw.strings(jsonformat=True)  
        if self.path == '/stats':
            # Give Internal Stats
            message = json.dumps(proxystats)
        if self.path == '/stats/clear':
            # Clear Internal Stats
            proxystats['gets'] = 0
            proxystats['errors'] = 0
            proxystats['uri'] = {}
            message = json.dumps(proxystats)
        # Count
        if message == "ERROR!" or message is None:
            proxystats['errors'] = proxystats['errors'] + 1
        else:
            proxystats['gets'] = proxystats['gets'] + 1
            if self.path in proxystats['uri']:
                proxystats['uri'][self.path] = proxystats['uri'][self.path] + 1
            else:
                proxystats['uri'][self.path] = 1
        # Send headers
        self.send_header('Content-type','text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(message)))
        self.end_headers()
        self.wfile.write(bytes(message, "utf8"))

try:
    with HTTPServer(('', PORT), handler) as server:
        server.serve_forever()
except:
    print(' CANCEL \n')

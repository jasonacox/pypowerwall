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

"""
import pypowerwall
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

PORT = 8675

# Credentials for your Powerwall - Check for environmental variables 
#    and always use those if available (required for Docker)
password = os.getenv("PW_PASSWORD", "password")
email = os.getenv("PW_EMAIL", "email@example.com")
host = os.getenv("PW_HOST", "hostname")
timezone = os.getenv("PW_TIMEZONE", "America/Los_Angeles")
debugmode = os.getenv("PW_DEBUG", "no")
cache_expire = os.getenv("PW_CACHE_EXPIRE", "5")

if(debugmode == "yes"):
    pypowerwall.set_debug(True)

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Set Timeout in Seconds
pw.pwcacheexpire = int(cache_expire)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
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

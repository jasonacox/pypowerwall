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

PORT = 8675

pypowerwall.set_debug(True)

# Credentials for your Powerwall - Customer Login Data
password='password'
email='email@example.com'
host = "hostname"
timezone = "America/Los_Angeles"

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/plain')
        self.end_headers()
        message = "ERROR!"
        if self.path == '/aggregates':
            message = pw.poll('/api/meters/aggregates')
        if self.path == '/soe':
            message = pw.poll('/api/system_status/soe')
        self.wfile.write(bytes(message, "utf8"))

try:
    with HTTPServer(('', PORT), handler) as server:
        server.serve_forever()
except:
    print(' CANCEL \n')

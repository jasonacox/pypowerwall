# pyPowerWall - Test Web API Server for TEDAPI
# -*- coding: utf-8 -*-
"""
 Test Web API Server for TEDAPI
 
 This module allows you to access the Tesla Powerwall Gateway 
 TEDAPI on 192.168.91.1 via a web API.

 Usage: python web.py <gateway_password>

 Web API http://localhost:4444
    GET /din - Returns the Powerwall Gateway DIN number
    GET /config - Returns the Powerwall Gateway configuration
    GET /status - Returns the Powerwall Gateway status

 Note:
    This module requires access to the Powerwall Gateway. You can add a route to
    using the command: sudo route add -host 192.168.91.1 <Powerwall_IP>
    The Powerwall Gateway password is required to access the TEDAPI.

 Author: Jason A. Cox
 Date: 1 Jun 2024
 For more information see https://github.com/jasonacox/pypowerwall
"""

from flask import Flask, request, jsonify
from tedapi import TEDAPI

app = Flask(__name__)

# Get gateway password from command line 
import sys
try:
    gw_pwd = sys.argv[1]
except IndexError:
    print('Usage: python web.py <gateway_password>')
    sys.exit(1)

# Connect to Powerwall
tedapi = TEDAPI(gw_pwd=gw_pwd)
if not tedapi.din:
    print('Failed to connect to Powerwall')
    sys.exit(1)
print(f"Connected to Powerwall: {tedapi.din}")

@app.route('/din', methods=['GET'])
def din():
    return jsonify({'din': tedapi.din})

@app.route('/config', methods=['GET'])
def config():
    return jsonify(tedapi.get_config())

@app.route('/status', methods=['GET'])
def status():
    return jsonify(tedapi.get_status())

# Main
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4444)
# End of file


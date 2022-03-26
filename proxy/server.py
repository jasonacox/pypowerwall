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
import sys

PORT = 8675
BUILD = "t6"

ALLOWLIST = [
    '/api/status', '/api/site_info/site_name', '/api/meters/site',
    '/api/meters/solar', '/api/sitemaster', '/api/powerwalls', 
    '/api/customer/registration', '/api/system_status', '/api/system_status/grid_status',
    '/api/system/update/status', '/api/site_info', '/api/system_status/grid_faults',
    '/api/operation', '/api/site_info/grid_codes', '/api/solars', '/api/solars/brands',
    '/api/customer', '/api/meters', '/api/installer', '/api/networks', 
    '/api/system/networks', '/api/meters/readings', '/api/synchrometer/ct_voltage_references'
    ]

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
proxystats['pypowerwall'] = "%s Proxy %s" % (pypowerwall.version, BUILD)
proxystats['gets'] = 0
proxystats['errors'] = 0
proxystats['timeout'] = 0
proxystats['uri'] = {}
proxystats['ts'] = int(time.time())         # Timestamp for Now
proxystats['start'] = int(time.time())      # Timestamp for Start 
proxystats['clear'] = int(time.time())      # Timestamp of lLast Stats Clear

if(debugmode == "yes"):
    pypowerwall.set_debug(True)
    sys.stderr.write("pyPowerwall [%s] Proxy Server [%s] Started - Port %d - DEBUG\n" % (pypowerwall.version, BUILD, PORT))

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Set Timeout in Seconds
pw.pwcacheexpire = int(cache_expire)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class handler(BaseHTTPRequestHandler):
    def address_string(self):
        # replace function to avoid lookup delays
        host, port = self.client_address[:2]
        #return socket.getfqdn(host)
        return host
    def do_GET(self):
        self.send_response(200)
        message = "ERROR!"
        if self.path == '/aggregates' or self.path == '/api/meters/aggregates':
            # Meters - JSON
            message = pw.poll('/api/meters/aggregates')
        elif self.path == '/soe' or self.path == '/api/system_status/soe':
            # Battery Level - JSON
            message = pw.poll('/api/system_status/soe')
        elif self.path == '/csv':
            # Grid,Home,Solar,Battery,Level - CSV
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
            message = json.dumps(proxystats)
        elif self.path == '/stats/clear':
            # Clear Internal Stats
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
            # Frequency, Current and Voltage
            fcv = {}
            idx = 1
            vitals = pw.vitals()
            for device in vitals:
                d = vitals[device]
                if  device.startswith('TEPINV'):
                    # PW freq
                    fcv["PW%d_name" % idx] = device
                    fcv["PW%d_PINV_Fout" % idx] = d['PINV_Fout']
                    fcv["PW%d_PINV_VSplit1" % idx] = d['PINV_VSplit1']
                    fcv["PW%d_PINV_VSplit2" % idx] = d['PINV_VSplit2']
                    idx = idx + 1
                if device.startswith('TESYNC'):
                    # Sync Freq
                    fcv["ISLAND_FreqL1_Load"] = d['ISLAND_FreqL1_Load']
                    fcv["ISLAND_FreqL2_Load"] = d['ISLAND_FreqL2_Load']
                    fcv["ISLAND_FreqL3_Load"] = d['ISLAND_FreqL3_Load']
                    fcv["ISLAND_FreqL1_Main"] = d['ISLAND_FreqL1_Main']
                    fcv["ISLAND_FreqL2_Main"] = d['ISLAND_FreqL2_Main']
                    fcv["ISLAND_FreqL3_Main"] = d['ISLAND_FreqL3_Main']
                    # Sync Voltages
                    fcv["ISLAND_VL1N_Load"] = d['ISLAND_VL1N_Load']
                    fcv["ISLAND_VL2N_Load"] = d['ISLAND_VL2N_Load']
                    fcv["ISLAND_VL3N_Load"] = d['ISLAND_VL3N_Load']
                    fcv["METER_X_VL1N"] = d['METER_X_VL1N']
                    fcv["METER_X_VL2N"] = d['METER_X_VL2N']
                    fcv["METER_X_VL3N"] = d['METER_X_VL3N']
                    fcv["METER_Y_VL1N"] = d['METER_Y_VL1N']
                    fcv["METER_Y_VL2N"] = d['METER_Y_VL2N']
                    fcv["METER_Y_VL3N"] = d['METER_Y_VL3N']
                    # Sync Current
                    fcv["METER_X_CTA_I"] = d['METER_X_CTA_I']
                    fcv["METER_X_CTB_I"] = d['METER_X_CTB_I']
                    fcv["METER_X_CTC_I"] = d['METER_X_CTC_I']
                    fcv["METER_Y_CTA_I"] = d['METER_Y_CTA_I']
                    fcv["METER_Y_CTB_I"] = d['METER_Y_CTB_I']
                    fcv["METER_Y_CTC_I"] = d['METER_Y_CTC_I']
            message = json.dumps(fcv)
        elif self.path == '/pod':
            pod = {}
            idx = 1
            vitals = pw.vitals()
            for device in vitals:
                d = vitals[device]
                if  device.startswith('TEPOD'):
                    pod["PW%d_name" % idx] = device
                    pod["PW%d_POD_ActiveHeating" % idx] = int(d['POD_ActiveHeating'])
                    pod["PW%d_POD_ChargeComplete" % idx] = int(d['POD_ChargeComplete'])
                    pod["PW%d_POD_ChargeRequest" % idx] = int(d['POD_ChargeRequest'])
                    pod["PW%d_POD_DischargeComplete" % idx] = int(d['POD_DischargeComplete'])
                    pod["PW%d_POD_PermanentlyFaulted" % idx] = int(d['POD_PermanentlyFaulted'])
                    pod["PW%d_POD_PersistentlyFaulted" % idx] = int(d['POD_PersistentlyFaulted'])
                    pod["PW%d_POD_enable_line" % idx] = int(d['POD_enable_line'])
                    pod["PW%d_POD_available_charge_power" % idx] = d['POD_available_charge_power']
                    pod["PW%d_POD_available_dischg_power" % idx] = d['POD_available_dischg_power']
                    pod["PW%d_POD_nom_energy_remaining" % idx] = d['POD_nom_energy_remaining']
                    pod["PW%d_POD_nom_energy_to_be_charged" % idx] = d['POD_nom_energy_to_be_charged']
                    pod["PW%d_POD_nom_full_pack_energy" % idx] = d['POD_nom_full_pack_energy']
                    idx = idx + 1
            message = json.dumps(pod)        
        elif self.path == '/help':
            message = 'HELP: See https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md'
        elif self.path in ALLOWLIST:
            # Allowed API Call
            message = pw.poll(self.path)
        else:
            message = "ERROR!"

        # Count
        if message is None:
            proxystats['timeout'] = proxystats['timeout'] + 1
            message == "TIMEOUT!"
        elif message == "ERROR!":
            proxystats['errors'] = proxystats['errors'] + 1
            message == "ERROR!"
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
    with ThreadingHTTPServer(('', PORT), handler) as server:
        server.serve_forever()
except:
    print(' CANCEL \n')

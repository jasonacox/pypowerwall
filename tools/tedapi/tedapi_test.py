# pyPowerWall - Tesla TEDAPI Class
# -*- coding: utf-8 -*-
"""
 TEDAPI Test Script
 
 This module allows you to access the Tesla Powerwall Gateway 
 TEDAPI on 192.168.91.1 as used by the Tesla One app.

 Note:
    This module requires access to the Powerwall Gateway. You can add a route to
    using the command: sudo route add -host 192.168.91.1 <Powerwall_IP>
    The Powerwall Gateway password is required to access the TEDAPI.

 Author: Jason A. Cox
 Date: 8 Jun 2024
 For more information see https://github.com/jasonacox/pypowerwall
"""

# Import Class
from pypowerwall.tedapi import TEDAPI

gw_pwd = "THEGWPASS"  # Change to your Powerwall Gateway Password

# Connect to Gateway
gw = TEDAPI(gw_pwd)

# Grab the Config and Live Status
config = gw.get_config() or {}
status = gw.get_status()

# Print
site_info = config.get('site_info', {})
site_name = site_info.get('site_name', 'Unknown')
print(f"My Site: {site_name}")
meterAggregates = status.get('control', {}).get('meterAggregates', [])
for meter in meterAggregates:
    location = meter.get('location', 'Unknown').title()
    realPowerW = int(meter.get('realPowerW', 0))
    print(f"   - {location}: {realPowerW}W")


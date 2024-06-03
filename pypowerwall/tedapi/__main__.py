# pyPowerWall - Tesla TEDAPI Class Main
# -*- coding: utf-8 -*-
"""
 Tesla TEADAPI Class - Command Line Test
 
 This script tests the TEDAPI class by connecting to a Tesla Powerwall Gateway
"""

# Imports
from pypowerwall.tedapi import TEDAPI, GW_IP
import json
import sys

# Print Header
print("Tesla Powerwall Gateway TEDAPI Reader")

# Command line arguments
if len(sys.argv) > 1:
    gw_pwd = sys.argv[1]
else:
    # Get GW_PWD from User
    gw_pwd = input("\nEnter Powerwall Gateway Password: ")
print()

# Create TEDAPI Object and get Configuration and Status
print(f"Connecting to Powerwall Gateway {GW_IP}")
ted = TEDAPI(gw_pwd)
config = ted.get_config()
status = ted.get_status()
print()

# Print Configuration
print(" - Configuration:")
site_info = config.get('site_info', {})
site_name = site_info.get('site_name', 'Unknown')
print(f"   - Site Name: {site_name}")
battery_commission_date = site_info.get('battery_commission_date', 'Unknown')
print(f"   - Battery Commission Date: {battery_commission_date}")
vin = config.get('vin', 'Unknown')
print(f"   - VIN: {vin}")
number_of_powerwalls = len(config.get('battery_blocks', []))
print(f"   - Number of Powerwalls: {number_of_powerwalls}")
print()

# Print power data
print(" - Power Data:")
nominalEnergyRemainingWh = status.get('control', {}).get('systemStatus', {}).get('nominalEnergyRemainingWh', 0)
nominalFullPackEnergyWh = status.get('control', {}).get('systemStatus', {}).get('nominalFullPackEnergyWh', 0)
soe = round(nominalEnergyRemainingWh / nominalFullPackEnergyWh * 100, 2)
print(f"   - Battery Charge: {soe}% ({nominalEnergyRemainingWh}Wh of {nominalFullPackEnergyWh}Wh)")
meterAggregates = status.get('control', {}).get('meterAggregates', [])
for meter in meterAggregates:
    location = meter.get('location', 'Unknown').title()
    realPowerW = int(meter.get('realPowerW', 0))
    print(f"   - {location}: {realPowerW}W")
print()

# Save Configuration and Status to JSON files
with open('status.json', 'w') as f:
    json.dump(status, f)
with open('config.json', 'w') as f:
    json.dump(config, f)
print(" - Configuration and Status saved to config.json and status.json")
print()


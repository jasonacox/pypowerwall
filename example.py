# Example: pyPowerwall Usage Demo
# --------------------------------
# This script demonstrates how to connect to a Tesla Powerwall using the pyPowerwall library.
# It supports multiple connection modes (local, fleetapi, cloud, tedapi).
#
# Usage:
#   - Set your connection mode and credentials below, or use a .env file with the following variables:
#       POWERWALL_MODE, POWERWALL_HOST, POWERWALL_PASSWORD, POWERWALL_EMAIL, POWERWALL_TIMEZONE, POWERWALL_GW_PWD
#   - Run: python example.py
#
# For more info, see: https://github.com/jasonacox/pypowerwall

import pypowerwall
import dotenv
import os

# Load environment variables from .env file if present
dotenv.load_dotenv()
host = password = email = timezone = gw_pwd = None

# Enable debug logging for more verbose output (optional for learning)
# pypowerwall.set_debug(True)

# Select the connection mode you want to use and enter
# the credentials for your Powerwall below.
mode = os.getenv('POWERWALL_MODE', 'local') 

# Option 1 - LOCAL MODE - Customer Login (Powerwall 2 and + only)
if mode == "local":
    password = "password"
    email = "email@example.com"
    host = "10.0.1.123"               # Address of your Powerwall Gateway
    timezone = "America/Los_Angeles"  # Your local timezone
    gw_pwd = None

# Option 2 - FLEETAPI MODE - Requires Setup (Powerwall & Solar-Only)
if mode == "fleetapi":
    host = password = email = ""
    timezone = "America/Los_Angeles"
    gw_pwd = None 

# Option 3 - CLOUD MODE - Requires Setup (Powerwall & Solar-Only)
if mode == "cloud":
    host = password = ""
    email = 'email@example.com'
    timezone = "America/Los_Angeles"
    gw_pwd = None

# Option 4 - TEDAPI MODE - Requires WiFI access to Gateway (Powerwall 2, + and 3)
if mode == "tedapi":
    host = "192.168.91.1"
    gw_pwd = "ABCDEFGHIJ"             # Gateway WiFi password
    password = email = ""
    timezone = "America/Los_Angeles"
    # Uncomment the following for hybrid mode (Powerwall 2 and +)
    # password = "password"
    # email = "email@example.com"

# Override with .env or environment variables if set
host = os.getenv('POWERWALL_HOST', host)
password = os.getenv('POWERWALL_PASSWORD', password)
email = os.getenv('POWERWALL_EMAIL', email)
timezone = os.getenv('POWERWALL_TIMEZONE', timezone)
gw_pwd = os.getenv('POWERWALL_GW_PWD', gw_pwd)

# Connect to Powerwall - auto_select mode (local, fleetapi, cloud, tedapi)
print(f"Connecting to Powerwall using {mode} mode...")
pw = pypowerwall.Powerwall(host, password, email, timezone, gw_pwd=gw_pwd, auto_select=True)

# --- System Info ---
print("Site Name: %s - Firmware: %s - DIN: %s" % (pw.site_name(), pw.version(), pw.din()))
print("System Uptime: %s\n" % pw.uptime())

# --- Pull Sensor Power Data ---
grid = pw.grid()
solar = pw.solar()
battery = pw.battery()
home = pw.home()

# --- Display Data ---
print("Battery power level: %0.0f%%" % pw.level())
print("Combined power metrics: %r" % pw.power())
print("")
print("Grid Power: %0.2fkW" % (float(grid)/1000.0))
print("Solar Power: %0.2fkW" % (float(solar)/1000.0))
print("Battery Power: %0.2fkW" % (float(battery)/1000.0))
print("Home Power: %0.2fkW" % (float(home)/1000.0))
print("")

# --- Raw JSON Payload Examples ---
print("Grid raw: %r\n" % pw.grid(verbose=True))
print("Solar raw: %r\n" % pw.solar(verbose=True))

# --- Device Vitals ---
print("Vitals: %r\n" % pw.vitals())

# --- String Data ---
print("String Data: %r\n" % pw.strings())

# --- System Status (e.g. Battery Capacity) ---
system_status = pw.system_status()
print("System Status: %r\n" % system_status)

# --- Key System Status Data ---
print("Battery Capacity: %0.2f kWh" % (system_status.get('nominal_full_pack_energy', 0) / 1000.0))
print("Battery Energy Remaining: %0.2f kWh" % (system_status.get('nominal_energy_remaining', 0) / 1000.0))
print("Max Charge Power: %0.2f kW" % (system_status.get('max_charge_power', 0) / 1000.0))
print("Max Discharge Power: %0.2f kW" % (system_status.get('max_discharge_power', 0) / 1000.0))
print("Grid Status: %s" % system_status.get('system_island_state', ''))
print("Available Battery Blocks: %d" % system_status.get('available_blocks', 0))

# Print per-battery block details if present
battery_blocks = system_status.get('battery_blocks', [])
if battery_blocks:
    print("\nBattery Blocks:")
    for i, block in enumerate(battery_blocks, 1):
        print(f" Block {i}:")
        print(f"   Serial: {block.get('PackageSerialNumber', '')}")
        print(f"   Nominal Full Pack Energy: {block.get('nominal_full_pack_energy', 0)/1000.0:.2f} kWh")
        print(f"   Nominal Energy Remaining: {block.get('nominal_energy_remaining', 0)/1000.0:.2f} kWh")
        print(f"   Power Output: {block.get('p_out', 0)} W")
        print(f"   Voltage Output: {block.get('v_out', 0)} V")
        print(f"   Frequency Output: {block.get('f_out', 0)} Hz")
        print(f"   Inverter State: {block.get('pinv_state', '')}")
        print(f"   Grid State: {block.get('pinv_grid_state', '')}")
        print(f"   Backup Ready: {block.get('backup_ready', False)}")
        print(f"   Version: {block.get('version', '')}")

# --- Explore Further ---
# Uncomment below to see all available methods and attributes:
# print(dir(pw))

# --- Next Steps ---
# See the API.md or project README for more advanced usage and 
# integration tips.

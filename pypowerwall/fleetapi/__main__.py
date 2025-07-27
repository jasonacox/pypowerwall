# pyPowerWall Module - FleetAPI Command Line Interface
# -*- coding: utf-8 -*-
"""
 Command Line Interface for Tesla FleetAPI to read and control Powerwall 
 status and settings.  This module is a command line interface to the
 FleetAPI class in the pypowerwall module.

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Command Line Interface for FleetAPI:
    python3 -m pypowerwall.fleetapi

"""

# Import Libraries
import sys
import json
import argparse
import os
from .fleetapi import FleetAPI, CONFIGFILE

# Display help if no arguments
if len(sys.argv) == 1:
    print("Tesla FleetAPI - Command Line Interface\n")
    print(f"Usage: {sys.argv[0]} command [arguments] [-h] [--debug] [--config CONFIG] [--site SITE] [--json]\n")
    print("Commands:")
    print("    setup               Setup FleetAPI for your site")
    print("    sites               List available sites")
    print("    status              Report current power status for your site")
    print("    info                Display information about your site")
    print("    getmode             Get current operational mode setting")
    print("    getreserve          Get current battery reserve level setting")
    print("    setmode             Set operational mode (self_consumption, backup, autonomous)")
    print("    setreserve          Set battery reserve level (percentage or 'current')\n")
    print("options:")
    print("  --debug               Enable debug mode")
    print("  --config CONFIG       Specify alternate config file (default: .fleetapi.config)")
    print("  --site SITE           Specify site_id")
    print("  --json                Output in JSON format")
    sys.exit(0)

# Parse command line arguments
parser = argparse.ArgumentParser(description='Tesla FleetAPI - Command Line Interface')
parser.add_argument("command", choices=["setup", "sites", "status", "info", "getmode", "getreserve",
                        "setmode", "setreserve"], help="Select command to execute")
parser.add_argument("argument", nargs="?", default=None, help="Argument for setmode or setreserve command")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
parser.add_argument("--config", help="Specify alternate config file")
parser.add_argument("--site", help="Specify site_id")
parser.add_argument("--json", action="store_true", help="Output in JSON format")

# Adding descriptions for each command
parser.add_help = False  # Disabling default help message
args = parser.parse_args()

settings_file = CONFIGFILE
if args.config:
    # Use alternate config file if specified
    settings_file = args.config

# Create FleetAPI object
settings_debug = False
settings_site = None
if args.debug:
    settings_debug = True
if args.site:
    settings_site = args.site

# Create FleetAPI object
fleet = FleetAPI(configfile=settings_file, debug=settings_debug, site_id=settings_site)

# Load Configuration
try:
    config_loaded = fleet.load_config()
except Exception as e:
    print(f"Error loading configuration: {e}")
    config_loaded = False
    # Prompt user to remove config file
    if os.path.exists(settings_file):
        resp = input(f"Do you want to remove the FleetAPI config file '{settings_file}' and re-run setup? [y/N]: ").strip().lower()
        if resp == 'y':
            os.remove(settings_file)
            print(f"Removed {settings_file}. Please re-run setup.")
        else:
            print("Config file not removed. Exiting...")
    sys.exit(1)

if not config_loaded:
    print(f"  Configuration file not found or invalid: {settings_file}")
    if args.command != "setup":
        print("  Run setup to access Tesla FleetAPI.")
        sys.exit(1)
    else:
        fleet.setup()
        if not fleet.load_config():
            print("  Setup failed, exiting...")
            sys.exit(1)
    sys.exit(0)

# Command: Run Setup
if args.command == "setup":
    fleet.setup()
    sys.exit(0)

# Command: List Sites
if args.command == "sites":
    sites = fleet.getsites()
    if not sites:
        print("Error: Unable to retrieve sites (API error or authentication failure).")
        sys.exit(1)
    if args.json:
        print(json.dumps(sites, indent=4))
    else:
        for site in sites:
            site_id = site.get('energy_site_id', None)
            site_name = site.get('site_name', None)
            print(f"  {site_id} - {site_name}")
    sys.exit(0)

# Command: Status
if args.command == "status":
    status = fleet.get_live_status()
    if not status:
        print("Error: Unable to retrieve live status (API error or authentication failure).")
        sys.exit(1)
    if args.json:
        print(json.dumps(status, indent=4))
    else:
        for key in status:
            print(f"  {key}: {status[key]}")
    sys.exit(0)

# Command: Site Info
if args.command == "info":
    info = fleet.get_site_info()
    if not info:
        print("Error: Unable to retrieve site info (API error or authentication failure).")
        sys.exit(1)
    if args.json:
        print(json.dumps(info, indent=4))
    else:
        for key in info:
            print(f"  {key}: {info[key]}")
    sys.exit(0)

# Command: Get Operating Mode
if args.command == "getmode":
    mode = fleet.get_operating_mode()
    if mode is None:
        print("Error: Unable to retrieve operating mode (API error or authentication failure).")
        sys.exit(1)
    if args.json:
        print(json.dumps({"mode": mode}, indent=4))
    else:
        print(f"{mode}")
    sys.exit(0)

# Command: Get Battery Reserve
if args.command == "getreserve":
    reserve = fleet.get_battery_reserve()
    if reserve is None:
        print("Error: Unable to retrieve battery reserve (API error or authentication failure).")
        sys.exit(1)
    if args.json:
        print(json.dumps({"reserve": reserve}, indent=4))
    else:
        print(f"{reserve}")
    sys.exit(0)

# Command: Set Operating Mode
if args.command == "setmode":
    if args.argument:
        # autonomous or self_consumption
        if args.argument in ["self", "self_consumption"]:
            result = fleet.set_operating_mode("self_consumption")
        elif args.argument in ["auto", "time", "autonomous"]:
            result = fleet.set_operating_mode("autonomous")
        elif args.argument in ["backup"]:
            result = fleet.set_operating_mode("backup")
        else:
            print("Invalid mode, must be 'self', 'backup' or 'auto'")
            sys.exit(1)
        if not result:
            print("Error: Unable to set operating mode (API error or authentication failure).")
            sys.exit(1)
        print(result)
    else:
        print("No mode specified, exiting...")
    sys.exit(0)

# Command: Set Battery Reserve
if args.command == "setreserve":
    if args.argument:
        if args.argument.isdigit():
            val = int(args.argument)
            if val < 0 or val > 100:
                print(f"Invalid reserve level {val}, must be 0-100")
                sys.exit(1)
        elif args.argument == "current":
            val = fleet.battery_level()
            if val is None:
                print("Error: Unable to retrieve current battery level (API error or authentication failure).")
                sys.exit(1)
        else:
            print("Invalid reserve level, must be 0-100 or 'current' to set to current level.")
            sys.exit(1)
        result = fleet.set_battery_reserve(int(val))
        if not result:
            print("Error: Unable to set battery reserve (API error or authentication failure).")
            sys.exit(1)
        print(result)
    else:
        print("No reserve level specified, exiting...")
    sys.exit(0)

print("No command specified, exiting...")
sys.exit(1)

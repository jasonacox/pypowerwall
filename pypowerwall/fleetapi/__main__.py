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
    print("    setmode             Set operatinoal mode (self_consumption or autonomous)")
    print("    setreserve          Set battery reserve level (prcentage or 'current')\n")
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
if not fleet.load_config():
    print(f"  Configuration file not found: {settings_file}")
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
    if args.json:
        print(json.dumps(sites, indent=4))
    else:
        for site in sites:
            print(f"  {site['energy_site_id']} - {site['site_name']}")
    sys.exit(0)

# Command: Status
if args.command == "status":
    status = fleet.get_live_status()
    if args.json:
        print(json.dumps(status, indent=4))
    else:
        for key in status:
            print(f"  {key}: {status[key]}")
    sys.exit(0)

# Command: Site Info
if args.command == "info":
    info = fleet.get_site_info()
    if args.json:
        print(json.dumps(info, indent=4))
    else:
        for key in info:
            print(f"  {key}: {info[key]}")
    sys.exit(0)

# Command: Get Operating Mode
if args.command == "getmode":
    mode = fleet.get_operating_mode()
    if args.json:
        print(json.dumps({"mode": mode}, indent=4))
    else:
        print(f"{mode}")
    sys.exit(0)

# Command: Get Battery Reserve
if args.command == "getreserve":
    reserve = fleet.get_battery_reserve()
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
            print(fleet.set_operating_mode("self_consumption"))
        elif args.argument in ["auto", "time", "autonomous"]:
            print(fleet.set_operating_mode("autonomous"))
        else:
            print("Invalid mode, must be 'self' or 'auto'")
            sys.exit(1)
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
        else:
            print("Invalid reserve level, must be 0-100 or 'current' to set to current level.")
            sys.exit(1)
        print(fleet.set_battery_reserve(int(val)))
    else:
        print("No reserve level specified, exiting...")
    sys.exit(0)

print("No command specified, exiting...")
sys.exit(1)

# pyPowerWall Module - Scan Function
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Scan Function:
    python -m pypowerwall <scan>

"""

import argparse
import os
import sys
import json

# Modules
from pypowerwall import version, set_debug

# Global Variables
authpath = os.getenv("PW_AUTH_PATH", "")

timeout = 1.0
hosts = 30
state = 0
color = True
ip = None
email = None

# Setup parser and groups
p = argparse.ArgumentParser(prog="PyPowerwall", description=f"PyPowerwall Module v{version}")
subparsers = p.add_subparsers(dest="command", title='commands (run <command> -h to see usage information)',
                              required=True)

setup_args = subparsers.add_parser("setup", help='Setup Tesla Login for Cloud Mode access')
setup_args.add_argument("-email", type=str, default=email, help="Email address for Tesla Login.")

setup_args = subparsers.add_parser("fleetapi", help='Setup Tesla FleetAPI for Cloud Mode access')

setup_args = subparsers.add_parser("tedapi", help='Test TEDAPI connection to Powerwall Gateway')

scan_args = subparsers.add_parser("scan", help='Scan local network for Powerwall gateway')
scan_args.add_argument("-timeout", type=float, default=timeout,
                       help=f"Seconds to wait per host [Default={timeout:.1f}]")
scan_args.add_argument("-nocolor", action="store_true", default=not color,
                       help="Disable color text output.")
scan_args.add_argument("-ip", type=str, default=ip, help="IP address within network to scan.")
scan_args.add_argument("-hosts", type=int, default=hosts,
                       help=f"Number of hosts to scan simultaneously [Default={hosts}]")

set_mode_args = subparsers.add_parser("set", help='Set Powerwall Mode and Reserve Level')
set_mode_args.add_argument("-mode", type=str, default=None,
                            help="Powerwall Mode: self_consumption, backup, or autonomous")
set_mode_args.add_argument("-reserve", type=int, default=None,
                            help="Set Battery Reserve Level [Default=20]")
set_mode_args.add_argument("-current", action="store_true", default=False,
                            help="Set Battery Reserve Level to Current Charge")
set_mode_args.add_argument("-gridcharging", type=str, default=None,
                            help="Enable Grid Charging Mode: on or off")
set_mode_args.add_argument("-gridexport", type=str, default=None,
                            help="Grid Export Mode: battery_ok, pv_only, or never")

get_mode_args = subparsers.add_parser("get", help='Get Powerwall Settings and Power Levels')
get_mode_args.add_argument("-format", type=str, default="text",
                            help="Output format: text, json, csv")
get_mode_args.add_argument("-host", type=str, default="",
                            help="IP address of Powerwall Gateway")
get_mode_args.add_argument("-password", type=str, default="",
                            help="Password for Powerwall Gateway")

version_args = subparsers.add_parser("version", help='Print version information')

# Add a global debug flag
p.add_argument("-debug", action="store_true", default=False, help="Enable debug output")

if len(sys.argv) == 1:
    p.print_help(sys.stderr)
    sys.exit(1)

# parse args
args = p.parse_args()
command = args.command

# Set Debug Mode
if args.debug:
    set_debug(True)

# Cloud Mode Setup
if command == 'setup':
    from pypowerwall import PyPowerwallCloud

    email = args.email
    print("pyPowerwall [%s] - Cloud Mode Setup\n" % version)
    # Run Setup
    c = PyPowerwallCloud(None, authpath=authpath)
    if c.setup(email):
        print(f"Setup Complete. Auth file {c.authfile} ready to use.")
    else:
        print("ERROR: Failed to setup Tesla Cloud Mode")
        sys.exit(1)

# FleetAPI Mode Setup
elif command == 'fleetapi':
    from pypowerwall import PyPowerwallFleetAPI

    print("pyPowerwall [%s] - FleetAPI Mode Setup\n" % version)
    # Run Setup
    c = PyPowerwallFleetAPI(None, authpath=authpath)
    if c.setup():
        print(f"Setup Complete. Config file {c.configfile} ready to use.")
    else:
        print("Setup Aborted.")
        sys.exit(1)

# TEDAPI Test
elif command == 'tedapi':
    from pypowerwall.tedapi.__main__ import run_tedapi_test
    run_tedapi_test(auto=True, debug=args.debug)

# Run Scan
elif command == 'scan':
    from pypowerwall import scan

    print("pyPowerwall [%s] - Scanner\n" % version)
    color = not args.nocolor
    ip = args.ip
    hosts = args.hosts
    timeout = args.timeout
    scan.scan(color, timeout, hosts, ip)

# Set Powerwall Mode
elif command == 'set':
    # If no arguments, print usage
    if not args.mode and not args.reserve and not args.current and not args.gridcharging and not args.gridexport:
        print("usage: pypowerwall set [-h] [-mode MODE] [-reserve RESERVE] [-current] [-gridcharging MODE] [-gridexport MODE]")
        sys.exit(1)
    import pypowerwall
    # Determine which cloud mode to use
    pw = pypowerwall.Powerwall(auto_select=True, host="", authpath=authpath)
    print(f"pyPowerwall [{version}] - Set Powerwall Mode and Power Levels using {pw.mode} mode.\n")
    if not pw.is_connected():
        print("ERROR: FleetAPI and Cloud access are not configured. Run 'fleetapi' or 'setup'.")
        sys.exit(1)
    if args.mode:
        mode = args.mode.lower()
        if mode not in ['self_consumption', 'backup', 'autonomous']:
            print("ERROR: Invalid Mode [%s] - must be one of self_consumption, backup, or autonomous" % mode)
            sys.exit(1)
        print("Setting Powerwall Mode to %s" % mode)
        pw.set_mode(mode)
    if args.reserve:
        reserve = args.reserve
        print("Setting Powerwall Reserve to %s" % reserve)
        pw.set_reserve(reserve)
    if args.current:
        current = float(pw.level())
        print("Setting Powerwall Reserve to Current Charge Level %s" % current)
        pw.set_reserve(current)
    if args.gridcharging:
        gridcharging = args.gridcharging.lower()
        if gridcharging not in ['on', 'off']:
            print("ERROR: Invalid Grid Charging Mode [%s] - must be on or off" % gridcharging)
            sys.exit(1)
        print("Setting Grid Charging Mode to %s" % gridcharging)
        pw.set_grid_charging(gridcharging)
    if args.gridexport:
        gridexport = args.gridexport.lower()
        if gridexport not in ['battery_ok', 'pv_only', 'never']:
            print("ERROR: Invalid Grid Export Mode [%s] - must be battery_ok, pv_only, or never" % gridexport)
            sys.exit(1)
        print("Setting Grid Export Mode to %s" % gridexport)
        pw.set_grid_export(gridexport)

# Get Powerwall Mode
elif command == 'get':
    import pypowerwall
    # Load email from auth file
    pw = pypowerwall.Powerwall(auto_select=True, authpath=authpath, password=args.password,
                                host=args.host)
    if args.format == 'text':
        print(f"pyPowerwall [{version}] - Get Powerwall Mode and Power Levels using {pw.mode} mode.\n")
    if not pw.is_connected():
        print("ERROR: Unable to connect. Set -host and -password or configure FleetAPI or Cloud access.")
        sys.exit(1)
    output = {
        'site': pw.site_name(),
        'site_id': pw.siteid or "N/A",
        'din': pw.din(),
        'mode': pw.get_mode(),
        'reserve': pw.get_reserve(),
        'current': pw.level(),
        'grid': pw.grid(),
        'home': pw.home(),
        'battery': pw.battery(),
        'solar': pw.solar(),
        'grid_charging': pw.get_grid_charging(),
        'grid_export_mode': pw.get_grid_export(),
    }
    if args.format == 'json':
        print(json.dumps(output, indent=2))
    elif args.format == 'csv':
        # create a csv header from keys
        header = ",".join(output.keys())
        print(header)
        values = ",".join(str(value) for value in output.values())
        print(values)
    else:
        # Table Output
        for item in output:
            name = item.replace("_", " ").title()
            print("  {:<18}{}".format(name, output[item]))
        print("")

# Print Version
elif command == 'version':
    print("pyPowerwall [%s]" % version)
# Print Usage
else:
    p.print_help()

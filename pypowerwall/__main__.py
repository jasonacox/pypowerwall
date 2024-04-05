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
from pypowerwall import version

# Global Variables
AUTHFILE = ".pypowerwall.auth"
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

get_mode_args = subparsers.add_parser("get", help='Get Powerwall Settings and Power Levels')
get_mode_args.add_argument("-format", type=str, default="text",
                            help="Output format: text, json, csv")

version_args = subparsers.add_parser("version", help='Print version information')

if len(sys.argv) == 1:
    p.print_help(sys.stderr)
    sys.exit(1)

# parse args
args = p.parse_args()
command = args.command

# Cloud Mode Setup
if command == 'setup':
    from pypowerwall import PyPowerwallCloud

    email = args.email
    print("pyPowerwall [%s] - Cloud Mode Setup\n" % version)
    # Run Setup
    c = PyPowerwallCloud(None, authpath=authpath)
    if c.setup(email):
        print("Setup Complete. Auth file %s ready to use." % AUTHFILE)
    else:
        print("ERROR: Failed to setup Tesla Cloud Mode")
        exit(1)
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
    import pypowerwall
    print("pyPowerwall [%s] - Set Powerwall Mode and Power Levels\n" % version)
    # Load email from auth file
    auth_file = authpath + AUTHFILE
    if not os.path.exists(auth_file):
        print("ERROR: Auth file %s not found. Run 'setup' to create." % auth_file)
        exit(1)
    with open(auth_file, 'r') as file:
        auth = json.load(file)
    email = list(auth.keys())[0]
    pw = pypowerwall.Powerwall(email=email, host="", authpath=authpath)
    if args.mode:
        mode = args.mode.lower()
        if mode not in ['self_consumption', 'backup', 'autonomous']:
            print("ERROR: Invalid Mode [%s] - must be one of self_consumption, backup, or autonomous" % mode)
            exit(1)
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
# Get Powerwall Mode
elif command == 'get':
    import pypowerwall
    # Load email from auth file
    auth_file = authpath + AUTHFILE
    if not os.path.exists(auth_file):
        print("ERROR: Auth file %s not found. Run 'setup' to create." % auth_file)
        exit(1)
    with open(auth_file, 'r') as file:
        auth = json.load(file)
    email = list(auth.keys())[0]
    pw = pypowerwall.Powerwall(email=email, host="", authpath=authpath)
    output = {
        'site': pw.site_name(),
        'din': pw.din(),
        'mode': pw.get_mode(),
        'reserve': pw.get_reserve(),
        'current': pw.level(),
        'grid': pw.grid(),
        'home': pw.home(),
        'battery': pw.battery(),
        'solar': pw.solar(),
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
        print("pyPowerwall [%s] - Set Powerwall Mode and Power Levels\n" % version)
        # Table Output
        for item in output:
            name = item.replace("_", " ").title()
            print("  {:<15}{}".format(name, output[item]))

# Print Version
elif command == 'version':
    print("pyPowerwall [%s]" % version)
# Print Usage
else:
    p.print_help()

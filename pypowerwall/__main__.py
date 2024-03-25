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
# Print Usage
else:
    p.print_help()

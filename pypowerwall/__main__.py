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


def main():
    """Main entry point for the pypowerwall CLI."""
    # Global Variables
    authpath = os.getenv("PW_AUTH_PATH", "")

    timeout = 1.0
    hosts = 30
    color = True
    ip = None
    email = None

    # Setup parser and groups
    p = argparse.ArgumentParser(prog="PyPowerwall", description=f"PyPowerwall Module v{version}")
    subparsers = p.add_subparsers(dest="command", title='commands (run <command> -h to see usage information)',
                                  required=True)

    setup_args = subparsers.add_parser("setup", help='Setup Tesla Login for Cloud Mode access')
    setup_args.add_argument("-email", type=str, default=email, help="Email address for Tesla Login.")

    login_args = subparsers.add_parser("login", help='Authenticate with Tesla and get refresh token')
    login_args.add_argument("-email", type=str, default=None, help="Tesla account email address")
    login_args.add_argument("-debug", action="store_true", default=False,
                           help="Enable debug output for auth flow")
    login_args.add_argument("-headless", action="store_true", default=False,
                           help="Manual mode — paste URL instead of opening browser")
    login_args.add_argument("-timeout", type=int, default=120,
                           help="Seconds to wait for browser login [Default=120]")
    login_args.add_argument("-region", type=str, default="us", choices=["us", "cn"],
                           help="Tesla region: 'us' (default) or 'cn' (China)")

    authtoken_args = subparsers.add_parser("authtoken",
                                            help='Get refresh token via local browser login (prints to stdout)')
    authtoken_args.add_argument("-debug", action="store_true", default=False,
                               help="Enable debug output for auth flow")
    authtoken_args.add_argument("-region", type=str, default="us", choices=["us", "cn"],
                                help="Tesla region: 'us' (default) or 'cn' (China)")

    fleetapi_args = subparsers.add_parser("fleetapi", help='Setup Tesla FleetAPI for Cloud Mode access')

    tedapi_args = subparsers.add_parser("tedapi", help='Test TEDAPI connection to Powerwall Gateway')
    tedapi_args.add_argument("gw_pwd", type=str, nargs="?", default=None,
                             help="Powerwall Gateway Password")
    tedapi_args.add_argument("-gw_pwd", dest="gw_pwd_option", metavar="GW_PWD", type=str, default=None,
                             help="Powerwall Gateway Password")
    tedapi_args.add_argument("-host", type=str, default=None,
                             help="IP address of Powerwall Gateway")
    tedapi_args.add_argument("-v1r", action="store_true", default=False,
                             help="Use v1r LAN TEDAPI mode")
    tedapi_args.add_argument("-password", type=str, default=None,
                             help="Customer password for v1r mode (defaults to last 5 of gw_pwd)")
    tedapi_args.add_argument("-rsa_key_path", type=str, default=None,
                             help="Path to RSA private key PEM for v1r mode")
    tedapi_args.add_argument("-wifi_host", type=str, default=None,
                             help="Optional WiFi TEDAPI host for v1r follower fallback")

    register_args = subparsers.add_parser("register",
                                          help='Register RSA key with Powerwall via Tesla Owner API or Fleet API (for v1r LAN mode)')

    scan_args = subparsers.add_parser("scan", help='Scan local network for Powerwall gateway')
    scan_args.add_argument("-timeout", type=float, default=timeout,
                           help=f"Seconds to wait per host [Default={timeout:.1f}]")
    scan_args.add_argument("-nocolor", action="store_true", default=not color,
                           help="Disable color text output.")
    scan_args.add_argument("network", type=str, nargs="?", default=None, metavar="CIDR",
                           help="IPv4 CIDR network to scan (e.g. 192.168.1.0/24). Auto-detects if omitted.")
    scan_args.add_argument("-ip", type=str, default=None,
                           help="IP address within network to scan.")
    scan_args.add_argument("-hosts", type=int, default=hosts,
                           help=f"Number of hosts to scan simultaneously [Default={hosts}, Max=256]")
    scan_args.add_argument("-json", action="store_true", default=False,
                           help="Output discovered gateways as JSON and suppress all other output.")

    set_mode_args = subparsers.add_parser("set", help='Set Powerwall Mode and Reserve Level')
    set_mode_args.add_argument("-mode", type=str, default=None,
                                help="Powerwall Mode: self_consumption, backup, or autonomous")
    set_mode_args.add_argument("-reserve", type=int, default=-1,
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
    get_mode_args.add_argument("-mode", type=str, default=None,
                                help="Force connection mode: local, cloud, fleetapi, or tedapi")

    version_args = subparsers.add_parser("version", help='Print version information')

    # Add a global debug flag
    p.add_argument("-debug", action="store_true", default=False, help="Enable debug output")
    p.add_argument("-authpath", type=str, default=None,
                   help="Override auth path (default uses PW_AUTH_PATH env var)")

    if len(sys.argv) == 1:
        p.print_help(sys.stderr)
        sys.exit(1)

    # parse args
    args = p.parse_args()
    command = args.command

    # Priority: command-line value > PW_AUTH_PATH env var > current directory
    if args.authpath is not None:  # user explicitly provided (could be "" to force CWD)
        if args.authpath.strip() == "":
            authpath = ""  # current directory
        else:
            authpath = os.path.expanduser(args.authpath)
    else:
        # If env var produced None (shouldn't) or still None-like, fallback to "" (cwd)
        authpath = authpath or ""

    # Debug: Show final authpath resolution before using it
    if args.debug:
        # Show absolute path if non-empty, otherwise indicate current directory
        display_authpath = os.path.abspath(authpath) if authpath else os.path.abspath(os.getcwd())
        print(f"[DEBUG] Using auth path: {display_authpath} (raw='{authpath}')")

    # Set Debug Mode
    if args.debug:
        set_debug(True)

    # Cloud Mode Setup
    elif command == 'setup':
        from pypowerwall.tesla_auth import login as tesla_login
        from pypowerwall import PyPowerwallCloud

        email = args.email
        print("pyPowerwall [%s] - Cloud Mode Setup\n" % version)

        # Check for existing auth file
        auth_file = os.path.join(authpath, ".pypowerwall.auth") if authpath else ".pypowerwall.auth"
        overwrite = False
        if os.path.isfile(auth_file) and not email:
            try:
                with open(auth_file) as f:
                    data = json.load(f)
                email = list(data.keys())[0]
                print("  Found existing auth file: %s" % auth_file)
                resp = input("  Overwrite existing file? [y/N]: ").strip()
                if resp.lower() == "y":
                    overwrite = True
                    email = None
                    os.remove(auth_file)
                # else: keep existing, just re-select site
            except Exception:
                pass

        token_data = None
        if email is None or not os.path.isfile(auth_file):
            # Get token via native browser (macOS) or headless (Linux/Windows/SSH)
            refresh_token, detected_email, token_data = tesla_login(
                headless=args.headless,
                region=args.region,
                debug=getattr(args, 'debug', False),
            )
            email = detected_email or email
            if not email:
                email = input("\nTesla account email: ").strip()

        # Run Setup with token data (or None if using existing file)
        c = PyPowerwallCloud(email, authpath=authpath)
        if c.setup(email=email, token_data=token_data):
            print(f"\nSetup Complete. Auth file {c.authfile} ready to use.")
        else:
            print("\nERROR: Failed to setup Tesla Cloud Mode")
            sys.exit(1)

    # Login to get refresh token (DEPRECATED - use 'setup' instead)
    elif command == 'login':
        print("⚠️  'login' command is deprecated. Use 'setup' instead.")
        print("   python -m pypowerwall setup")
        sys.exit(1)

    # Get auth token (local only, print to stdout)
    elif command == 'authtoken':
        from pypowerwall.tesla_auth import get_authtoken
        try:
            print("\n⚡ Tesla Authentication — pypowerwall authtoken")
            print("=" * 60)
            token = get_authtoken(region=args.region, debug=getattr(args, 'debug', False))
            print("\n" + "=" * 60)
            print("Refresh Token:")
            print("-" * 60)
            print(token)
            print("-" * 60)
            print("\nCopy the token above and use it on your remote machine.")
        except (KeyboardInterrupt, EOFError):
            print("\nLogin cancelled.")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Login failed: {e}")
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
        tedapi_argv = []
        gw_pwd = args.gw_pwd_option or args.gw_pwd
        if gw_pwd:
            tedapi_argv.extend(['-gw_pwd', gw_pwd])
        if args.host:
            tedapi_argv.extend(['-host', args.host])
        if args.v1r:
            tedapi_argv.append('-v1r')
        if args.password:
            tedapi_argv.extend(['-password', args.password])
        if args.rsa_key_path:
            tedapi_argv.extend(['-rsa_key_path', args.rsa_key_path])
        if args.wifi_host:
            tedapi_argv.extend(['-wifi_host', args.wifi_host])
        if args.debug:
            tedapi_argv.append('--debug')
        run_tedapi_test(argv=tedapi_argv, debug=args.debug)

    # Fleet API RSA Key Registration (v1r LAN mode)
    elif command == 'register':
        from pypowerwall.v1r_register import main as fleet_register_main
        fleet_register_main()

    # Run Scan
    elif command == 'scan':
        from pypowerwall import scan
        json_output = args.json
        if not json_output:
            print("pyPowerwall [%s] - Scanner\n" % version)
        results = scan.scan(
            cidr=args.network or args.ip,
            max_threads=args.hosts,
            timeout=args.timeout,
            color=not args.nocolor,
            interactive=not json_output,
            json_output=json_output,
        )
        if json_output:
            print(json.dumps(results, indent=2))

    # Set Powerwall Mode
    elif command == 'set':
        # If no arguments, print usage
        if not args.mode and args.reserve == -1 and not args.current and not args.gridcharging and not args.gridexport:
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
        if args.reserve != -1:
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
        # Determine connection mode
        if args.mode:
            mode = args.mode.lower()
            if mode == 'local':
                pw = pypowerwall.Powerwall(host=args.host, password=args.password, authpath=authpath)
            elif mode == 'cloud':
                pw = pypowerwall.Powerwall(cloudmode=True, fleetapi=False, authpath=authpath)
            elif mode == 'fleetapi':
                pw = pypowerwall.Powerwall(cloudmode=True, fleetapi=True, authpath=authpath)
            else:
                print(f"ERROR: Invalid mode '{mode}' - must be one of: local, cloud, fleetapi")
                sys.exit(1)
        else:
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


if __name__ == '__main__':
    main()


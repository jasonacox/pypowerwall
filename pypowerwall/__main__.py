# pyPowerWall Module - CLI Entry Point
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 CLI Usage:
    python -m pypowerwall <command> [options]

 Commands:
    setup       Setup Tesla Cloud, Fleet API, or v1r LAN TEDAPI access
    get         Get Powerwall settings and power levels
    set         Set Powerwall operating mode and reserve level
    tedapi      Test TEDAPI connection to Powerwall Gateway
    scan        Scan local network for Powerwall gateway
    register    Register RSA key for v1r LAN mode
    authtoken   Get Tesla Cloud refresh token
    version     Print version information

"""

import argparse
import os
import sys
import json

# Modules
from pypowerwall import version, set_debug


def _email_from_auth(authpath):
    """Extract email from .pypowerwall.auth file if it exists."""
    auth_file = os.path.join(authpath, ".pypowerwall.auth") if authpath else ".pypowerwall.auth"
    try:
        with open(auth_file) as f:
            data = json.load(f)
        return list(data.keys())[0]
    except Exception:
        return None


def _add_connection_args(parser):
    """Add mutually exclusive connection mode flags and credential args to a subparser.

    Modes (choose at most one):
      -local      Local Powerwall Gateway  (needs -host, -password)
      -cloud      Tesla Cloud              (needs prior 'setup')
      -fleetapi   Tesla Fleet API          (needs prior 'setup -fleetapi')
      -tedapi     TEDAPI direct            (needs -gw_pwd)
      -v1r        v1r LAN TEDAPI           (needs -gw_pwd and RSA private key)
      (none)      Auto-select from available configuration
    """
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("-local", action="store_true", default=False,
                     help="Connect via local Powerwall Gateway (requires -host)")
    grp.add_argument("-cloud", action="store_true", default=False,
                     help="Connect via Tesla Cloud (requires prior 'setup')")
    grp.add_argument("-fleetapi", action="store_true", default=False,
                     help="Connect via Tesla Fleet API (requires prior 'setup -fleetapi')")
    grp.add_argument("-tedapi", action="store_true", default=False,
                     help="Connect via TEDAPI (requires -gw_pwd)")
    grp.add_argument("-v1r", action="store_true", default=False,
                     help="Connect via v1r LAN TEDAPI (requires -gw_pwd and RSA private key)")
    parser.add_argument("-host", type=str, default="",
                        help="IP address of Powerwall Gateway [local/tedapi/v1r]")
    parser.add_argument("-password", type=str, default="",
                        help="Customer password [local/v1r; v1r defaults to last 5 of gw_pwd]")
    parser.add_argument("-gw_pwd", type=str, default=None,
                        help="Gateway password [required for -tedapi and -v1r]")
    parser.add_argument("-rsa_key_path", type=str, default=None,
                        help="RSA private key PEM path [v1r; default: ./tedapi_rsa_private.pem]")


def _build_powerwall(args, authpath):
    """Construct a Powerwall instance from the parsed connection mode flags."""
    import pypowerwall
    if getattr(args, 'v1r', False):
        if not args.gw_pwd:
            print("ERROR: -v1r requires -gw_pwd <gateway_password>")
            sys.exit(1)
        if not args.host:
            print("ERROR: -v1r requires -host <gateway_ip>")
            sys.exit(1)
        rsa_key_path = args.rsa_key_path
        if not rsa_key_path:
            default_key = "tedapi_rsa_private.pem"
            authpath_key = os.path.join(authpath, default_key) if authpath else None
            if authpath_key and os.path.isfile(authpath_key):
                rsa_key_path = authpath_key
            elif os.path.isfile(default_key):
                rsa_key_path = default_key
            else:
                search_dirs = ([authpath] if authpath else []) + ["."]
                print(
                    f"ERROR: -v1r requires an RSA private key. "
                    f"Specify -rsa_key_path or place '{default_key}' in one of: {', '.join(search_dirs)}"
                )
                sys.exit(1)
        return pypowerwall.Powerwall(
            host=args.host or None,
            password=args.password or None,
            gw_pwd=args.gw_pwd,
            rsa_key_path=rsa_key_path,
            authpath=authpath,
        )
    if getattr(args, 'tedapi', False):
        if not args.gw_pwd:
            print("ERROR: -tedapi requires -gw_pwd <gateway_password>")
            sys.exit(1)
        host = args.host or "192.168.91.1"
        return pypowerwall.Powerwall(host=host, gw_pwd=args.gw_pwd, authpath=authpath)
    if getattr(args, 'local', False):
        return pypowerwall.Powerwall(host=args.host, password=args.password, authpath=authpath)
    if getattr(args, 'cloud', False):
        auth_file = os.path.join(authpath, ".pypowerwall.auth") if authpath else ".pypowerwall.auth"
        if not os.path.isfile(auth_file):
            print(f"ERROR: Tesla Cloud auth file not found: {auth_file}")
            print("  Run 'python -m pypowerwall setup' to authenticate.")
            sys.exit(1)
        email = _email_from_auth(authpath)
        return pypowerwall.Powerwall(cloudmode=True, fleetapi=False, authpath=authpath, email=email)
    if getattr(args, 'fleetapi', False):
        from pypowerwall.fleetapi.fleetapi import CONFIGFILE as FLEET_CONFIGFILE
        config_file = os.path.join(authpath, FLEET_CONFIGFILE) if authpath else FLEET_CONFIGFILE
        if not os.path.isfile(config_file):
            print(f"ERROR: Fleet API config file not found: {config_file}")
            print("  Run 'python -m pypowerwall setup -fleetapi' to configure Fleet API access.")
            sys.exit(1)
        email = _email_from_auth(authpath)
        return pypowerwall.Powerwall(cloudmode=True, fleetapi=True, authpath=authpath, email=email)
    # No mode flag — auto-select from available configuration
    return pypowerwall.Powerwall(
        auto_select=True,
        authpath=authpath,
        password=getattr(args, 'password', ''),
        host=getattr(args, 'host', ''),
    )


def main():
    """Main entry point for the pypowerwall CLI."""
    # Global Variables
    authpath = os.getenv("PW_AUTH_PATH", "")

    timeout = 1.0
    hosts = 30

    # Shared parent parser: flags that apply to every subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-debug", action="store_true", default=False,
                        help="Enable debug output")
    common.add_argument("-authpath", type=str, default=None,
                        help="Override auth path (default uses PW_AUTH_PATH env var)")

    # Setup parser and groups
    p = argparse.ArgumentParser(prog="PyPowerwall", description=f"PyPowerwall Module v{version}",
                                parents=[common])
    subparsers = p.add_subparsers(dest="command", title='commands (run <command> -h to see usage information)',
                                  required=True)

    setup_args = subparsers.add_parser("setup", parents=[common],
                                       help='Setup Tesla Cloud, Fleet API, or v1r LAN TEDAPI access')
    setup_grp = setup_args.add_mutually_exclusive_group()
    setup_grp.add_argument("-cloud", action="store_true", default=False,
                           help="Setup Tesla Cloud Mode (default)")
    setup_grp.add_argument("-fleetapi", action="store_true", default=False,
                           help="Setup Tesla Fleet API mode")
    setup_grp.add_argument("-v1r", action="store_true", default=False,
                           help="Register RSA key with Powerwall for v1r LAN TEDAPI mode")
    setup_args.add_argument("-email", type=str, default=None, help="Email address for Tesla Login.")
    setup_args.add_argument("-headless", action="store_true", default=False,
                           help="Force headless/token-paste mode — skip the browser window and use "
                                "the SSH-friendly token-paste flow. Run 'python -m pypowerwall authtoken' "
                                "on a local machine to get a token, then paste it here.")
    setup_args.add_argument("-region", type=str, default="us", choices=["us", "cn"],
                           help="Tesla region: 'us' (default) or 'cn' (China)")

    login_args = subparsers.add_parser("login", parents=[common],
                                       help='Authenticate with Tesla Cloud and get refresh token (deprecated: use setup)')
    login_args.add_argument("-email", type=str, default=None, help="Tesla account email address")
    login_args.add_argument("-headless", action="store_true", default=False,
                           help="Manual mode — paste URL instead of opening browser")
    login_args.add_argument("-timeout", type=int, default=120,
                           help="Seconds to wait for browser login [Default=120]")
    login_args.add_argument("-region", type=str, default="us", choices=["us", "cn"],
                           help="Tesla region: 'us' (default) or 'cn' (China)")

    authtoken_args = subparsers.add_parser("authtoken", parents=[common],
                                            help='Get Tesla Cloud refresh token via local browser login (prints to stdout)')
    authtoken_args.add_argument("-region", type=str, default="us", choices=["us", "cn"],
                                help="Tesla region: 'us' (default) or 'cn' (China)")

    fleetapi_args = subparsers.add_parser("fleetapi", parents=[common],
                                           help='[Deprecated] Setup Tesla FleetAPI — use: setup -fleetapi')

    tedapi_args = subparsers.add_parser("tedapi", parents=[common],
                                        help='Test TEDAPI connection to Powerwall Gateway')
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

    register_args = subparsers.add_parser("register", parents=[common],
                                           help='Register RSA key with Powerwall via Tesla Owner API or Fleet API (for v1r LAN mode)')

    scan_args = subparsers.add_parser("scan", parents=[common],
                                      help='Scan local network for Powerwall gateway')
    scan_args.add_argument("-timeout", type=float, default=timeout,
                           help=f"Seconds to wait per host [Default={timeout:.1f}]")
    scan_args.add_argument("-nocolor", action="store_true", default=False,
                           help="Disable color text output.")
    scan_args.add_argument("network", type=str, nargs="?", default=None, metavar="CIDR",
                           help="IPv4 CIDR network to scan (e.g. 192.168.1.0/24). Auto-detects if omitted.")
    scan_args.add_argument("-ip", type=str, default=None,
                           help="IP address within network to scan.")
    scan_args.add_argument("-hosts", type=int, default=hosts,
                           help=f"Number of hosts to scan simultaneously [Default={hosts}, Max=256]")
    scan_args.add_argument("-json", action="store_true", default=False,
                           help="Output discovered gateways as JSON and suppress all other output.")

    set_mode_args = subparsers.add_parser("set", parents=[common],
                                           help='Set Powerwall operating mode and reserve level')
    _add_connection_args(set_mode_args)
    set_mode_args.add_argument("-mode", type=str, default=None,
                                help="Operating mode: self_consumption, backup, or autonomous")
    set_mode_args.add_argument("-reserve", type=int, default=-1,
                                help="Set Battery Reserve Level [Default=20]")
    set_mode_args.add_argument("-current", action="store_true", default=False,
                                help="Set Battery Reserve Level to Current Charge")
    set_mode_args.add_argument("-gridcharging", type=str, default=None,
                                help="Grid Charging Mode: on or off")
    set_mode_args.add_argument("-gridexport", type=str, default=None,
                                help="Grid Export Mode: battery_ok, pv_only, or never")

    get_mode_args = subparsers.add_parser("get", parents=[common],
                                           help='Get Powerwall settings and power levels')
    _add_connection_args(get_mode_args)
    get_mode_args.add_argument("-format", type=str, default="text",
                                help="Output format: text, json, csv")
    # Deprecated: old string -mode flag for connection selection; hidden from help
    get_mode_args.add_argument("-mode", type=str, default=None, dest="legacy_mode",
                                help=argparse.SUPPRESS)

    version_args = subparsers.add_parser("version", parents=[common],
                                         help='Print version information')

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

    # Debug setup
    if args.debug:
        display_authpath = os.path.abspath(authpath) if authpath else os.path.abspath(os.getcwd())
        print(f"[DEBUG] Using auth path: {display_authpath} (raw='{authpath}')")
        set_debug(True)

    # Cloud, FleetAPI, or v1r Setup
    if command == 'setup':
        if args.v1r:
            from pypowerwall.v1r_register import main as fleet_register_main
            fleet_register_main(authpath=authpath)
            return

        if args.fleetapi:
            from pypowerwall import PyPowerwallFleetAPI
            print("pyPowerwall [%s] - FleetAPI Mode Setup\n" % version)
            c = PyPowerwallFleetAPI(None, authpath=authpath)
            if c.setup():
                print(f"Setup Complete. Config file {c.configfile} ready to use.")
            else:
                print("Setup Aborted.")
                sys.exit(1)
            return

        # Cloud setup (default, also explicit with -cloud)
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
            # Get token via native browser (macOS/desktop) or token-paste flow (SSH/headless).
            # -headless explicitly forces the token-paste flow; SSH sessions are auto-detected.
            refresh_token, detected_email, token_data = tesla_login(
                headless=args.headless,
                region=args.region,
                debug=getattr(args, 'debug', False),
            )
            email = detected_email or email
            if not email:
                email = input("\nTesla account email: ").strip()
            # If headless/remote, token_data is empty — write token manually
            if not token_data:
                from pypowerwall.tesla_auth import save_token
                save_token(
                    {"refresh_token": refresh_token, "token_type": "Bearer", "expires_in": 28800},
                    path=auth_file, email=email, region=args.region,
                )
                token_data = None  # signal setup() to use existing file

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

    # FleetAPI Mode Setup (deprecated — use: setup -fleetapi)
    elif command == 'fleetapi':
        print("⚠️  'fleetapi' command is deprecated. Use 'setup -fleetapi' instead.")
        print("   python -m pypowerwall setup -fleetapi")
        from pypowerwall import PyPowerwallFleetAPI
        print("\npyPowerwall [%s] - FleetAPI Mode Setup\n" % version)
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
        # If no action arguments, print usage
        if not args.mode and args.reserve == -1 and not args.current and not args.gridcharging and not args.gridexport:
            set_mode_args.print_usage()
            sys.exit(1)
        pw = _build_powerwall(args, authpath)
        if not pw.is_connected():
            print("ERROR: Unable to connect. Check connection mode and credentials.")
            sys.exit(1)
        print(f"pyPowerwall [{version}] - Set Powerwall settings using {pw.mode} mode.\n")
        if args.mode:
            mode = args.mode.lower()
            if mode not in ['self_consumption', 'backup', 'autonomous']:
                print("ERROR: Invalid Mode [%s] - must be one of self_consumption, backup, or autonomous" % mode)
                sys.exit(1)
            print("Setting Powerwall Mode to %s" % mode)
            pw.set_mode(mode)
        if args.reserve != -1:
            reserve = args.reserve
            if reserve > 80 and pw.mode in ('cloud', 'fleetapi'):
                print(f"WARNING: Tesla cloud/FleetAPI limits backup reserve to 80% max. "
                      f"Requesting {reserve}% but Tesla may cap it at 80%. "
                      f"Use TEDAPI v1r mode (-v1r) to set reserve above 80%.")
            print("Setting Powerwall Reserve to %s" % reserve)
            pw.set_reserve(reserve)
            if reserve > 80 and pw.mode in ('cloud', 'fleetapi'):
                actual = pw.get_reserve(scale=True, force=True)
                if actual is not None and actual <= 80:
                    print(f"NOTE: Tesla capped reserve at {actual}% instead of {reserve}%.")
        if args.current:
            current = float(pw.level())
            if current > 80 and pw.mode in ('cloud', 'fleetapi'):
                print(f"WARNING: Tesla cloud/FleetAPI limits backup reserve to 80% max. "
                      f"Current charge is {current:.0f}% but Tesla may cap reserve at 80%. "
                      f"Use TEDAPI v1r mode (-v1r) to set reserve above 80%.")
            print("Setting Powerwall Reserve to Current Charge Level %s" % current)
            pw.set_reserve(current)
            if current > 80 and pw.mode in ('cloud', 'fleetapi'):
                actual = pw.get_reserve(scale=True, force=True)
                if actual is not None and actual <= 80:
                    print(f"NOTE: Tesla capped reserve at {actual}% instead of {current:.0f}%.")
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
        # Backward compat: deprecated 'get -mode <value>' → new boolean flag
        if getattr(args, 'legacy_mode', None):
            # Check for conflict: boolean flag already set by user
            boolean_flags = ['local', 'cloud', 'fleetapi', 'tedapi', 'v1r']
            active_booleans = [f for f in boolean_flags if getattr(args, f, False)]
            if active_booleans:
                print(f"ERROR: Cannot use both -{active_booleans[0]} flag and deprecated -mode {args.legacy_mode}. "
                      f"Use only the boolean flag (e.g. -{args.legacy_mode}).")
                sys.exit(1)
            _legacy_mode_map = {
                'local': 'local', 'cloud': 'cloud', 'fleetapi': 'fleetapi',
                'tedapi': 'tedapi', 'v1r': 'v1r',
            }
            _mapped = _legacy_mode_map.get(args.legacy_mode.lower())
            if _mapped:
                print(f"⚠️  Deprecated: 'get -mode {args.legacy_mode}' — use 'get -{args.legacy_mode}' instead.")
                setattr(args, _mapped, True)
            else:
                print(f"ERROR: Unknown connection mode '{args.legacy_mode}'. Use -local, -cloud, -fleetapi, -tedapi, or -v1r.")
                sys.exit(1)
        pw = _build_powerwall(args, authpath)
        if not pw.is_connected():
            print("ERROR: Unable to connect. Set -host and -password or configure FleetAPI or Cloud access.")
            sys.exit(1)
        if args.format == 'text':
            print(f"pyPowerwall [{version}] - Get Powerwall settings using {pw.mode} mode.\n")
        output = {
            'site': pw.site_name(),
            'site_id': pw.siteid or "N/A",
            'din': pw.din(),
            'firmware': pw.version(),
            'mode': pw.get_mode(),
            'reserve': pw.get_reserve(),
            'soc': pw.level(scale=True),
            'grid_status': pw.grid_status(),
            'grid': pw.grid(),
            'home': pw.home(),
            'battery': pw.battery(),
            'solar': pw.solar(),
            'grid_charging': pw.get_grid_charging(),
            'grid_export_mode': pw.get_grid_export(),
            'time_remaining': pw.get_time_remaining(),
        }
        if args.format == 'json':
            print(json.dumps(output, indent=2))
        elif args.format == 'csv':
            header = ",".join(output.keys())
            print(header)
            values = ",".join("N/A" if v is None else str(v) for v in output.values())
            print(values)
        else:
            # Table Output — override display labels for terse keys
            _labels = {
                'site_id': 'Site ID',
                'din': 'DIN',
                'soc': 'Battery Level',
            }
            for item in output:
                name = _labels.get(item, item.replace("_", " ").title())
                value = output[item]
                print("  {:<18}{}".format(name, "N/A" if value is None else value))
            print("")

    # Print Version
    elif command == 'version':
        print("pyPowerwall [%s]" % version)
    # Print Usage
    else:
        p.print_help()


if __name__ == '__main__':
    main()


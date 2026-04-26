# pyPowerwall - Tesla TEDAPI Class Main
# -*- coding: utf-8 -*-
"""
 Tesla TEDAPI Class - Command Line Test

 This script tests the TEDAPI class by connecting to a Tesla Powerwall Gateway
"""


def _build_tedapi_arg_parser(default_host):
    """Build the CLI parser used by the TEDAPI test command."""
    import argparse

    parser = argparse.ArgumentParser(description='Tesla Powerwall Gateway TEDAPI Reader')
    parser.add_argument('gw_pwd', nargs='?', help='Powerwall Gateway Password')
    parser.add_argument('-gw_pwd', dest='gw_pwd_option', metavar='GW_PWD', default=None,
                        help='Powerwall Gateway Password')
    parser.add_argument('-host', '--gw_ip', dest='host', default=default_host,
                        help='Powerwall Gateway IP Address')
    parser.add_argument('-v1r', action='store_true', help='Use v1r LAN TEDAPI mode')
    parser.add_argument('-password', default=None,
                        help='Customer password for v1r mode (defaults to last 5 of gw_pwd)')
    parser.add_argument('-rsa_key_path', default=None,
                        help='Path to RSA private key PEM for v1r mode')
    parser.add_argument('-wifi_host', default=None,
                        help='Optional WiFi TEDAPI host for v1r follower fallback')
    parser.add_argument('--debug', action='store_true', help='Enable Debug Output')
    return parser


def run_tedapi_test(argv=None, debug=False):
    # Imports
    from pypowerwall.tedapi import TEDAPI, GW_IP
    from pypowerwall import __version__
    import json
    import sys
    import requests
    import logging

    # Print header
    print(f"pyPowerwall - Powerwall Gateway TEDAPI Reader [v{__version__}]")

    # Setup Logging
    log = logging.getLogger(__name__)

    def set_debug(toggle=True, color=True):
        """Enable verbose logging"""
        if toggle:
            if color:
                logging.basicConfig(format='\x1b[31;1m%(levelname)s:%(message)s\x1b[0m', level=logging.DEBUG)
            else:
                logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.debug('pyPowerwall TEDAPI version %s', __version__)
            log.debug('Python %s on %s', sys.version, sys.platform)
        else:
            log.setLevel(logging.NOTSET)

    # Check for arguments using argparse
    parser = _build_tedapi_arg_parser(GW_IP)
    args = parser.parse_args(argv)
    gw_pwd = args.gw_pwd_option or args.gw_pwd
    if args.debug:
        set_debug(True)
    elif debug:
        set_debug(True)
    host = args.host

    if args.v1r:
        if not args.rsa_key_path:
            parser.error('-v1r requires -rsa_key_path')
        if not args.password and not gw_pwd:
            parser.error('-v1r requires -password or -gw_pwd')
        password = args.password or gw_pwd[-5:]
        if gw_pwd is None:
            gw_pwd = ""
    else:
        password = None

    # Check that host is listening to port 443
    url = f'https://{host}'
    log.debug(f"Checking Powerwall Gateway at {url}")
    print(f" - Connecting to {url}...", end="")
    try:
        resp = requests.get(url, verify=False, timeout=5)
        log.debug(f"Connection to Powerwall Gateway successful, code {resp.status_code}.")
        print(" SUCCESS")
    except Exception as e:
        print(" FAILED")
        print()
        print(f"ERROR: Unable to connect to Powerwall Gateway {host} on port 443.")
        print("Please verify your host has a route to the Gateway.")
        print(f"\nError details: {e}")
        sys.exit(1)

    # Get GW_PWD from User if not provided
    if gw_pwd is None:
        while not gw_pwd:
            try:
                gw_pwd = input("\nEnter Powerwall Gateway Password: ")
            except KeyboardInterrupt:
                print("")
                sys.exit(1)
            except Exception as e:
                print(f"Error: {e}")
                sys.exit(1)
            if not gw_pwd:
                print("Password Required")

    # Create TEDAPI Object and get Configuration and Status
    print()
    print(f"Connecting to Powerwall Gateway {host}")
    if args.v1r:
        ted = TEDAPI(gw_pwd=gw_pwd or "", host=host, v1r=True,
                     password=password, rsa_key_path=args.rsa_key_path,
                     wifi_host=args.wifi_host)
    else:
        ted = TEDAPI(gw_pwd, host=host)
    if ted.din is None:
        print("\nERROR: Unable to connect to Powerwall Gateway. Check your password and try again")
        sys.exit(1)
    config = ted.get_config() or {}
    status = ted.get_status() or {}
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
    if nominalFullPackEnergyWh == 0:
        print(f"   - Battery Full Charge Unknown ({nominalEnergyRemainingWh}Wh of {nominalFullPackEnergyWh}Wh)")
    else:
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

if __name__ == "__main__":
    run_tedapi_test()

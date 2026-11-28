# pyPowerwall - Tesla TEDAPI Class Main
# -*- coding: utf-8 -*-
"""
 Tesla TEDAPI Class - Command Line Test

 This script tests the TEDAPI class by connecting to a Tesla Powerwall Gateway
"""


def _build_tedapi_arg_parser(default_host):
    """Build the CLI parser used by the TEDAPI test command."""
    import argparse

    from pypowerwall.tedapi.api_version import TEDAPIApiVersion
    from pypowerwall.tedapi.auth_mode import AuthMode

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
    parser.add_argument('-tedapi_api_version', default=TEDAPIApiVersion.V2024_06.value,
                        choices=[v.value for v in TEDAPIApiVersion],
                        help='Query/protobuf version set (default: V2024_06)')
    parser.add_argument('-firmware', action='store_true',
                        help='Fetch and print the gateway firmware version, then exit')
    parser.add_argument('-network', action='store_true',
                        help='Fetch and print the gateway network status (Wi-Fi, Ethernet, '
                             'cellular), then exit')
    parser.add_argument('-clients', action='store_true',
                        help='Fetch and print the gateway\'s authorized clients (paired keys), then exit')
    parser.add_argument('-add_client', metavar='KEY_FILE', default=None,
                        help='Register the RSA key in KEY_FILE (PEM, public or private) with the '
                             'gateway, then exit. Needs -v1r. Locally added keys have not been '
                             'seen to verify; use "python -m pypowerwall register" for a usable key')
    parser.add_argument('-description', default='pypowerwall',
                        help='With -add_client: label stored with the key (default: pypowerwall)')
    parser.add_argument('-remove_client', metavar='KEY', default=None,
                        help='Remove an authorized client, then exit. KEY is a fingerprint prefix '
                             '(8+ hex characters, from -clients), the listed base64 key, or a PEM '
                             'key file. Needs -v1r; asks for confirmation unless -yes')
    parser.add_argument('-yes', action='store_true',
                        help='With -remove_client: do not ask for confirmation')
    parser.add_argument('-details', action='store_true',
                        help='With -firmware: include full system info (part/serial, githash). '
                             'With -network: include MAC, IPv4 settings and Wi-Fi SSID. '
                             'With -clients: include descriptions and public keys')
    parser.add_argument('--auth-mode', default=AuthMode.BASIC.value,
                        choices=[m.value for m in AuthMode],
                        help='Authentication mode: basic (default, Gateway Wi-Fi only via '
                             '192.168.91.1) or bearer (installer login, also works over '
                             'the wired LAN IP; verified on solar-only/inverter gateways — '
                             'not Powerwall 2 or Powerwall 3; see jasonacox/pypowerwall-server#105)')
    parser.add_argument('--debug', action='store_true', help='Enable Debug Output')
    return parser


def _json_bytes_safe(obj):
    """json.dumps `default=` that renders otherwise non-serializable values instead
    of crashing the CLI: bytes (e.g. FirmwareVersion.githash) as hex, protobuf
    messages as a dict, anything else as str."""
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    if hasattr(obj, "DESCRIPTOR"):  # a protobuf message
        try:
            from google.protobuf.json_format import MessageToDict
            return MessageToDict(obj)
        except Exception:
            pass
    return str(obj)


def _render_firmware(info, details=False):
    """Format a get_firmware_version() result for display. Pure (no I/O) so it is
    unit-testable. `info` is the version string (details=False), the system-info
    dict (details=True), or None when the gateway returned nothing."""
    import json
    if info is None:
        return "unavailable (no response from gateway)"
    if details:
        return json.dumps(info, indent=2, default=_json_bytes_safe)
    return str(info)


def _render_network(status):
    """Format a get_network_status() result for display. Pure (no I/O) so it is
    unit-testable. `status` is the per-interface dict, or None when the gateway
    returned nothing (no answer, or firmware without the request)."""
    import json
    if status is None:
        return 'unavailable (no network status from gateway)'
    return json.dumps(status, indent=2, default=_json_bytes_safe)


def _render_clients(payload):
    """Format a get_authorized_clients() result for display. Pure (no I/O) so it
    is unit-testable."""
    import json
    if payload is None:
        return 'unavailable (no authorized clients from gateway)'
    return json.dumps(payload, indent=2, sort_keys=True)


def _read_key_argument(value):
    """The bytes of a key file when ``value`` names one, else ``value`` itself
    (a fingerprint prefix or base64 key)."""
    import os
    if value and os.path.isfile(value):
        with open(value, 'rb') as f:
            return f.read()
    return value


def run_tedapi_test(argv=None, debug=False):
    # Imports
    from pypowerwall.tedapi import TEDAPI, GW_IP
    from pypowerwall import __version__
    from pypowerwall.helpers import lookup
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

    if (args.add_client or args.remove_client) and not args.v1r:
        parser.error('-add_client and -remove_client require -v1r (signed commands)')
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
                     wifi_host=args.wifi_host,
                     tedapi_api_version=args.tedapi_api_version)
    else:
        ted = TEDAPI(gw_pwd, host=host, tedapi_api_version=args.tedapi_api_version,
                     auth_mode=args.auth_mode)
    if ted.din is None:
        print("\nERROR: Unable to connect to Powerwall Gateway. Check your password and try again")
        sys.exit(1)

    # Focused firmware entrypoint: fetch + print the firmware/system info and exit
    # (no config/status fetch, no files written). Handy for validating the version
    # path -- e.g. diff -tedapi_api_version V2024_06 vs V2026_06 for the same gateway.
    if args.firmware:
        print()
        info = ted.get_firmware_version(force=True, details=args.details)
        if args.details:
            print(" - Firmware System Info:")
            print(_render_firmware(info, details=True))
        else:
            print(f" - Firmware Version: {_render_firmware(info)}")
        print()
        return

    # Focused network entrypoint: fetch + print the gateway network status and
    # exit (read-only; no config/status fetch, no files written).
    if args.network:
        print()
        print(' - Network Status:')
        print(_render_network(ted.get_network_status(force=True, details=args.details)))
        print()
        return
    # Focused authorized-client entrypoints: list / add / remove, then exit.
    if args.clients:
        print()
        print(" - Authorized Clients:")
        print(_render_clients(ted.get_authorized_clients(force=True, details=args.details)))
        print()
        return
    if args.add_client:
        print()
        try:
            key = _read_key_argument(args.add_client)
        except OSError as e:
            print(f"ERROR: unable to read {args.add_client}: {e}")
            sys.exit(1)
        try:
            client = ted.add_authorized_client(key, description=args.description)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        if client is None:
            print("ERROR: the gateway did not add the key (see the log above)")
            sys.exit(1)
        print(" - Added Authorized Client:")
        print(_render_clients(client))
        print()
        return
    if args.remove_client:
        print()
        try:
            key = _read_key_argument(args.remove_client)
        except OSError as e:
            print(f"ERROR: unable to read {args.remove_client}: {e}")
            sys.exit(1)
        if not args.yes:
            answer = input(f"Remove authorized client {args.remove_client}? "
                           "It will no longer be able to send signed commands. [y/N] ")
            if answer.strip().lower() not in ('y', 'yes'):
                print("Cancelled")
                return
        try:
            removed = ted.remove_authorized_client(key)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        if not removed:
            print("ERROR: the key was not removed (see the log above)")
            sys.exit(1)
        print(" - Authorized client removed")
        print()
        return

    config = ted.get_config() or {}
    status = ted.get_status() or {}
    print()

    # Print Configuration
    print(" - Configuration:")
    site_info = config.get('site_info') or {}
    site_name = site_info.get('site_name', 'Unknown')
    print(f"   - Site Name: {site_name}")
    battery_commission_date = site_info.get('battery_commission_date', 'Unknown')
    print(f"   - Battery Commission Date: {battery_commission_date}")
    vin = config.get('vin', 'Unknown')
    print(f"   - VIN: {vin}")
    number_of_powerwalls = len(config.get('battery_blocks') or [])
    print(f"   - Number of Powerwalls: {number_of_powerwalls}")
    print(f"   - Firmware Version: {_render_firmware(ted.get_firmware_version(force=True))}")
    print()

    # Save Configuration and Status to JSON files first, so the raw payloads are
    # captured for debugging even if the structure below is unexpected.
    with open('status.json', 'w') as f:
        json.dump(status, f)
    with open('config.json', 'w') as f:
        json.dump(config, f)

    # Print power data (null-safe: a gateway in a faulted or uncommissioned
    # state can return explicit nulls for 'control', 'systemStatus', meter
    # entries, or config fields - chained .get(key, default) only guards
    # missing keys, not null values)
    print(" - Power Data:")
    control = status.get('control')
    if not isinstance(control, dict):
        is_running = lookup(status, ['system', 'sitemanagerStatus', 'isRunning'])
        print(f"   - WARNING: Gateway status payload has no 'control' data "
              f"(system.sitemanagerStatus.isRunning: {is_running}).")
        if is_running is False:
            print("     The gateway is connected and communicating, but its site")
            print("     manager is not running, so it is not producing live power")
            print("     data. Check the Tesla app for alerts or faults. This is a")
            print("     gateway condition, not a pypowerwall problem.")
        else:
            print("     Unexpected payload. The raw payload was saved to status.json -")
            print("     please share it in a GitHub issue (redact any site identifiers).")
        control = {}
    nominalEnergyRemainingWh = lookup(control, ['systemStatus', 'nominalEnergyRemainingWh']) or 0
    nominalFullPackEnergyWh = lookup(control, ['systemStatus', 'nominalFullPackEnergyWh']) or 0
    if nominalFullPackEnergyWh == 0:
        print(f"   - Battery Full Charge Unknown ({nominalEnergyRemainingWh}Wh of {nominalFullPackEnergyWh}Wh)")
    else:
        soe = round(nominalEnergyRemainingWh / nominalFullPackEnergyWh * 100, 2)
        print(f"   - Battery Charge: {soe}% ({nominalEnergyRemainingWh}Wh of {nominalFullPackEnergyWh}Wh)")
    meterAggregates = control.get('meterAggregates') or []
    for meter in meterAggregates:
        if not isinstance(meter, dict):
            continue
        location = meter.get('location')
        location = location.title() if isinstance(location, str) else 'Unknown'
        realPowerW = meter.get('realPowerW')
        realPowerW = int(realPowerW) if isinstance(realPowerW, (int, float)) else 0
        print(f"   - {location}: {realPowerW}W")
    print()
    print(" - Configuration and Status saved to config.json and status.json")
    print()

if __name__ == "__main__":
    run_tedapi_test()

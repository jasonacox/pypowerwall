# pyPowerWall Module - Scan Function
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Scan Function
    This tool will scan your local network looking for a Tesla Energy Gateway
    and/or Powerwall. It uses your local IP address as a default.

"""
import ipaddress
import socket
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from queue import Queue
from typing import Dict, Final, List, Optional

import requests

import pypowerwall

UNKNOWN: Final[str] = "Unknown"
POWERWALL: Final[str] = "Powerwall"

class ScanContext:
    """Handles terminal formatting, interactive output, and other broad spectrum settings."""
    _BOLD: Final[str] = "bold"
    _SUBBOLD: Final[str] = "subbold"
    _NORMAL: Final[str] = "normal"
    _DIM: Final[str] = "dim"
    _ALERT: Final[str] = "alert"
    _ALERTDIM: Final[str] = "alertdim"

    def __init__(self, timeout: float, color: bool = True, interactive: bool = False):
        self.timeout = timeout
        self.interactive = interactive
        self.color = False if not interactive else color
        self.colors = {
            self._BOLD: "\033[0m\033[97m\033[1m" if self.color else "",
            self._SUBBOLD: "\033[0m\033[32m" if self.color else "",
            self._NORMAL: "\033[97m\033[0m" if self.color else "",
            self._DIM: "\033[0m\033[97m\033[2m" if self.color else "",
            self._ALERT: "\033[0m\033[91m\033[1m" if self.color else "",
            self._ALERTDIM: "\033[0m\033[91m\033[2m" if self.color else "",
        }

    def bold(self):
        return self.colors[self._BOLD]

    def subbold(self):
        return self.colors[self._SUBBOLD]

    def normal(self):
        return self.colors[self._NORMAL]

    def dim(self):
        return self.colors[self._DIM]

    def alert(self):
        return self.colors[self._ALERT]

    def alertdim(self):
        return self.colors[self._ALERTDIM]


def normalize_caseless(text: str) -> str:
    return unicodedata.normalize("NFKD", text.casefold())

def caseless_equal(left: str, right: str) -> bool:
    return normalize_caseless(left) == normalize_caseless(right)


def get_my_ip() -> str:
    """Get the local IP address of the machine.

    Returns:
        str: IP address of the localhost.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]


def check_connection(addr: str, context: ScanContext, port: int = 443) -> bool:
    """Checks for simple connection status to a provided address.

    Args:
        addr (str): The address to attempt connection to.
        context (ScanContext): Context controlling output interactivity, color, and timeout behaviors.
        port (int, optional): The port to connect to. Defaults to 443.

    Returns:
        bool: True if connection is successful, False otherwise.
    """

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
            conn.settimeout(context.timeout)
            return conn.connect_ex((addr, port)) == 0
    except Exception as e:
        if context.interactive:
            print(f"An error occurred during connection attempt: {e}")
        return False


# Example Tesla Inverter response to https://{addr}/api/status
# {
#      "din": "1538000-45-C--XXXXXXXXXXXXXX",
#      "start_time": "2024-11-29 17:01:30 +0800",
#      "up_time_seconds": "23h48m59.321804629s",
#      "is_new": false,
#      "version": "24.36.2 46990655",
#      "git_hash": "469906551a97e7b41a60844c37be7ede868d5d56",
#      "commission_count": 0,
#      "device_type": "teg",
#      "teg_type": "pvinverter",
#      "sync_type": "v2.1",
#      "cellular_disabled": false,
#      "can_reboot": false
# }


def scan_ip(addr: str, context: ScanContext, result_queue: Queue) -> None:
    """Thread Worker: Scan IP Address for presence of a Tesla Energy Gateway.

    Args:
        addr (str): IP address to scan
        context (ScanContext): Context controlling output interactivity, color, and timeout behaviors.
        result_queue (Queue): Thread safe queue to store results of the asynchronous scan.
    """

    host = f"{context.dim()}\r\t  Host: {context.subbold()}{addr} ...{context.normal()}"
    if context.interactive:
        print(host, end='')

    if not check_connection(addr, context):
        return

    # noinspection PyBroadException
    try:
        # Check to see if it is a Powerwall
        # Note: timeout=5 is intentionally higher than context.timeout (used only for
        # the TCP probe) to allow enough time for a full HTTP response.
        response = requests.get(f'https://{addr}/api/status', verify=False, timeout=5)
        if response.status_code != HTTPStatus.NOT_FOUND:
            data = response.json()
            din: str = data.get('din', UNKNOWN)
            version: str = data.get('version', UNKNOWN)
            if din == UNKNOWN and version == UNKNOWN:
                return

            up_time: str = data.get('up_time_seconds', UNKNOWN)
            teg_type: str = data.get('teg_type', POWERWALL)
            if caseless_equal(teg_type, UNKNOWN):
                teg_type = POWERWALL

            if context.interactive:
                print(f"{host} OPEN{context.dim()} - {context.subbold()}Found {teg_type} {din}{context.subbold()}\n\t\t\t\t\t [Firmware {version}]{context.normal()}")
            result_queue.put({
                'ip': addr,
                'din': din,
                'firmware': version,
                'up_time': up_time
            })
            return

        # Check if it is a Powerwall 3
        response_pw3 = requests.get(f'https://{addr}/tedapi/din', verify=False, timeout=5)
        # Expected response from PW3
        # {"code":403,"error":"Unable to GET to resource","message":"User does not have adequate access rights"}
        if "User does not have adequate access rights" in response_pw3.text:
            # Found PW3
            if context.interactive:
                print(f"{host} OPEN{context.dim()} - {context.subbold()}Found Powerwall 3 [Cloud and TEDAPI Mode only]{context.normal()}")
            result_queue.put({
                'ip': addr,
                'din': 'Powerwall-3',
                'firmware': 'Cloud and TEDAPI Mode support only - See https://tinyurl.com/pw3support'
            })
    except Exception:
        pass


def scan(
    cidr: Optional[str] = None,
    ip: Optional[str] = None,
    max_threads: int = 30,
    timeout: float = 1.0,
    color: bool = False,
    interactive: bool = False,
    json_output: bool = False,
) -> List[Dict[str, str]]:
    """Scan the local network for Tesla Powerwall Gateways.

    Args:
        cidr (Optional[str], optional): IPv4 CIDR network to scan (e.g. "10.0.0.0/16"). If None, autodetects as /24.
        ip (Optional[str], optional): IP address within network to scan. Defaults to /24 if no prefix given.
        max_threads (int, optional): Maximum number of concurrent threads/IP addresses to simultaneously scan. Defaults to 30.
        timeout (float, optional): Timeout in seconds for each host scan. Defaults to 1.0.
        color (bool, optional): If True, use colored output. Defaults to False.
        interactive (bool, optional): Whether messages should be printed and input sought from a user. Defaults to False.
        json_output (bool, optional): If True, suppress all console output (implies non-interactive). Defaults to False.

    Returns:
        List[Dict[str, str]]: A list of discovered Tesla Energy Gateway (Powerwall/Inverter) devices.
    """

    # Support ip parameter as alias for cidr
    if cidr is None and ip is not None:
        cidr = ip

    # json_output suppresses all console output
    if json_output:
        interactive = False

    user_provided = cidr is not None
    context = ScanContext(timeout=timeout, color=color, interactive=interactive)

    # Determine network to scan
    # noinspection PyBroadException
    try:
        if cidr is None:
            cidr = get_my_ip()
        # If no CIDR prefix provided (e.g. bare IP), default to /24.
        if '/' not in cidr:
            cidr = cidr + '/24'
        network = ipaddress.IPv4Network(cidr, strict=False)
    except Exception:
        if context.interactive:
            print(f"{context.alert()}ERROR: Unable to determine your IP address and network automatically.{context.normal()}")
        network = ipaddress.IPv4Network('192.168.1.0/24')

    if context.interactive:
        print(f"{context.bold()}\npyPowerwall Network Scanner{context.dim()} [{pypowerwall.version}]{context.normal()}")
        print(f'{context.dim()}Scan local network for Tesla Powerwall Gateways\n')

    if context.timeout < 0.2 and context.interactive:
        print(f'{context.alert()}\tWARNING: Setting a low timeout ({context.timeout}) may cause misses.\n')

    # Ask user to verify network — skip if they already provided one on the command line
    if context.interactive and not user_provided:
        print(f'{context.dim()}\tYour network appears to be: {context.bold()}{network}{context.normal()}\n')

        # noinspection PyBroadException
        try:
            response = input(f"{context.subbold()}\tEnter Network CIDR [{context.bold()}{network}{context.subbold()}]: {context.normal()}")
        except Exception:
            # Assume user aborted
            print(f"{context.alert()}  Cancel\n\n{context.normal()}")
            sys.exit()

        if response:
            # Default to /24 if no prefix length given
            if '/' not in response:
                response = response + '/24'
            # Verify we have a valid network
            # noinspection PyBroadException
            try:
                network = ipaddress.IPv4Network(response, strict=False)
            except Exception:
                print(f'\n{context.alert()}\tERROR: {response} is not a valid network.{context.normal()}')
                print(f'{context.dim()}\t\t   Proceeding with {network} instead.')

    if context.interactive:
        print(f"\n{context.bold()}\tRunning Scan on {context.subbold()}{network}{context.bold()}...{context.dim()}")

    # Warn if the network is larger than a /24 (254 hosts) — large subnets can
    # exhaust file descriptors and ephemeral ports.
    if network.prefixlen < 24 and context.interactive:
        print(f'{context.alert()}\tWARNING: Scanning a /{network.prefixlen} network ({network.num_addresses - 2} hosts). '
              f'This may take a while and can strain system resources.{context.normal()}')

    # Cap threads to a safe maximum to avoid exhausting OS file descriptors.
    max_safe_threads = 256
    if max_threads > max_safe_threads:
        if context.interactive:
            print(f'{context.dim()}\tNote: Capping threads from {max_threads} to {max_safe_threads} (resource safety limit){context.normal()}')
        max_threads = max_safe_threads

    result_queue = Queue()
    try:
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for addr in network.hosts():
                executor.submit(scan_ip, str(addr), context, result_queue)

        if context.interactive:
            print(f"{context.dim()}\r\t  Done\t\t\t\t\t\t   \n{context.normal()}")
    except KeyboardInterrupt:
        if context.interactive:
            print(f"{context.dim()}\r\t  ** Interrupted by user **\t\t\t\t\t\t\n{context.normal()}")

    # Collect results from the queue
    discovered_devices: List[Dict[str, str]] = []
    while not result_queue.empty():
        device_info = result_queue.get()
        discovered_devices.append(device_info)

    if context.interactive:
        print(f"{context.normal()}Discovered {len(discovered_devices)} Powerwall Gateway(s)")
        for device in discovered_devices:
            print(f"{context.dim()}\t {device['ip']} [{device['din']}] Firmware {device['firmware']}")
        print(f"{context.normal()} ")
    return discovered_devices

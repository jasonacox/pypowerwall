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
import errno
import ipaddress
import socket
import sys
import threading
import time
import unicodedata
from http import HTTPStatus
from ipaddress import IPv4Address
from queue import Queue
from typing import Any, Dict, Final, List, Optional

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
        try:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        except Exception:
            raise

def check_connection(addr: IPv4Address, context: ScanContext, port: int = 443, max_retries: int = 10, retry_delay: float = 0.1) -> bool:
    """Checks for simple connection status to a provided address.

    Args:
        addr (IPv4Address): The address to attempt connection to.
        context (ScanContext): Context controlling output interactivity, color, and timeout behaviors.
        port (int, optional): The port to connect to. Defaults to 443.
        max_retries (int, optional): Maximum number of retry attempts. Defaults to 10.
        retry_delay (float, optional): Delay between connection retries in seconds. Defaults to 0.1. In the future this should be replaced with exponential backoff and jitter.

    Returns:
        bool: True if connection is successful, False otherwise.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.settimeout(context.timeout)
        for _ in range(max_retries):
            try:
                result = conn.connect_ex((str(addr), port))
                if result == 0:
                    return True
                elif result != errno.EAGAIN:
                    return False
            except Exception as e:
                if context.interactive:
                    print(f"An error occurred during connection attempt: {e}")
                return False
            time.sleep(retry_delay)
    return False  # Connection failed after max retries

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

def scan_ip(addr: IPv4Address, context: ScanContext, result_queue: Queue) -> None:
    """Thread Worker: Scan IP Address for presence of a Tesla Energy Gateway.

    Args:
        addr (IPv4Address): IP address to scan
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
        response = requests.get(f'https://{addr}/api/status', verify=False, timeout=5)
        if response.status_code != HTTPStatus.NOT_FOUND:
            data: Final[str] = response.json()
            din: Final[str] = data.get('din', UNKNOWN)
            version: Final[str] = data.get('version', UNKNOWN)
            if din == UNKNOWN and version == UNKNOWN:
                return

            up_time: Final[str] = data.get('up_time_seconds', UNKNOWN)
            type_selector = lambda type: type if not caseless_equal(type, UNKNOWN) else POWERWALL
            teg_type: Final[str] = type_selector(data.get('teg_type', POWERWALL))

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
                print(f"{host} OPEN{context.dim()} - {context.subbold()}Found Powerwall 3 [Cloud and TEDAPI Mode only]{context.normal}")
            result_queue.put({
                'ip': addr,
                'din': 'Powerwall-3',
                'firmware': 'Cloud and TEDAPI Mode support only - See https://tinyurl.com/pw3support'
            })
        elif context.interactive:
            # Not a Powerwall
            print(f"{host} OPEN{context.dim()} - Not a Tesla Energy Gateway")
    except Exception:
        if context.interactive:
            print(f'{host} OPEN{context.dim()} - Not a Tesla Energy Gateway')


def scan(
    ip: Optional[str] = None,
    max_threads: int = 30,
    timeout: float = 1.0,
    color: bool = False,
    interactive: bool = False
) -> List[Dict[str, str]]:
    """Scan the local network for Tesla Powerwall Gateways.

    Args:
        ip (Optional[str], optional): IP address to determine the network to scan. If None, autodetects.
        max_threads (int, optional): Maximum number of concurrent threads/IP addresses to simultaneously scan. Defaults to 30.
        timeout (float, optional): Timeout in seconds for each host scan. Defaults to 1.0.
        color (bool, optional): If True, use colored output. Defaults to False.
        interactive (bool, optional): Whether messages should be printed and input sought from a user. Defaults to False.

    Returns:
        List[Dict[str, str]]: A list of discovered Tesla Energy Gateway (Powerwall/Inverter) devices.
    """

    context = ScanContext(timeout=timeout, color=color, interactive=interactive)

    # Fetch my IP address and assume /24 network
    # noinspection PyBroadException
    try:
        ip = get_my_ip() if ip is None else ip
        network = ipaddress.IPv4Network(ip + '/24', strict=False)
    except Exception:
        if context.interactive:
            print(f"{context.alert()}ERROR: Unable to determine your IP address and network automatically.{context.normal()}")
        network = ipaddress.IPv4Network('192.168.1.0/24')

    if context.interactive:
        print(f"{context.bold()}\npyPowerwall Network Scanner{context.dim()} [{pypowerwall.version}]{context.normal()}")
        print(f'{context.dim()}Scan local network for Tesla Powerwall Gateways\n')

    max_threads = min(200, max_threads)

    if context.timeout < 0.2 and context.interactive:
        print(f'{context.alert()}\tWARNING: Setting a low timeout ({context.timeout}) may cause misses.\n')

    # Ask user to verify network
    if context.interactive:
        print(f'{context.dim()}\tYour network appears to be: {context.bold()}{network}{context.normal()}\n')

        # noinspection PyBroadException
        try:
            response = input(f"{context.subbold()}\tEnter {context.bold()}Network{context.subbold()} or press enter to use {network}{context.normal()}")
        except Exception:
            # Assume user aborted
            print(f"{context.alert()}  Cancel\n\n{context.normal()}")
            sys.exit()

        if response:
            # Verify we have a valid network
            # noinspection PyBroadException
            try:
                network = ipaddress.IPv4Network(response, strict=False)
            except Exception:
                print(f'\n{context.alert()}\tERROR: {response} is not a valid network.{context.normal()}')
                print(f'{context.dim()}\t\t   Proceeding with {network} instead.')

        print(f"\n{context.bold()}\tRunning Scan...{context.dim()}")

    result_queue = Queue()
    threads: List[threading.Thread] = []
    try:
        for addr in network.hosts():
            # Scan each host in a separate thread
            addr_str: Final = str(addr)
            thread = threading.Thread(target=scan_ip, args=(addr_str, context, result_queue))
            thread.start()
            threads.append(thread)

            # Limit the number of concurrent threads
            while len(threads) >= max_threads:
                # Remove completed threads
                threads = [t for t in threads if t.is_alive()]
                time.sleep(0.01)

        for thread in threads:
            # Wait for remaining threads to exit
            thread.join()

        if context.interactive:
            print(f"{context.dim()}\r\t  Done\t\t\t\t\t\t   \n{context.normal()}")
    except KeyboardInterrupt:
        if context.interactive:
            print(f"{context.dim()}\r\t  ** Interrupted by user **\t\t\t\t\t\t\n{context.normal()}")

    # Collect results from the queue
    discovered_devices: List[Dict[Any, Any]] = []
    while not result_queue.empty():
        device_info: Final = result_queue.get()
        discovered_devices.append(device_info)

    if context.interactive:
        print(f"{context.normal()}Discovered {len(discovered_devices)} Powerwall Gateway(s)")
        for device in discovered_devices:
            print(f"{context.dim()}\t {device['ip']} [{device['din']}] Firmware {device['firmware']}")
        print(f"{context.normal()} ")
    return discovered_devices

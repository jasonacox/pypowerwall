# pyPowerWall - Tesla TEDAPI Class
# -*- coding: utf-8 -*-
"""
 Tesla TEDAPI Class

 This module allows you to access the Tesla Powerwall Gateway
 TEDAPI on 192.168.91.1 as used by the Tesla One app.

 Class:
    TEDAPI(gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
              pwconfigexpire: int = 5, host: str = GW_IP) - Initialize TEDAPI

 Parameters:
    gw_pwd - Powerwall Gateway Password
    debug - Enable Debug Output
    pwcacheexpire - Cache Expiration in seconds
    timeout - API Timeout in seconds
    pwconfigexpire - Configuration Cache Expiration in seconds
    host - Powerwall Gateway IP Address (default: 192.168.91.1)

 Functions:
    get_din() - Get the DIN from the Powerwall Gateway
    get_config() - Get the Powerwall Gateway Configuration
    get_status() - Get the Powerwall Gateway Status
    connect() - Connect to the Powerwall Gateway
    backup_time_remaining() - Get the time remaining in hours
    battery_level() - Get the battery level as a percentage
    vitals() - Use tedapi data to create a vitals dictionary
    get_firmware_version() - Get the Powerwall Firmware Version
    get_battery_blocks() - Get list of Powerwall Battery Blocks
    get_components() - Get the Powerwall 3 Device Information
    get_battery_block(din) - Get the Powerwall 3 Battery Block Information
    get_pw3_vitals() - Get the Powerwall 3 Vitals Information
    get_device_controller() - Get the Powerwall Device Controller Status

 Note:
    This module requires access to the Powerwall Gateway. You can add a route to
    using the command: sudo route add -host 192.168.91.1 <Powerwall_IP>
    The Powerwall Gateway password is required to access the TEDAPI.

 Author: Jason A. Cox
 Date: 1 Jun 2024
 For more information see https://github.com/jasonacox/pypowerwall
"""

import inspect
import json
import logging
import math
import sys
import threading
import time
from functools import wraps
from http import HTTPStatus
from typing import List

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from pypowerwall import __version__
from pypowerwall.api_lock import acquire_lock_with_backoff

from pypowerwall.tedapi.ted_api_messages import BatteryComponentsMessage, ConfigMessage, ComponentsMessage, DeviceControllerMessage, FirmwareMessage, GatewayStatusMessage, TEDAPIMessage

from . import tedapi_pb2
from .decorators import uses_cache, uses_connection_required
from .exceptions import PyPowerwallTEDAPIThrottleException
from .vitals_dictionary import VitalsDictionary

urllib3.disable_warnings(InsecureRequestWarning)

# TEDAPI Fixed Gateway IP Address
GW_IP = "192.168.91.1"

# Rate Limit Codes
BUSY_CODES: List[HTTPStatus] = [HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE]

# Setup Logging
log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

# Utility Functions
def lookup(data, keylist):
    """
    Lookup a value in a nested dictionary or return None if not found.
    data - nested dictionary
    keylist - list of keys to traverse
    """
    for key in keylist:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data

def uses_api_lock(func):
    # If the attribute doesn't exist or isn't a valid threading.Lock, overwrite it.
    if not hasattr(func, 'api_lock') or not isinstance(func.api_lock, type(threading.Lock)):
        func.api_lock = threading.Lock()
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Wrap the function with the lock
        self = args[0]
        with acquire_lock_with_backoff(func, self.timeout):
            result = func(*args, **kwargs)
        return result
    return wrapper

# TEDAPI Class
class TEDAPI:
    def __init__(self, gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
                 pwconfigexpire: int = 5, host: str = GW_IP) -> None:
        self.debug = debug
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire status cache
        self.pwconfigexpire = pwconfigexpire  # seconds to expire config cache
        self.pwcache = {}  # holds the cached data for api
        self.timeout = timeout
        self.pwcooldown = 0
        self.gw_ip = host
        self.din = None
        self.pw3 = False # Powerwall 3 Gateway only supports TEDAPI
        if not gw_pwd:
            raise ValueError("Missing gw_pwd")
        if self.debug:
            self.set_debug(True)
        self.gw_pwd = gw_pwd
        # Connect to Powerwall Gateway
        if not self.connect():
            log.error("Failed to connect to Powerwall Gateway")

    # TEDAPI Functions
    def set_debug(self, toggle=True, color=True):
        """Enable verbose logging"""
        if toggle:
            if color:
                logging.basicConfig(format='\x1b[31;1m%(levelname)s:%(message)s\x1b[0m', level=logging.DEBUG)
            else:
                logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.debug("%s [%s]\n" % (__name__, __version__))
        else:
            log.setLevel(logging.NOTSET)

    def __run_request(self, url, method='get', payload=None):
        """
        Run a request to the Powerwall Gateway

        Args:
            url (str): The URL to send the request to.
            method (str): The HTTP method to use ('get' or 'post'). Default is 'get'.
            payload (protobuf.Message): The payload to send with the request (for 'post' method).

        Returns:
            The requests.Response object or the Protobuf payload data (for Message types).
        """
        if self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            raise PyPowerwallTEDAPIThrottleException('Rate limit cooldown period - Pausing API calls')
        try:
            if method.lower() == 'post':
                r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                  headers={'Content-type': 'application/octet-string'},
                                  data=payload.SerializeToString() if payload else None, timeout=self.timeout)
            elif method.lower() == 'get':
                r = requests.get(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False, timeout=self.timeout)
            else:
                log.error(f"Unsupported HTTP method: {method}")
                raise ValueError(f"Unsupported HTTP method: {method}")

            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                raise PyPowerwallTEDAPIThrottleException("Rate limited by Powerwall")
            if r.status_code == HTTPStatus.FORBIDDEN:
                log.error("Access Denied: Check your Gateway Password")
                raise requests.RequestException("Access Denied: Check your Gateway Password", response=r)
            if r.status_code != HTTPStatus.OK:
                log.error(f"Request failed with code: {r.status_code}")
                raise requests.RequestException(f"Request failed with code: {r.status_code}", response=r)

            # If it's a Protobuf payload, we can just hydrate it and return it for convenience
            if isinstance(payload, TEDAPIMessage):
                data = payload.ParseFromString(r.content)
                return data

            return r

        # Log request exceptions but bubble them anyway
        except requests.RequestException as e:
            log.error(f"Request failed: {e}")
            raise e

    @uses_cache('din')
    def get_din(self, force=False):
        # pylint: disable=unused-argument
        """
        Get the DIN from the Powerwall Gateway
        """
        log.debug("Fetching DIN from Powerwall...")
        url = f'https://{self.gw_ip}/tedapi/din'
        try:
            r = self.__run_request(url, 'get')

            data = r.text if r and hasattr(r, 'text') else None
            if data:
                log.debug(f"Connected: Powerwall Gateway DIN: {data}")
                return data
            else:
                log.error("No response text found in the request.")
                return None
        except Exception as e:
            log.error(f"Error fetching DIN: {e}")
            return None

    @uses_connection_required
    @uses_cache('config')
    @uses_api_lock
    def get_config(self, force=False):
        # pylint: disable=unused-argument
        """
        Get the Powerwall Gateway Configuration

        Payload:
        {
            "auto_meter_update": true,
            "battery_blocks": [],
            "bridge_inverter": {},
            "client_protocols": {},
            "credentials": [],
            "customer": {},
            "default_real_mode": "self_consumption",
            "dio": {},
            "enable_inverter_meter_readings": true,
            "freq_shift_load_shed": {},
            "freq_support_parameters": {},
            "industrial_networks": {},
            "installer": {},
            "island_config": {},
            "island_contactor_controller": {},
            "logging": {},
            "meters": [],
            "site_info": {},
            "solar": {},
            "solars": [],
            "strategy": {},
            "test_timers": {},
            "vin": "1232100-00-E--TG11234567890"
        }
        """
        # Fetch Configuration from Powerwall
        log.debug("Get Configuration from Powerwall")
        pb = ConfigMessage(self.din)
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            data = self.__run_request(url, method='post', payload=pb)
            log.debug(f"Configuration: {data}")
            return data
        except Exception as e:
            log.error(f"Error fetching config: {e}")
            return None

    @uses_connection_required
    @uses_cache('status')
    @uses_api_lock
    def get_status(self, force=False):
        # pylint: disable=unused-argument
        """
        Get the Powerwall Gateway Status

        Payload:
        {
            "control": {
                "alerts": {},
                "batteryBlocks": [],
                "islanding": {},
                "meterAggregates": [],
                "pvInverters": [],
                "siteShutdown": {},
                "systemStatus": {}
                },
            "esCan": {
                "bus": {
                    "ISLANDER": {},
                    "MSA": {},
                    "PINV": [],
                    "POD": [],
                    "PVAC": [],
                    "PVS": [],
                    "SYNC": {},
                    "THC": []
                    },
                "enumeration": null,
                "firmwareUpdate": {},
                "inverterSelfTests": null,
                "phaseDetection": null
                },
            "neurio": {
                "isDetectingWiredMeters": false,
                "pairings": [],
                "readings": []
                },
            "pw3Can": {},
            "system": {}
        }
        """
        # Fetch Current Status from Powerwall
        log.debug("Get Status from Powerwall")
        # Build Protobuf to fetch status
        pb = GatewayStatusMessage(self.din)
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            data = self.__run_request(url, method='post', payload=pb)
            return data

        except Exception as e:
            log.error(f"Error fetching status: {e}")
            return None


    @uses_connection_required
    #@uses_cache('device_controller')
    @uses_api_lock
    def get_device_controller(self, force=False):
        # pylint: disable=unused-argument
        """
        Get the Powerwall Device Controller Status

        Similar to get_status but with additional data:
        {
            "components": {}, // Additional data
            "control": {},
            "esCan": {},
            "ieee20305": {}, // Additional data
            "neurio": {},
            "pw3Can": {},
            "system": {},
            "teslaRemoteMeter": {} // Additional data
        }

        TODO: Refactor to combine tedapi queries
        """
        # Fetch Current Status from Powerwall
        log.debug("Get controller data from Powerwall")
        # Build Protobuf to fetch controller data
        pb = DeviceControllerMessage(self.din)
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            data = self.__run_request(url, method='post', payload=pb)
            return data

        except Exception as e:
            log.error(f"Error fetching device controller status: {e}")
            return None

    @uses_connection_required
    def get_firmware_version(self, force=False, details=False):
        """
        Get the Powerwall Firmware Version

        Args:
            force (bool): Force a refresh of the firmware version
            details (bool): Return additional system information including
                            gateway part number, serial number, and wireless devices
        """
        try:
            data = self.__get_firmware_data(force)
            log.debug(f"Firmware Version: {data}")
            if details:
                return data
            else:
                return data["system"]["version"]["text"]
        except Exception as e:
            log.error(f"Error fetching firmware version: {e}")
            return None

    @uses_cache('firmware')
    @uses_api_lock
    def __get_firmware_data(self, force=False):
        # pylint: disable=unused-argument
        """
        Internal function to load the firmware with details so the cache includes everything
        """
        log.debug("Get Firmware Version from Powerwall")
        pb = FirmwareMessage(self.din)
        url = f'https://{self.gw_ip}/tedapi/v1'
        data = self.__run_request(url, method='post', payload=pb)
        return data

    @uses_connection_required
    @uses_cache('components')
    @uses_api_lock
    def get_components(self, force=False):
        # pylint: disable=unused-argument
        """
        Get the Powerwall 3 Device Information

        Note: Provides empty response for previous Powerwall versions
        """
        log.debug("Get components from Powerwall")
        pb = ComponentsMessage(self.din)
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            data = self.__run_request(url, method='post', payload=pb)
            return data
        except Exception as e:
            log.error(f"Error fetching device controller status: {e}")
            return None

    @uses_connection_required
    @uses_cache('pw3_vitals')
    @uses_api_lock
    def get_pw3_vitals(self, force=False):
        """
        Get Powerwall 3 Battery Vitals Data

        Returns:
        {
            "PVAC--{part}--{sn}" {
                "PVAC_PvState_A": "PV_Active",
                "PVAC_PVCurrent_A": 0.0,
                ...
                "PVAC_PVMeasuredVoltage_A": 0.0,
                ...
                "PVAC_PVMeasuredPower_A": 0.0,
                ...
                "PVAC_Fout": 60.0,
                "PVAC_Pout": 0.0,
                "PVAC_State": X,
                "PVAC_VL1Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL1Ground']),
                "PVAC_VL2Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL2Ground']),
                "PVAC_Vout": lookup(p, ['PVAC_Status', 'PVAC_Vout']),
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
            }.
            "PVS--{part}--{sn}" {
                "PVS_StringA_Connected": true,
                ...
            },
            "TEPOD--{part}--{sn}" {
                "alerts": [],
                "POD_nom_energy_remaining": 0.0,
                "POD_nom_full_pack_energy": 0.0,
                "POD_nom_energy_to_be_charged": 0.0,
            }
        }
        """
        components = self.get_components(force=force)
        din = self.din
        if not components:
            log.error("Unable to get Powerwall 3 Components")
            return None

        response = {}
        config = self.get_config(force=force)
        battery_blocks = config['battery_blocks']

        # Loop through all the battery blocks (Powerwalls)
        for battery in battery_blocks:
            pw_din = battery['vin'] # 1707000-11-J--TG12xxxxxx3A8Z
            pw_part, pw_serial = pw_din.split('--')
            battery_type = battery['type']
            if "Powerwall3" not in battery_type:
                continue

            data = self.get_battery_block(pw_din)

            # Collect alerts for the top level response
            alerts = []
            components = data['components']
            for component in components:
                if components[component]:
                    for alert in components[component][0]['activeAlerts']:
                        if alert['name'] not in alerts:
                            alerts.append(alert['name'])

            bms_component = data['components']['bms'][0] # TODO: Process all BMS components
            signals = bms_component['signals']
            nom_energy_remaining = 0
            nom_full_pack_energy = 0
            for signal in signals:
                if "BMS_nominalEnergyRemaining" == signal['name']:
                    nom_energy_remaining = int(signal['value'] * 1000) # Convert to Wh
                elif "BMS_nominalFullPackEnergy" == signal['name']:
                    nom_full_pack_energy = int(signal['value'] * 1000) # Convert to Wh
            response[f"TEPOD--{pw_din}"] = {
                "alerts": alerts,
                "POD_nom_energy_remaining": nom_energy_remaining,
                "POD_nom_energy_to_be_charged": nom_full_pack_energy - nom_energy_remaining,
                "POD_nom_full_pack_energy": nom_full_pack_energy,
            }
            # PVAC, PVS and TEPINV
            response[f"PVAC--{pw_din}"] = {}
            response[f"PVS--{pw_din}"] = {}
            response[f"TEPINV--{pw_din}"] = {}
            pch_components = data['components']['pch']
            # pch_components contain:
            #   PCH_PvState_A through F - textValue in [Pv_Active, Pv_Active_Parallel, Pv_Standby]
            #   PCH_PvVoltageA through F - value
            #   PCH_PvCurrentA through F - value
            # Loop through and find all the strings - PW3 has 6 strings A-F
            for n in ["A", "B", "C", "D", "E", "F"]:
                pv_state = "Unknown"
                pv_voltage = 0
                pv_current = 0
                for component in pch_components: # TODO: Probably better way to do this
                    signals = component['signals']
                    for signal in signals:
                        if f'PCH_PvState_{n}' == signal['name']:
                            pv_state = signal['textValue']
                        elif f'PCH_PvVoltage{n}' == signal['name']:
                            pv_voltage = signal['value'] if signal['value'] > 0 else 0
                        elif f'PCH_PvCurrent{n}' == signal['name']:
                            pv_current = signal['value'] if signal['value'] > 0 else 0
                        elif 'PCH_AcFrequency' == signal['name']:
                            response[f"PVAC--{pw_din}"]["PVAC_Fout"] = signal['value']
                            response[f"TEPINV--{pw_din}"]["PINV_Fout"] = signal['value']
                        elif 'PCH_AcVoltageAN' == signal['name']:
                            response[f"PVAC--{pw_din}"]["PVAC_VL1Ground"] = signal['value']
                            response[f"TEPINV--{pw_din}"]["PINV_VSplit1"] = signal['value']
                        elif 'PCH_AcVoltageBN' == signal['name']:
                            response[f"PVAC--{pw_din}"]["PVAC_VL2Ground"] = signal['value']
                            response[f"TEPINV--{pw_din}"]["PINV_VSplit2"] = signal['value']
                        elif 'PCH_AcVoltageAB' == signal['name']:
                            response[f"PVAC--{pw_din}"]["PVAC_Vout"] = signal['value']
                            response[f"TEPINV--{pw_din}"]["PINV_Vout"] = signal['value']
                        elif 'PCH_AcRealPowerAB' == signal['name']:
                            response[f"PVAC--{pw_din}"]["PVAC_Pout"] = signal['value']
                            response[f"TEPINV--{pw_din}"]["PINV_Pout"] = (signal['value'] or 0) / 1000
                        elif 'PCH_AcMode' == signal['name']:
                            response[f"PVAC--{pw_din}"]["PVAC_State"] = signal['textValue']
                            response[f"TEPINV--{pw_din}"]["PINV_State"] = signal['textValue']
                pv_power = pv_voltage * pv_current # Calculate power
                response[f"PVAC--{pw_din}"][f"PVAC_PvState_{n}"] = pv_state
                response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredVoltage_{n}"] = pv_voltage
                response[f"PVAC--{pw_din}"][f"PVAC_PVCurrent_{n}"] = pv_current
                response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredPower_{n}"] = pv_power
                response[f"PVAC--{pw_din}"]["manufacturer"] = "TESLA"
                response[f"PVAC--{pw_din}"]["partNumber"] = pw_part
                response[f"PVAC--{pw_din}"]["serialNumber"] = pw_serial
                response[f"PVS--{pw_din}"][f"PVS_String{n}_Connected"] = ("Pv_Active" in pv_state)
        return response

    def get_battery_blocks(self, force=False):
        """
        Return Powerwall Battery Blocks
        """
        config = self.get_config(force=force)
        battery_blocks = config.get('battery_blocks') or []
        return battery_blocks

    @uses_connection_required
    @uses_cache('battery-[args-din]')
    @uses_api_lock
    def get_battery_block(self, din=None, force=False):
        # pylint: disable=unused-argument
        """
        Get the Powerwall 3 Battery Block Information

        Args:
            din (str): DIN of Powerwall 3 to query
            force (bool): Force a refresh of the battery block

        Note: Provides 404 response for previous Powerwall versions
        """
        # Make sure we have a DIN
        if not din:
            log.error("No DIN specified - Unable to get battery block")
            return None
        log.debug(f"Get Battery Block from Powerwall ({din})")

        pb = BatteryComponentsMessage(self.din, din)
        url = f'https://{self.gw_ip}/tedapi/device/{din}/v1'
        log.debug(f"Fetching components from {din}")

        try:
            data = self.__run_request(url, method='post', payload=pb)
            log.debug(f"Configuration: {data}")
            return data
        except Exception as e:
            log.error(f"Error fetching battery block: {e}")
            return None

    def connect(self):
        """
        Connect to the Powerwall Gateway
        """
        # Test IP Connection to Powerwall Gateway
        log.debug(f"Testing Connection to Powerwall Gateway: {self.gw_ip}")
        url = f'https://{self.gw_ip}'
        self.din = None
        try:
            resp = requests.get(url, verify=False, timeout=5)
            if resp.status_code != HTTPStatus.OK:
                # Connected but appears to be Powerwall 3
                log.debug("Detected Powerwall 3 Gateway")
                self.pw3 = True
            self.din = self.get_din()
        except Exception as e:
            log.error(f"Unable to connect to Powerwall Gateway {self.gw_ip}")
            log.error("Please verify your your host has a route to the Gateway.")
            log.error(f"Error Details: {e}")
        return self.din

    # Handy Function to access Powerwall Status
    
    def current_power(self, location=None, force=False):
        """
        Get the current power in watts for a location:
            BATTERY, SITE, LOAD, SOLAR, SOLAR_RGM, GENERATOR, CONDUCTOR
        """
        status = self.get_status(force=force)
        power = lookup(status, ['control', 'meterAggregates'])
        if not isinstance(power, list):
            return None
        if location:
            for p in power:
                if p.get('location') == location.upper():
                    return p.get('realPowerW')
        else:
            # Build a dictionary of all locations
            power = {}
            for p in power:
                power[p.get('location')] = p.get('realPowerW')
        return power


    def backup_time_remaining(self, force=False):
        """
        Get the time remaining in hours
        """
        status = self.get_status(force=force)
        nominalEnergyRemainingWh = lookup(status, ['control', 'systemStatus', 'nominalEnergyRemainingWh'])
        load = self.current_power('LOAD', force)
        if not nominalEnergyRemainingWh or not load:
            return None
        time_remaining = nominalEnergyRemainingWh / load
        return time_remaining


    def battery_level(self, force=False):
        """
        Get the battery level as a percentage
        """
        status = self.get_status(force=force)
        nominalEnergyRemainingWh = lookup(status, ['control', 'systemStatus', 'nominalEnergyRemainingWh'])
        nominalFullPackEnergyWh = lookup(status, ['control', 'systemStatus', 'nominalFullPackEnergyWh'])
        if not nominalEnergyRemainingWh or not nominalFullPackEnergyWh:
            return None
        battery_level = nominalEnergyRemainingWh / nominalFullPackEnergyWh * 100
        return battery_level


    # Vitals API Mapping Function
    def vitals(self, force=False):
        """
        Use tedapi data to create a vitals API dictionary
        """
        # status = self.get_status(force)
        config = self.get_config(force=force)
        status = self.get_device_controller(force=force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None

        # Create PVAC, PVS, and TESLA blocks - Assume they are aligned
        num = len(lookup(status, ['esCan', 'bus', 'PVAC']) or {})
        if num != len(lookup(status, ['esCan', 'bus', 'PVS']) or {}):
            log.debug("PVAC and PVS device count mismatch in TEDAPI")

        # Create Vitals Dictionary
        vitals_dictionary = VitalsDictionary(config, status, self.gw_ip)
        vitals = vitals_dictionary.get_vitals()

        # Merge in the Powerwall 3 data if available
        if self.pw3:
            pw3_data = self.get_pw3_vitals(force) or {}
            vitals.update(pw3_data)

        return vitals


    def get_blocks(self, force=False):
        """
        Get the list of battery blocks from the Powerwall Gateway
        """
        status = self.get_status(force=force)
        config = self.get_config(force=force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None
        block = {}
        # Loop through each THC device serial number
        for i, p in enumerate(lookup(status, ['esCan', 'bus', 'THC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # THC block
            name = f"{packagePartNumber}--{packageSerialNumber}"
            block[name] = {
                "Type": "",
                "PackagePartNumber": packagePartNumber,
                "PackageSerialNumber": packageSerialNumber,
                "disabled_reasons": [],
                "pinv_state": None,
                "pinv_grid_state": None,
                "nominal_energy_remaining": None,
                "nominal_full_pack_energy": None,
                "p_out": None,
                "q_out": None,
                "v_out": None,
                "f_out": None,
                "i_out": None,
                "energy_charged": None,
                "energy_discharged": None,
                "off_grid": None,
                "vf_mode": None,
                "wobble_detected": None,
                "charge_power_clamped": None,
                "backup_ready": None,
                "OpSeqState": None,
                "version": None
            }
            # POD block
            pod = lookup(status, ['esCan', 'bus', 'POD'])[i]
            energy_remaining = lookup(pod, ['POD_EnergyStatus', 'POD_nom_energy_remaining'])
            full_pack_energy = lookup(pod, ['POD_EnergyStatus', 'POD_nom_full_pack_energy'])
            block[name].update({
                "nominal_energy_remaining": energy_remaining,
                "nominal_full_pack_energy": full_pack_energy,
            })
            # INV block
            pinv = lookup(status, ['esCan', 'bus', 'PINV'])[i]
            block[name].update({
                "f_out": lookup(pinv, ['PINV_Status', 'PINV_Fout']),
                "pinv_state": lookup(p, ['PINV_Status', 'PINV_State']),
                "pinv_grid_state": lookup(p, ['PINV_Status', 'PINV_GridState']),
                "p_out": lookup(pinv, ['PINV_Status', 'PINV_Pout']),
                "v_out": lookup(pinv, ['PINV_Status', 'PINV_Vout']),
            })
        return block

    # End of TEDAPI Class

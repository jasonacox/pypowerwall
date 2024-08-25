# pyPowerWall - Tesla FleetAPI Class
# -*- coding: utf-8 -*-
"""
 Tesla FleetAPI Class
 
 This module allows you to access the Tesla FleetAPI to manage
 your Powerwall. It has a CLI that can be run in setup mode to
 walk you through the steps to get access to the Tesla FleetAPI. 

 Class:
    FleetAPI - Tesla FleetAPI Class

 Functions:
    poll(api, action, data) - poll FleetAPI
    getsites() - get sites
    site_name() - get site name
    ... Get 
    get_live_status() - get the current power information for the site
    get_site_info() - get site info
    get_battery_reserve() - get battery reserve level
    get_operating_mode() - get operating mode
    get_history() - get energy history
    get_calendar_history() - get calendar history
    get_grid_charging() - get allow grid charging mode
    get_grid_export() - get grid export mode
    solar_power() - get solar power
    grid_power() - get grid power
    battery_power() - get battery power
    load_power() - get load power
    battery_level() - get battery level
    energy_left() - get energy left
    total_pack_energy() - get total pack energy
    grid_status() - get grid status
    island_status() - get island status
    firmware_version() - get firmware version
    ... Set
    set_battery_reserve(reserve) - set battery reserve level (percent)
    set_operating_mode(mode) - set operating mode (self_consumption or autonomous)
    set_grid_charging(mode) - set grid charging mode (on or off)
    set_grid_export(mode) - set grid export mode (battery_ok, pv_only, or never)

 Author: Jason A. Cox
 Date: 18 Feb 2024
 For more information see https://github.com/jasonacox/pypowerwall

 Requirements

 * Register your application https://developer.tesla.com/
 * Before running this script, you must first run create_pem_key.py
   to create a PEM key and register it with Tesla. Put the public
   key in {site}/.well-known/appspecific/com.tesla.3p.public-key.pem
 * Python: pip install requests

 Tesla FleetAPI Reference: https://developer.tesla.com/docs/fleet-api
"""

# FleetAPI Class

import os
import json
import logging
import sys
import time
import urllib.parse
import requests

# Defaults
CONFIGFILE = ".pypowerwall.fleetapi"
SCOPE = "openid offline_access energy_device_data energy_cmds"
SETUP_TIMEOUT = 15   # Time in seconds to wait for setup related API response
REFRESH_TIMEOUT = 60 # Time in seconds to wait for refresh token response
API_TIMEOUT = 10     # Time in seconds to wait for FleetAPI response

fleet_api_urls = {
    "North America, Asia-Pacific": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "Europe, Middle East, Africa": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "China": "https://fleet-api.prd.cn.vn.cloud.tesla.cn"
}

# Set up logging
log = logging.getLogger(__name__)

# pylint: disable=too-many-public-methods
class FleetAPI:
    def __init__(self, configfile=CONFIGFILE, debug=False, site_id=None,
                 pwcacheexpire: int = 5, timeout: int = API_TIMEOUT):
        self.CLIENT_ID = ""
        self.CLIENT_SECRET = ""
        self.DOMAIN = ""
        self.REDIRECT_URI = ""
        self.AUDIENCE = ""
        self.partner_token = ""
        self.partner_account = {}
        self.access_token = ""
        self.refresh_token = ""
        self.site_id = ""
        self.debug = debug
        self.configfile = configfile
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire cache
        self.pwcache = {}  # holds the cached data for api
        self.refreshing = False
        self.timeout = timeout

        if debug:
            log.setLevel(logging.DEBUG)
        if configfile:
            self.configfile = configfile
        self.load_config()
        if site_id:
            self.site_id = site_id
        if not self.site_id:
            log.debug("No site_id set or returned by FleetAPI - Run Setup.")

    # Function to return a random string of characters and numbers
    def random_string(self, length):
        import random
        import string
        return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

    # Return key value from data or None
    def keyval(self, data, key):
        return data.get(key) if data and key else None

    # Load Configuration
    def load_config(self):
        if os.path.isfile(self.configfile):
            with open(self.configfile, 'r') as f:
                config = json.loads(f.read())
            # Set the global variables
            self.CLIENT_ID = config.get('CLIENT_ID')
            self.CLIENT_SECRET = config.get('CLIENT_SECRET')
            self.DOMAIN = config.get('DOMAIN')
            self.REDIRECT_URI = config.get('REDIRECT_URI')
            self.AUDIENCE = config.get('AUDIENCE')
            self.partner_token = config.get('partner_token')
            self.partner_account = config.get('partner_account')
            self.access_token = config.get('access_token')
            self.refresh_token = config.get('refresh_token')
            self.site_id = config.get('site_id')
            # Check for valid site_id
            if not self.site_id:
                sites = self.getsites()
                self.site_id = sites[0]['energy_site_id']
            log.debug(f"Configuration loaded: {self.configfile}")
            return config
        else:
            log.debug(f"Configuration file not found: {self.configfile}")
            return False

    # Save Configuration
    def save_config(self):
        # Copy the global variables to the config dictionary
        config = {
            "CLIENT_ID": self.CLIENT_ID,
            "CLIENT_SECRET": self.CLIENT_SECRET,
            "DOMAIN": self.DOMAIN,
            "REDIRECT_URI": self.REDIRECT_URI,
            "AUDIENCE": self.AUDIENCE,
            "partner_token": self.partner_token,
            "partner_account": self.partner_account,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "site_id": self.site_id
        }
        # Save the config dictionary to the file
        with open(self.configfile, 'w') as f:
            f.write(json.dumps(config, indent=4))

    # Refresh Token
    def new_token(self):
        #  Lock to prevent multiple refreshes
        if self.refreshing:
            return
        self.refreshing = True
        log.info("Token expired, refreshing token")
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.CLIENT_ID,
            'refresh_token': self.refresh_token
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                        data=data, headers=headers, timeout=REFRESH_TIMEOUT)
        # Extract access_token and refresh_token from this response
        access = response.json().get('access_token')
        refresh = response.json().get('refresh_token')
        # If access or refresh token is None return
        if not access or not refresh or response.status_code > 201:
            log.error(f"Unable to refresh token. Response code: {response.status_code}")
            self.refreshing = False
            return
        self.access_token = access
        self.refresh_token = refresh
        log.info("Token refreshed - saving.")
        log.debug(f"  Response Code: {response.status_code}")
        log.debug(f"  Access Token: {self.access_token}")
        log.debug(f"  Refresh Token: {self.refresh_token}")
        # Update config
        self.save_config()
        self.refreshing = False

    # Poll FleetAPI
    def poll(self, api="api/1/products", action="GET", data=None, recursive=False, force=False):
        url = f"{self.AUDIENCE}/{api}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.access_token
        }
        if action == "POST":
            # Post to FleetAPI with json data payload
            log.debug(f"POST: {url} {json.dumps(data)}")
            # Check for timeout exception
            try:
                response = requests.post(url, headers=headers,
                                         data=json.dumps(data), timeout=self.timeout)
            except requests.exceptions.Timeout:
                log.error(f"Timeout error posting to {url}")
                return None
        else:
            # Check if we have a cached response
            if not force and api in self.pwcachetime:
                if time.time() - self.pwcachetime[api] < self.pwcacheexpire:
                    log.debug(f"Using cached data for {api}")
                    return self.pwcache[api]
            log.debug(f"GET: {url}")
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
            except requests.exceptions.Timeout:
                log.error(f"Timeout error polling {url}")
                return None
        if response.status_code == 401 and not recursive:
            # Token expired, refresh token and try again
            self.new_token()
            data = self.poll(api, action, data, True)
        elif response.status_code == 401:
            log.error("Token expired, refresh token failed")
            data = None
        elif response.status_code != 200:
            log.error(f"Code {response.status_code}: {response.text}")
            data = None
        else:
            data = response.json()
        if action == "GET":
            # Cache the data
            self.pwcachetime[api] = time.time()
            self.pwcache[api] = data
        return data

    def get_live_status(self, force=False):
        # Get the current power information for the site.
        """
        {
            'response': {
            'solar_power': 0,
            'percentage_charged': 46.6731017783813,
            'backup_capable': True,
            'battery_power': 780,
            'load_power': 780,
            'grid_status': 'Active',
            'grid_services_active': False,
            'grid_power': 0,
            'grid_services_power': 0,
            'generator_power': 0,
            'island_status': 'on_grid',
            'storm_mode_active': False,
            'timestamp': '2024-05-12T00:18:19-07:00',
            'wall_connectors': []
            }
        }
        """
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/live_status", force=force)
        log.debug(f"get_live_status: {payload}")
        return self.keyval(payload, "response")

    def get_site_info(self, force=False):
        # Get site info
        """
        {
            'id': '1234000-00-E--TG12345678904G',
            'site_name': 'TeslaEnergyGateway',
            'backup_reserve_percent': 20,
            'default_real_mode': 'self_consumption',
            'installation_date': '2021-09-25T15: 53: 47-07: 00',
            'user_settings': {
                'go_off_grid_test_banner_enabled': False,
                'storm_mode_enabled': False,
                'powerwall_onboarding_settings_set': True,
                'powerwall_tesla_electric_interested_in': False,
                'vpp_tour_enabled': True,
                'sync_grid_alert_enabled': True,
                'breaker_alert_enabled': False
            },
            'components': {
                'solar': True,
                'solar_type': 'pv_panel',
                'battery': True,
                'grid': True,
                'backup': True,
                'gateway': 'teg',
                'load_meter': True,
                'tou_capable': True,
                'storm_mode_capable': True,
                'flex_energy_request_capable': False,
                'car_charging_data_supported': False,
                'off_grid_vehicle_charging_reserve_supported': True,
                'vehicle_charging_performance_view_enabled': False,
                'vehicle_charging_solar_offset_view_enabled': False,
                'battery_solar_offset_view_enabled': True,
                'solar_value_enabled': True,
                'energy_value_header': 'EnergyValue',
                'energy_value_subheader': 'EstimatedValue',
                'energy_service_self_scheduling_enabled': True,
                'show_grid_import_battery_source_cards': True,
                'set_islanding_mode_enabled': True,
                'wifi_commissioning_enabled': True,
                'backup_time_remaining_enabled': True,
                'battery_type': 'solar_powerwall',
                'configurable': True,
                'grid_services_enabled': False,
                'gateways': [
                    {
                        'device_id': 'xxxxxxxx-xxxxx-xxx-xxxx-xxxxxxxxxxxx',
                        'din': '1232100-00-E--TG12345678904G',
                        'serial_number': 'TG12345678904G',
                        'part_number': '1232100-00-E',
                        'part_type': 10,
                        'part_name': 'TeslaBackupGateway2',
                        'is_active': True,
                        'site_id': 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxxx',
                        'firmware_version': '24.4.00fe780c9',
                        'updated_datetime': '2024-05-11T09: 20: 26.225Z'
                    }
                ],
                'batteries': [
                    {
                        'device_id': 'xxxxxxxx-xxxxx-xxx-xxxx-xxxxxxxxxxxx',
                        'din': '2012170-25-E--TG12345678904G',
                        'serial_number': 'TG12345678904G',
                        'part_number': '2012170-25-E',
                        'part_type': 2,
                        'part_name': 'Powerwall2',
                        'nameplate_max_charge_power': 5400,
                        'nameplate_max_discharge_power': 5400,
                        'nameplate_energy': 13500
                    },
                    {
                        'device_id': 'xxxxxxxx-xxxxx-xxx-xxxx-xxxxxxxxxxxx',
                        'din': '3012170-05-B--TG12345678904G',
                        'serial_number': 'TG12345678904G',
                        'part_number': '3012170-05-B',
                        'part_type': 2,
                        'part_name': 'Powerwall2',
                        'nameplate_max_charge_power': 5400,
                        'nameplate_max_discharge_power': 5400,
                        'nameplate_energy': 13500
                    }
                ],
                'inverters': [
                    {
                        'device_id': 'xxxxxxxx-xxxxx-xxx-xxxx-xxxxxxxxxxxx',
                        'din': '1530000-00-F--CN12345678901J',
                        'part_number': '1538100-00-F',
                        'part_type': 7,
                        'part_name': 'Non-TeslaInverter',
                        'is_active': True,
                        'site_id': 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxxx',
                    }
                ],
                'edit_setting_permission_to_export': True,
                'edit_setting_grid_charging': True,
                'edit_setting_energy_exports': True,
                'system_alerts_enabled': True
            },
            'version': '24.4.00fe780c9',
            'battery_count': 2,
            'tariff_content': {}
        }
        """
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/site_info", force=force)
        log.debug(f"get_site_info: {payload}")
        return self.keyval(payload, "response")

    def get_site_status(self, force=False):
        # Get site status
        """
        {
            'response': {
            'resource_type': 'battery',
            'site_name': 'Tesla Energy Gateway',
            'gateway_id': '1234000-00-E--TG12345678904G',
            'percentage_charged': 46.6731017783813,
            'battery_type': 'ac_powerwall',
            'backup_capable': True,
            'battery_power': 820,
            'go_off_grid_test_banner_enabled': None,
            'storm_mode_enabled': False,
            'powerwall_onboarding_settings_set': True,
            'powerwall_tesla_electric_interested_in': None,
            'vpp_tour_enabled': None,
            'sync_grid_alert_enabled': True,
            'breaker_alert_enabled': True
            }
        }
        """
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/site_status", force=force)
        log.debug(f"get_site_status: {payload}")
        return self.keyval(payload, "response")

    def get_backup_time_remaining(self, force=False):
        # Get backup time remaining
        """
        {'response': {'time_remaining_hours': 9.863332186566478}}
        """
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/backup_time_remaining", force=force)
        log.debug(f"get_backup_time_remaining: {payload}")
        return self.keyval(payload, "response")

    def get_products(self, force=False):
        # Get list of Tesla products assigned to user
        """
        {
            "response": [
            {
            "id": 100021,
            "user_id": 429511308124,
            "vehicle_id": 99999,
            "vin": "5YJ3000000NEXUS01",
            "color": null,
            "access_type": "OWNER",
            "display_name": "Owned",
            "option_codes": "TEST0,COUS",
            "cached_data": null,
            "granular_access": {
                "hide_private": false
            },
            "tokens": [
                "4f993c5b9e2b937b",
                "7a3153b1bbb48a96"
            ],
            "state": null,
            "in_service": false,
            "id_s": "100021",
            "calendar_enabled": false,
            "api_version": null,
            "backseat_token": null,
            "backseat_token_updated_at": null,
            "command_signing": "off"
            },
            {
            "energy_site_id": 429124,
            "resource_type": "battery",
            "site_name": "My Home",
            "id": "STE12345678-12345",
            "gateway_id": "1112345-00-E--TG0123456789",
            "energy_left": 35425,
            "total_pack_energy": 39362,
            "percentage_charged": 90,
            "battery_power": 1000
            }
            ],
            "count": 2
            }
        """
        payload = self.poll("api/1/products", force=force)
        log.debug(f"get_products: {payload}")
        return self.keyval(payload, "response")

    def get_calendar_history(self, kind=None, duration=None, time_zone=None, 
                             start=None, end=None):
        """ Get energy history 
        kind: power, soe, energy, backup, self_consumption, 
              time_of_use_energy, savings
        duration: day, week, month, year, lifetime
        time_zone: America/Los_Angeles
        start: 2024-05-01T00:00:00-07:00 (RFC3339 format)
        end: 2024-05-01T23:59:59-07:00
        """
        return self.get_history(kind, duration, time_zone, 
                                start, end, "calendar_history")
    
    def get_history(self, kind=None, duration=None, time_zone=None, 
                    start=None, end=None, history="history"):
        """ Get energy history 
        kind: power, energy, backup, self_consumption
        duration: day, week, month, year, lifetime
        time_zone: America/Los_Angeles
        start: 2024-05-01T00:00:00-07:00 (RFC3339 format)
        end: 2024-05-01T23:59:59-07:00
        """
        if not self.site_id:
            return None
        arg_kind = f"kind={kind}&" if kind else ""
        arg_duration = f"period={duration}&" if duration else ""
        arg_time_zone = f"time_zone={time_zone}" if time_zone else ""
        arg_start = f"start={start}&" if start else ""
        arg_end = f"end={end}&" if end else ""
        h = self.poll(f"api/1/energy_sites/{self.site_id}/{history}?{arg_kind}{arg_duration}{arg_time_zone}{arg_start}{arg_end}")
        return self.keyval(h, "response")

    def get_grid_charging(self, force=False):
        """ Get allow grid charging allowed mode (True or False) """
        components = self.get_site_info(force=force).get("components") or {}
        state = self.keyval(components, "disallow_charge_from_grid_with_solar_installed") or False
        return not state

    def get_grid_export(self, force=False):
        """ Get grid export mode (battery_ok, pv_only, or never) """
        components = self.get_site_info(force=force).get("components") or {}
        # Check to see if non_export_configured - pre-PTO setting
        if self.keyval(components, "non_export_configured"):
            return "never"
        mode = self.keyval(components, "customer_preferred_export_rule") or "battery_ok"
        return mode

    def set_battery_reserve(self, reserve: int):
        """ Set battery reserve level (percent) """
        if reserve < 0 or reserve > 100:
            log.debug(f"Invalid reserve level: {reserve}")
            return False
        data = {"backup_reserve_percent": reserve}
        # 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{energy_site_id}/backup'
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/backup", "POST", data)
        # Invalidate cache
        self.pwcachetime.pop(f"api/1/energy_sites/{self.site_id}/site_info", None)
        return payload

    def set_operating_mode(self, mode: str):
        """ Set operating mode (self_consumption or autonomous) """
        data = {"default_real_mode": mode}
        if mode not in ["self_consumption", "autonomous"]:
            log.debug(f"Invalid mode: {mode}")
            return False
        # 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{energy_site_id}/operation'
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/operation", "POST", data)
        # Invalidate cache
        self.pwcachetime.pop(f"api/1/energy_sites/{self.site_id}/site_info", None)
        return payload

    def set_grid_charging(self, mode: str):
        """ Set allow grid charging mode (True or False)

        Mode will show up in get_site_info() under components:
         * False
            "disallow_charge_from_grid_with_solar_installed": true,
         * True
            No entry
        """
        if mode in ["on", "yes"] or mode is True:
            mode = False
        elif mode in ["off", "no"] or mode is False:
            mode = True
        else:
            log.debug(f"Invalid mode: {mode}")
            return False
        data = {"disallow_charge_from_grid_with_solar_installed": mode}
        # 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{energy_site_id}/grid_import_export'
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/grid_import_export", "POST", data)
        # Invalidate cache
        self.pwcachetime.pop(f"api/1/energy_sites/{self.site_id}/site_info", None)
        return payload

    def set_grid_export(self, mode: str):
        """ Set grid export mode (battery_ok, pv_only, or never) 
        
        Mode will show up in get_site_info() under components:
         * never
            "non_export_configured": true,
            "customer_preferred_export_rule": "never",
         * pv_only
            "customer_preferred_export_rule": "pv_only"
         * battery_ok
            "customer_preferred_export_rule": "battery_ok"
            or not set
        """
        if mode not in ["battery_ok", "pv_only", "never"]:
            log.debug(f"Invalid mode: {mode} - must be battery_ok, pv_only, or never")
            return False
        data = {"customer_preferred_export_rule": mode}
        # 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{energy_site_id}/grid_import_export'
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/grid_import_export", "POST", data)
        # Invalidate cache
        self.pwcachetime.pop(f"api/1/energy_sites/{self.site_id}/site_info", None)
        return payload

    def get_operating_mode(self, force=False):
        return self.keyval(self.get_site_info(force=force), "default_real_mode")

    def get_battery_reserve(self, force=False):
        return self.keyval(self.get_site_info(force=force), "backup_reserve_percent")

    def getsites(self, force=False):
        payload = self.poll("api/1/products", force=force)
        return self.keyval(payload, "response")

    # Macros for common data
    def solar_power(self):
        return self.keyval(self.get_live_status(), "solar_power")
    def grid_power(self):
        return self.keyval(self.get_live_status(), "grid_power")
    def battery_power(self):
        return self.keyval(self.get_live_status(), "battery_power")
    def load_power(self):
        return self.keyval(self.get_live_status(), "load_power")
    def home_power(self):
        return self.keyval(self.get_live_status(), "load_power")
    def site_name(self):
        return self.keyval(self.get_site_info(), "site_name")
    def battery_level(self, force=False):
        return self.keyval(self.get_live_status(force=force), "percentage_charged")
    def battery_reserve(self):
        return self.get_battery_reserve()
    def operating_mode(self):
        return self.get_operating_mode()
    def energy_left(self, force=False):
        return self.keyval(self.get_site_status(force=force), "energy_left") # FIXME: This is not in the API
    def total_pack_energy(self, force=False):
        return self.keyval(self.get_site_status(force=force), "total_pack_energy")  # FIXME: This is not in the API
    def grid_status(self):
        return self.keyval(self.get_live_status(), "grid_status")
    def island_status(self):
        return self.keyval(self.get_live_status(), "island_status")
    def firmware_version(self):
        return self.keyval(self.get_site_info(), "firmware_version")

    # Setup Environment
    def setup(self):
        # Print Header
        print("\nTesla FleetAPI Setup")
        print("--------------------")
        print()
        print("Step 1 - Register your application at https://developer.tesla.com/")
        print("Step 2 - Run create_pem_key.py to create a PEM key file for your website.")
        print("         Put the public key in {site}/.well-known/appspecific/com.tesla.3p.public-key.pem")
        print("Step 3 - Run this script to generate a partner token, register your partner account,")
        print("         generate a user token, and get the site_id and live data for your Tesla Powerwall.")
        print()

        current_audience = 0
        # Display current configuration if we have it
        config = self.load_config()
        if config:
            print(f"Current Configuration - Loaded: {self.configfile}:")
            for item in config:
                val = config[item]
                if isinstance(val, dict):
                    continue
                if isinstance(val, str) and len(val) > 50:
                    val = val[:50] + "..." + val[-5:]
                print(f"  {item}: {val}")
            # Ask user if they wish to overwrite the configuration
            overwrite = input("\nDo you want to overwrite this configuration? [y/N]: ")
            if not overwrite.lower().startswith("y"):
                print("Exiting...")
                return False
        else:
            print(f"No configuration found - Creating: {self.configfile}")
        # Get the client_id and client_secret from the userl
        print("\nStep 3 - Enter your Tesla FleetAPI credentials...")
        client_id = input(f"  Enter Client ID [{self.CLIENT_ID}]: ")
        if client_id:
            self.CLIENT_ID = client_id
        client_secret = input(f"  Enter Client Secret [{self.CLIENT_SECRET}]: ")
        if client_secret:
            self.CLIENT_SECRET = client_secret
        domain = input(f"  Enter Domain [{self.DOMAIN}]: ")
        if domain:
            self.DOMAIN = domain
        redirect_uri = f"https://{self.DOMAIN}/access"
        if self.REDIRECT_URI:
            redirect_uri = self.REDIRECT_URI
        r = input(f"  Enter Redirect URI [{redirect_uri}]: ")
        if r:
            self.REDIRECT_URI = r
        else:
            self.REDIRECT_URI = redirect_uri
        # Select AUDIENCE from region list
        if not self.AUDIENCE:
            self.AUDIENCE = list(fleet_api_urls.values())[0]
            current_audience = 1
        print("  Select your region:")
        for i, region in enumerate(fleet_api_urls):
            if self.AUDIENCE == fleet_api_urls[region]:
                print(f"   * {i+1}. {region} [{fleet_api_urls[region]}] (current)")
                current_audience = i+1
            else:
                print(f"     {i+1}. {region} [{fleet_api_urls[region]}]")
        region = input(f"  Enter Region [{current_audience}]: ")
        if region:
            self.AUDIENCE = list(fleet_api_urls.values())[int(region)-1]
        print()
        # Save the configuration
        self.save_config()
        print("  Configuration saved")
        print()

        # Generate Partner Token
        print("Step 3A - Generating a partner authentication token...")
        # Verify that the PEM key file exists
        print("  Verifying PEM Key file...")
        verify_url = f"https://{self.DOMAIN}/.well-known/appspecific/com.tesla.3p.public-key.pem"
        response = requests.get(verify_url, timeout=SETUP_TIMEOUT)
        if response.status_code != 200:
            print(f"ERROR: Could not verify PEM key file at {verify_url}")
            print("       Make sure you have created the PEM key file and uploaded it to your website.")
            print()
            print("Run create_pem_key.py to create a PEM key file for your website.")
            return False
        print(f"   * Success: PEM Key file verified at {verify_url}.")
        print()
        # Check to see if already cached
        if self.partner_token:
            print("  Using cached token.")
            log.debug(f"Cached partner token: {self.partner_token}")
        else:
            # If not cached, generate a new token
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.CLIENT_ID,
                'client_secret': self.CLIENT_SECRET,
                'scope': SCOPE,
                'audience': self.AUDIENCE
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            log.debug(f"POST: https://auth.tesla.com/oauth2/v3/token {json.dumps(data)}")
            response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                            data=data, headers=headers, timeout=SETUP_TIMEOUT)
            log.debug(f"Response Code: {response.status_code}")
            partner_token = response.json().get("access_token")
            self.partner_token = partner_token
            print(f"   Got Token: {partner_token[:40]}...\n")
            log.debug(f"Partner Token: {partner_token}")
            # Save the configuration
            self.save_config()
            print("  Configuration saved")
        print()

        # Register Partner Account
        print("Step 3B - Registering your partner account...")
        if self.partner_account:
            print("  Already registered. Skipping...")
        else:
            # If not registered, register
            url = f"{self.AUDIENCE}/api/1/partner_accounts"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + self.partner_token
            }
            data = {
                'domain': self.DOMAIN,
            }
            log.debug(f"POST: {url} {json.dumps(data)}")
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=SETUP_TIMEOUT)
            log.debug(f"  Response Code: {response.status_code}")
            self.partner_account = response.json()
            log.debug(f"Partner Account: {json.dumps(self.partner_account, indent=4)}\n")
            # Save the configuration
            self.save_config()
            print("  Configuration saved")
        print()

        # Generate User Token
        print("Step 3C - Generating a one-time authentication token...")
        if self.access_token and self.refresh_token:
            print("  Replacing cached tokens...")
        scope = urllib.parse.quote(SCOPE)
        state = self.random_string(64)
        url = f"https://auth.tesla.com/oauth2/v3/authorize?&client_id={self.CLIENT_ID}&locale=en-US&prompt=login&redirect_uri={self.REDIRECT_URI}&response_type=code&scope={scope}&state={state}"
        # Prompt user to login to Tesla account and authorize access
        print("  Login to your Tesla account to authorize access.")
        print(f"  Go to this URL: {url}")
        # If on Mac, automatically open the URL in the default browser
        if sys.platform == 'darwin':
            import subprocess
            subprocess.call(['open', url])
        print("\nAfter authorizing access, copy the code from the URL and paste it below.")
        code = input("  Enter the code: ")
        # Check to see if user pasted URL or just the code
        if code.startswith("http"):
            code = code.split("code=")[1].split("&")[0]
        print()
        log.debug(f"Code: {code}")

        # Step 3D - Exchange the authorization code for a token
        #   The access_token will be used as the Bearer token
        #   in the Authorization header when making API requests.
        print("Step 3D - Exchange the authorization code for a token")
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.CLIENT_ID,
            'client_secret': self.CLIENT_SECRET,
            'code': code,
            'audience': self.AUDIENCE,
            'redirect_uri': self.REDIRECT_URI,
            'scope': SCOPE
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        log.debug(f"POST: https://auth.tesla.com/oauth2/v3/token {json.dumps(data)}")
        response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                        data=data, headers=headers, timeout=SETUP_TIMEOUT)
        log.debug(f"Response Code: {response.status_code}")
        # Extract access_token and refresh_token from this response
        access_token = response.json().get('access_token')
        refresh_token = response.json().get('refresh_token')
        print("\n  Tokens generated.")
        print(f"   * Access Token: {access_token}")
        print(f"   * Refresh Token: {refresh_token}\n")
        self.access_token = access_token
        self.refresh_token = refresh_token
        # Save the configuration
        self.save_config()
        print("  Configuration saved")
        print()

        # Select Site ID
        print("Step 4 - Select site_id for your Tesla Powerwall...")
        if self.site_id:
            print(f"  Previous site_id: {self.site_id}")
        # Get list of sites
        sites = self.getsites()
        sel = 0
        # If not set, pick first site
        if not self.site_id:
            self.site_id = sites[0]['energy_site_id']
            sel = 1
        log.debug(sites)
        print("  Sites:")
        for i, site in enumerate(sites):
            if self.site_id == site['energy_site_id']:
                print(f"   * {i+1}. {site['energy_site_id']} - {site['site_name']} (current)")
                sel = i+1
            else:
                print(f"     {i+1}. {site['energy_site_id']} - {site['site_name']}")
        # If only one site, use it
        if len(sites) == 1:
            print(f"  Using site: {sites[0]['energy_site_id']}")
            self.site_id = sites[0]['energy_site_id']
            sel = 1
        else:
            site = input(f"  Enter Site ID [{sel}]: ")
            if site:
                self.site_id = sites[int(site)-1]['energy_site_id']
        print()
        log.debug(f"Site ID: {self.site_id}")
        # Save the configuration
        self.save_config()
        print("  Configuration saved")
        print()

        # Get Site Info
        print("Step 5 - Verifying Access...")
        site_info = self.get_site_info()
        # List all the site info
        print()
        print("  Site Info:")
        for key in site_info:
            print(f"   * {key}: {site_info[key]}")
        print()
        print("  Live Status:")
        live_status = self.get_live_status()
        for key in live_status:
            print(f"   * {key}: {live_status[key]}")
        print()
        print("Setup complete.")
        print("You can now use this script to manage your Tesla Powerwall.")
        print()
        return True

# End of FleetAPI Class

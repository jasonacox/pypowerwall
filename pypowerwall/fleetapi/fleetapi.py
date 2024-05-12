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

 Command Line Interface:

    Usage: fleetapi.py command [arguments] [-h] [--debug] [--config CONFIG] [--site SITE] [--json]

    Commands:
        setup               Setup FleetAPI for your site
        sites               List available sites
        status              Report current power status for your site
        info                Display information about your site
        getmode             Get current operational mode setting
        getreserve          Get current battery reserve level setting
        setmode             Set operatinoal mode (self_consumption or autonomous)
        setreserve          Set battery reserve level (prcentage or 'current')
        
    options:
    -h, --help            Show this help message and exit
    --debug               Enable debug mode
    --config CONFIG       Specify alternate config file (default: .fleetapi.config)
    --site SITE           Specify site_id
    --json                Output in JSON format

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
import requests
import logging
import sys
import urllib.parse

# Defaults
CONFIGFILE = ".fleetapi.config"
SCOPE = "openid offline_access energy_device_data energy_cmds"

fleet_api_urls = {
    "North America, Asia-Pacific": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "Europe, Middle East, Africa": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "China": "https://fleet-api.prd.cn.vn.cloud.tesla.cn"
}

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log(msg):
    logger.debug(msg)

class FleetAPI:
    def __init__(self, configfile=None, debug=False, site_id=None):
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
        self.CONFIGFILE = CONFIGFILE

        if debug:
            logger.setLevel(logging.DEBUG)
        if configfile:
            self.CONFIGFILE = configfile
        self.load_config()
        if site:
            self.site_id = site_id

    # Function to return a random string of characters and numbers
    def random_string(self, length):
        import random
        import string
        return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

    # Return key value from data or None
    def keyval(self, data, key):
        if key in data:
            return data[key]
        return None
    
    # Load Configuration
    def load_config(self):
        if os.path.isfile(self.CONFIGFILE):
            with open(self.CONFIGFILE, 'r') as f:
                config = json.loads(f.read())
            # Set the global variables
            self.CLIENT_ID = config['CLIENT_ID']
            self.CLIENT_SECRET = config['CLIENT_SECRET']
            self.DOMAIN = config['DOMAIN']
            self.REDIRECT_URI = config['REDIRECT_URI']
            self.AUDIENCE = config['AUDIENCE']
            self.partner_token = config['partner_token']
            self.partner_account = config['partner_account']
            self.access_token = config['access_token']
            self.refresh_token = config['refresh_token']
            self.site_id = config['site_id']
            log(f"Configuration loaded: {self.CONFIGFILE}")
            return config
        else:
            log(f"Configuration file not found: {self.CONFIGFILE}")
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
        with open(self.CONFIGFILE, 'w') as f:
            f.write(json.dumps(config, indent=4))

    # Refresh Token
    def new_token(self):
        print("Token expired, refreshing token...")
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.CLIENT_ID,
            'refresh_token': self.refresh_token
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                        data=data, headers=headers)
        # Extract access_token and refresh_token from this response
        self.access_token = response.json()['access_token']
        self.refresh_token = response.json()['refresh_token']
        logger.info(f"  Response Code: {response.status_code}")
        logger.info(f"  Access Token: {self.access_token}")
        logger.info(f"  Refresh Token: {self.refresh_token}")
        # Update config
        self.save_config()
        
    # Poll FleetAPI
    def poll(self, api="api/1/products", action="GET", data=None, recursive=False):
        url = f"{self.AUDIENCE}/{api}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.access_token
        }
        if action == "POST":
            # Post to FleetAPI with json data payload
            log(f"POST: {url} {json.dumps(data)}")
            response = requests.post(url, headers=headers, data=json.dumps(data))
        else:
            log(f"GET: {url}")
            response = requests.get(url, headers=headers)
        if response.status_code == 401 and not recursive:
            # Token expired, refresh token and try again
            self.new_token()
            return self.poll(api, action, data, True)
        elif response.status_code == 401:
            print("Token expired, refresh token failed, exiting...")
            return None
        elif response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None
        return response.json()
    
    def get_live_status(self):
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
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/live_status")    
        log(f"get_live_status: {payload}")
        return self.keyval(payload, "response")

    def get_site_info(self):
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
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/site_info")
        log(f"get_site_info: {payload}")
        return self.keyval(payload, "response")
    
    def get_site_status(self):
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
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/site_status")
        log(f"get_site_status: {payload}")
        return self.keyval(payload, "response")

    def get_backup_time_remaining(self):
        # Get backup time remaining
        """
        {'response': {'time_remaining_hours': 9.863332186566478}}
        """
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/backup_time_remaining")
        log(f"get_backup_time_remaining: {payload}")
        return self.keyval(payload, "response")
    
    def get_products(self):
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
        payload = self.poll(f"api/1/products")
        log(f"get_products: {payload}")
        return self.keyval(payload, "response")
    
    def set_battery_reserve(self, reserve: int):
        if reserve < 0 or reserve > 100:
            log(f"Invalid reserve level: {reserve}")
            return False
        data = {"backup_reserve_percent": reserve}
        # 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{energy_site_id}/backup' 
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/backup", "POST", data)
        return payload

    def set_operating_mode(self, mode: str):
        data = {"default_real_mode": mode}
        if mode not in ["self_consumption", "autonomous"]:
            log(f"Invalid mode: {mode}")
            return False
        # 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{energy_site_id}/operation' 
        payload = self.poll(f"api/1/energy_sites/{self.site_id}/operation", "POST", data)
        return payload
            
    def get_operating_mode(self):
        return self.keyval(self.get_site_info(), "default_real_mode")

    def get_battery_reserve(self):
        return self.keyval(self.get_site_info(), "backup_reserve_percent")

    def getsites(self):
        payload = self.poll("api/1/products")
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
    def battery_level(self):
        return self.keyval(self.get_live_status(), "percentage_charged")
    def battery_reserve(self):
        return self.get_battery_reserve()
    def operating_mode(self):
        return self.get_operating_mode()
    def energy_left(self):
        return self.keyval(self.get_site_status(), "energy_left") # FIXME: This is not in the API
    def total_pack_energy(self):
        return self.keyval(self.get_site_status(), "total_pack_energy")  # FIXME: This is not in the API
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

        # Display current configuration if we have it
        config = self.load_config()
        if config:
            print("Current Configuration:")
            for item in config:
                val = config[item]
                if isinstance(val, dict):
                    continue
                if isinstance(val, str) and len(val) > 50:
                    val = val[:50] + "..." + val[-5:]
                print(f"  {item}: {val}")
        else:
            print("No configuration found")
        # Get the client_id and client_secret from the user
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
        response = requests.get(verify_url)
        if response.status_code != 200:
            print(f"ERROR: Could not verify PEM key file at {verify_url}")
            print(f"       Make sure you have created the PEM key file and uploaded it to your website.")
            print()
            print("Run create_pem_key.py to create a PEM key file for your website.")
            exit(1)
        print(f"   * Success: PEM Key file verified at {verify_url}.")
        print()
        # Check to see if already cached
        if self.partner_token:
            print("  Using cached token.")
            log(f"Cached partner token: {self.partner_token}")
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
            log(f"POST: https://auth.tesla.com/oauth2/v3/token {json.dumps(data)}")
            response = requests.post('https://auth.tesla.com/oauth2/v3/token', 
                            data=data, headers=headers)
            log(f"Response Code: {response.status_code}")
            partner_token = response.json()['access_token']
            self.partner_token = partner_token
            print(f"   Got Token: {partner_token[:40]}...\n")
            log(f"Partner Token: {partner_token}")
            # Save the configuration
            self.save_config()
            print("  Configuration saved")
        print()

        # Register Partner Account
        print("Step 3B - Registering your partner account...")
        if self.partner_account:
            print(f"  Already registered. Skipping...")
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
            log(f"POST: {url} {json.dumps(data)}")
            response = requests.post(url, headers=headers, data=json.dumps(data))
            log(f"  Response Code: {response.status_code}")
            self.partner_account = response.json()
            log(f"Partner Account: {json.dumps(self.partner_account, indent=4)}\n")
            # Save the configuration
            self.save_config()
            print("  Configuration saved")
        print()

        # Generate User Token
        print("Step 3C - Generating a one-time authentication token...")
        if self.access_token and self.refresh_token:
            print(f"  Using cached token...")
        else:
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
            log(f"Code: {code}")

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
            log(f"POST: https://auth.tesla.com/oauth2/v3/token {json.dumps(data)}")
            response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                            data=data, headers=headers)
            log(f"Response Code: {response.status_code}")
            # Extract access_token and refresh_token from this response
            access_token = response.json()['access_token']
            refresh_token = response.json()['refresh_token']
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
            print(f"  Using cached site_id: {self.site_id}")
        else:
            # Get list of sites
            sites = self.getsites()
            sel = 0
            # If not set, pick first site
            if not self.site_id:
                self.site_id = sites[0]['energy_site_id']
                sel = 1
            log(sites)
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
            log(f"Site ID: {self.site_id}")
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

# End of FleetAPI Class
            
# Main - Command Line Interface
if __name__ == "__main__":   
    import argparse
    # Display help if no arguments
    if len(sys.argv) == 1:
        print("Tesla FleetAPI - Command Line Interface\n")
        print("Usage: fleetapi.py command [arguments] [-h] [--debug] [--config CONFIG] [--site SITE] [--json]\n")
        print("Commands:")
        print("    setup               Setup FleetAPI for your site")
        print("    sites               List available sites")
        print("    status              Report current power status for your site")
        print("    info                Display information about your site")
        print("    getmode             Get current operational mode setting")
        print("    getreserve          Get current battery reserve level setting")
        print("    setmode             Set operatinoal mode (self_consumption or autonomous)")
        print("    setreserve          Set battery reserve level (prcentage or 'current')\n")
        print("options:")
        print("  --debug               Enable debug mode")
        print("  --config CONFIG       Specify alternate config file (default: .fleetapi.config)")
        print("  --site SITE           Specify site_id")
        print("  --json                Output in JSON format")
        exit(0)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Tesla FleetAPI - Command Line Interface')
    parser.add_argument("command", choices=["setup", "sites", "status", "info", "getmode", "getreserve",
                         "setmode", "setreserve"], help="Select command to execute")
    parser.add_argument("argument", nargs="?", default=None, help="Argument for setmode or setreserve command")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--config", help="Specify alternate config file")
    parser.add_argument("--site", help="Specify site_id")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    # Adding descriptions for each command
    parser.add_help = False  # Disabling default help message
    args = parser.parse_args()

    settings_file = CONFIGFILE
    if args.config:
        # Use alternate config file if specified
        settings_file = args.config

    # Create FleetAPI object
    settings_debug = False
    settings_site = None
    if args.debug:
        settings_debug = True
    if args.site:
        settings_site = args.site
    
    # Create FleetAPI object
    fleet = FleetAPI(configfile=settings_file, debug=settings_debug, site=settings_site)   

    # Load Configuration
    if not fleet.load_config():
        print(f"  Configuration file not found: {settings_file}")
        if args.command != "setup":
            print("  Run setup to configure environment")
            exit(1)
        else:
            fleet.setup()
            if not fleet.load_config():
                print("  Setup failed, exiting...")
                exit(1)
        exit(0)

    # Command: Run Setup
    if args.command == "setup":
        fleet.setup()
        exit(0)

    # Command: List Sites
    if args.command == "sites":
        sites = fleet.getsites()
        if args.json:
            print(json.dumps(sites, indent=4))
        else:
            for site in sites:
                print(f"  {site['energy_site_id']} - {site['site_name']}")
        exit(0)

    # Command: Status
    if args.command == "status":
        status = fleet.get_live_status()
        if args.json:
            print(json.dumps(status, indent=4))
        else:
            for key in status:
                print(f"  {key}: {status[key]}")
        exit(0)

    # Command: Site Info
    if args.command == "info":
        info = fleet.get_site_info()
        if args.json:
            print(json.dumps(info, indent=4))
        else:
            for key in info:
                print(f"  {key}: {info[key]}")
        exit(0)

    # Command: Get Operating Mode
    if args.command == "getmode":
        mode = fleet.get_operating_mode()
        if args.json:
            print(json.dumps({"mode": mode}, indent=4))
        else:
            print(f"{mode}")
        exit(0)

    # Command: Get Battery Reserve
    if args.command == "getreserve":
        reserve = fleet.get_battery_reserve()
        if args.json:
            print(json.dumps({"reserve": reserve}, indent=4))
        else:
            print(f"{reserve}")
        exit(0)

    # Command: Set Operating Mode
    if args.command == "setmode":
        if args.argument:
            # autonomous or self_consumption
            if args.argument in ["self", "self_consumption"]:
                print(fleet.set_operating_mode("self_consumption"))
            elif args.argument in ["auto", "time", "autonomous"]:
                print(fleet.set_operating_mode("autonomous"))
            else:
                print("Invalid mode, must be 'self' or 'auto'")
                exit(1)
        else:
            print("No mode specified, exiting...")
        exit(0)

    # Command: Set Battery Reserve
    if args.command == "setreserve":
        if args.argument:
            if args.argument.isdigit():
                val = int(args.argument)
                if val < 0 or val > 100:
                    print(f"Invalid reserve level {val}, must be 0-100")
                    exit(1)
            elif args.argument == "current":
                val = fleet.battery_level()
            else:
                print("Invalid reserve level, must be 0-100 or 'current' to set to current level.")
                exit(1)
            print(fleet.set_battery_reserve(int(val)))
        else:
            print("No reserve level specified, exiting...")
        exit(0)

    print("No command specified, exiting...")
    exit(1)




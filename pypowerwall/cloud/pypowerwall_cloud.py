import json
import logging
import os
import time
from typing import Optional, Union, List

from teslapy import Tesla, Battery, SolarPanel

from pypowerwall.cloud.decorators import not_implemented_mock_data
from pypowerwall.cloud.exceptions import * # pylint: disable=unused-wildcard-import
from pypowerwall.cloud.mock_data import *  # pylint: disable=unused-wildcard-import
from pypowerwall.cloud.stubs import *
from pypowerwall.pypowerwall_base import PyPowerwallBase
from pypowerwall import __version__

log = logging.getLogger(__name__)

AUTHFILE = ".pypowerwall.auth"  # Stores auth session information
SITEFILE = ".pypowerwall.site"  # Stores site id
COUNTER_MAX = 64  # Max counter value for SITE_DATA API
SITE_CONFIG_TTL = 59  # Site config cache TTL in seconds


def set_debug(debug=False, quiet=False, color=True):
    logging.basicConfig(format='%(levelname)s: %(message)s')
    if not quiet:
        log.setLevel(logging.INFO)
        if color:
            logging.basicConfig(format='\x1b[31;1m%(levelname)s: %(message)s\x1b[0m')
        if debug:
            log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.NOTSET)


def lookup(data, keylist):
    """
    Lookup a value in a nested dictionary or return None if not found.
        data - nested dictionary
        keylist - list of keys to traverse
    """
    for key in keylist:
        if key in data:
            data = data[key]
        else:
            return None
    return data

# pylint: disable=too-many-public-methods
# noinspection PyMethodMayBeStatic
class PyPowerwallCloud(PyPowerwallBase):
    def __init__(self, email: Optional[str], pwcacheexpire: int = 5, timeout: int = 5, siteid: Optional[int] = None,
                 authpath: str = ""):
        super().__init__(email)
        self.site = None
        self.tesla = None
        self.apilock = {}  # holds lock flag for pending cloud api requests
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire cache
        self.siteindex = 0  # site index to use
        self.siteid = siteid  # site id to use
        self.counter = 0  # counter for SITE_DATA API
        self.authpath = os.path.expanduser(authpath)  # path to cloud auth and site files
        self.timeout = timeout
        self.authfile = os.path.join(self.authpath, AUTHFILE)
        self.sitefile = os.path.join(self.authpath, SITEFILE)
        self.poll_api_map = self.init_poll_api_map()
        self.post_api_map = self.init_post_api_map()

        if self.siteid is None:
            # Check for site file
            if os.path.exists(self.sitefile):
                with open(self.sitefile) as file:
                    try:
                        self.siteid = int(file.read())
                    except Exception as exc:
                        log.debug(f"Unable to determine siteid from sitefile, using ID '0' instead: {exc}")
                        self.siteid = 0
            else:
                self.siteindex = 0
        log.debug(f" -- cloud: Using site {self.siteid} for {self.email}")

    def init_post_api_map(self) -> dict:
        return {
            "/api/operation": self.post_api_operation,
        }

    def init_poll_api_map(self) -> dict:
        # API map for local to cloud call conversion
        return {
            # Somewhat Real Actions
            "/api/devices/vitals": self.get_api_devices_vitals,
            "/api/meters/aggregates": self.get_api_meters_aggregates,
            "/api/operation": self.get_api_operation,
            "/api/site_info": self.get_api_site_info,
            "/api/site_info/site_name": self.get_api_site_info_site_name,
            "/api/status": self.get_api_status,
            "/api/system_status": self.get_api_system_status,
            "/api/system_status/grid_status": self.get_api_system_status_grid_status,
            "/api/system_status/soe": self.get_api_system_status_soe,
            "/vitals": self.get_vitals,
            # Possible Actions
            "/api/login/Basic": self.api_login_basic,
            "/api/logout": self.api_logout,
            # Mock Actions
            "/api/auth/toggle/supported": self.get_api_auth_toggle_supported,
            "/api/customer": self.get_api_customer,
            "/api/customer/registration": self.get_api_customer_registration,
            "/api/installer": self.get_api_installer,
            "/api/meters": self.get_api_meters,
            "/api/meters/readings": self.get_api_unimplemented_timeout,
            "/api/meters/site": self.get_api_meters_site,
            "/api/meters/solar": self.get_unimplemented_api,
            "/api/networks": self.get_api_unimplemented_timeout,
            "/api/powerwalls": self.get_api_powerwalls,
            "/api/site_info/grid_codes": self.get_api_unimplemented_timeout,
            "/api/sitemaster": self.get_api_sitemaster,
            "/api/solar_powerwall": self.get_api_solar_powerwall,
            "/api/solars": self.get_api_solars,
            "/api/solars/brands": self.get_api_solars_brands,
            "/api/synchrometer/ct_voltage_references": self.get_api_synchrometer_ct_voltage_references,
            "/api/system/update/status": self.get_api_system_update_status,
            "/api/system_status/grid_faults": self.get_api_system_status_grid_faults,
            "/api/troubleshooting/problems": self.get_api_troubleshooting_problems,
        }

    def authenticate(self):
        log.debug('Tesla cloud mode enabled')
        # Check to see if we can connect to the cloud
        if not self.connect():
            err = "Unable to connect to Tesla Cloud - run pypowerwall setup"
            log.debug(err)
            raise ConnectionError(err)
        self.auth = {'AuthCookie': 'local', 'UserRecord': 'local'}

    def connect(self):
        """
        Connect to Tesla Cloud via teslapy
        """
        # Check for auth file
        if not os.path.exists(self.authfile):
            msg = f"Missing auth file {self.authfile} - run setup"
            log.debug(msg)
            raise PyPowerwallCloudNoTeslaAuthFile(msg)

        # Create Tesla instance
        self.tesla = Tesla(self.email, cache_file=self.authfile, timeout=self.timeout)
        # Check to see if we have a cached token
        if not self.tesla.authorized:
            # Login to Tesla account and cache token
            state = self.tesla.new_state()
            code_verifier = self.tesla.new_code_verifier()
            try:
                self.tesla.fetch_token(
                    authorization_response=self.tesla.authorization_url(state=state, code_verifier=code_verifier)
                )
            except Exception as err:
                log.error("Login failure - %s" % repr(err))
                return False
        # Get site info
        sites = self.getsites()
        if sites is None or len(sites) == 0:
            log.error("No sites found for %s" % self.email)
            return False
        # Find siteindex - Lookup energy_site_id in sites
        if self.siteid is None:
            self.siteid = sites[0]['energy_site_id']  # default to first site
            self.siteindex = 0
        else:
            found = False
            for idx, site in enumerate(sites):
                if site['energy_site_id'] == self.siteid:
                    self.siteindex = idx
                    found = True
                    break
            if not found:
                log.error("Site %r not found for %s" % (self.siteid, self.email))
                return False
        # Set site
        self.site = sites[self.siteindex]
        site_name = sites[self.siteindex].get('site_name') or 'Unknown'
        log.debug(f"Connected to Tesla Cloud - Site {self.siteid} "
                  f"({site_name}) for {self.email}")
        return True

    # Function to map Powerwall API to Tesla Cloud Data
    def poll(self, api: str, force: bool = False,
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla Cloud Data
        """
        if self.tesla is None:
            raise PyPowerwallCloudTeslaNotConnected
        # API Map - Determine what data we need based on Powerwall APIs
        log.debug(f" -- cloud: Request for {api}")

        func = self.poll_api_map.get(api)
        if func:
            kwargs = {
                'force': force,
                'recursive': recursive,
                'raw': raw
            }
            return func(**kwargs)
        else:
            # raise PyPowerwallCloudNotImplemented(api)
            # or pass a custom error response:
            return {"ERROR": f"Unknown API: {api}"}

    def post(self, api: str, payload: Optional[dict], din: Optional[str],
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla Cloud Data
        """
        if self.tesla is None:
            raise PyPowerwallCloudTeslaNotConnected
        # API Map - Determine what data we need based on Powerwall APIs
        log.debug(f" -- cloud: Request for {api}")

        func = self.post_api_map.get(api)
        if func:
            kwargs = {
                'payload': payload,
                'din': din
            }
            res = func(**kwargs)
            if res:
                # invalidate appropriate read cache on (more or less) successful call to writable API
                super()._invalidate_cache(api)
            return res
        else:
            # raise PyPowerwallCloudNotImplemented(api)
            # or pass a custom error response:
            return {"ERROR": f"Unknown API: {api}"}

    def getsites(self) -> Optional[List[Union[Battery, SolarPanel]]]:
        """
        Get list of Tesla Energy sites
        """
        if self.tesla is None:
            return None
        try:
            sitelist = self.tesla.battery_list() + self.tesla.solar_list()
        except Exception as err:
            log.error(f"Failed to retrieve sitelist - {repr(err)}")
            return None
        return sitelist

    def change_site(self, siteid):
        """
        Change the site to the one that matches the siteid
        """
        # Check that siteid is a valid number
        try:
            siteid = int(siteid)
        except Exception as err:
            log.error("Invalid siteid - %s" % repr(err))
            return False
        # Check for valid site index
        sites = self.getsites()
        if sites is None or len(sites) == 0:
            log.error("No sites found for %s" % self.email)
            return False
        # Set siteindex - Find siteid in sites
        for idx, site in enumerate(sites):
            if site.get('energy_site_id') != siteid:
                continue
            self.siteid = siteid
            self.siteindex = idx
            self.site = site
            site_name = site.get('site_name', 'Unknown')
            log.debug(f"Changed site to {self.siteid} ({site_name}) for {self.email}")
            return True
        log.error("Site %d not found for %s" % (siteid, self.email))
        return False

    # Functions to get data from Tesla Cloud

    def _site_api(self, name: str, ttl: int, force: bool, **kwargs):
        """
        Private function to get site data from Tesla Cloud using
        TeslaPy API.  This function uses a lock to prevent threads
        from sending multiple requests to Tesla Cloud at the same time.
        It also caches the data for ttl seconds.

        Arguments:
            name - TeslaPy API name
            ttl - Cache expiration time in seconds
            force - If True skip cache
            kwargs - Variable arguments to pass to API call

        Returns (response, cached)
            response - TeslaPy API response
            cached - True if cached data was returned
        """
        if self.tesla is None:
            log.debug(" -- cloud: No connection to Tesla Cloud")
            return None, False
        # Check for lock and wait if api request already sent
        if name in self.apilock:
            locktime = time.perf_counter()
            while self.apilock[name]:
                time.sleep(0.2)
                if time.perf_counter() >= locktime + self.timeout:
                    log.debug(f" -- cloud: Timeout waiting for {name} (unable to acquire lock)")
                    return None, False
        # Check to see if we have cached data
        if self.pwcache.get(name) is not None and not force:
            if self.pwcachetime[name] > time.perf_counter() - ttl:
                log.debug(f" -- cloud: Returning cached {name} data")
                return self.pwcache[name], True

        response = None
        try:
            # Set lock
            self.apilock[name] = True
            response = self.site.api(name, **kwargs)
        except Exception as err:
            log.error(f"Failed to retrieve {name} - {repr(err)}")
        else:
            log.debug(f" -- cloud: Retrieved {name} data")
            self.pwcache[name] = response
            self.pwcachetime[name] = time.perf_counter()
        finally:
            # Release lock
            self.apilock[name] = False
        return response, False

    def get_battery(self, force: bool = False):
        """
        Get site battery data from Tesla Cloud

            "response": {
                "resource_type": "battery",
                "site_name": "Tesla Energy Gateway",
                "gateway_id": "1232100-00-E--TGxxxxxxxxxxxx",
                "energy_left": 21276.894736842103,
                "total_pack_energy": 25939,
                "percentage_charged": 82.02665768472995,
                "battery_type": "ac_powerwall",
                "backup_capable": true,
                "battery_power": -220,
                "go_off_grid_test_banner_enabled": null,
                "storm_mode_enabled": false,
                "powerwall_onboarding_settings_set": true,
                "powerwall_tesla_electric_interested_in": null,
                "vpp_tour_enabled": null,
                "sync_grid_alert_enabled": true,
                "breaker_alert_enabled": true
            }
        """
        # GET api/1/energy_sites/{site_id}/site_status
        (response, _) = self._site_api("SITE_SUMMARY", self.pwcacheexpire, language="en", force=force)
        return response

    def get_site_power(self, force: bool = False):
        """
        Get site power data from Tesla Cloud

            "response": {
                "solar_power": 1290,
                "energy_left": 21276.894736842103,
                "total_pack_energy": 25939,
                "percentage_charged": 82.02665768472995,
                "backup_capable": true,
                "battery_power": -220,
                "load_power": 1070,
                "grid_status": "Active", # Solar Only will use "Unknown"
                "grid_services_active": false,
                "grid_power": 0,
                "grid_services_power": 0,
                "generator_power": 0,
                "island_status": "on_grid",
                "storm_mode_active": false,
                "timestamp": "2023-12-17T14:23:31-08:00",
                "wall_connectors": []
            }
        """
        # GET api/1/energy_sites/{site_id}/live_status?counter={counter}&language=en
        (response, cached) = self._site_api("SITE_DATA", self.pwcacheexpire, counter=self.counter + 1,
                                            language="en", force=force)
        if not cached:
            self.counter = (self.counter + 1) % COUNTER_MAX
        return response

    def get_site_config(self, force: bool = False):
        """
        Get site configuration data from Tesla Cloud

        Args:
            force:     if True, skip cache
        "response": {
            "id": "1232100-00-E--TGxxxxxxxxxxxx",
            "site_name": "Tesla Energy Gateway",
            "backup_reserve_percent": 80,
            "default_real_mode": "self_consumption",
            "installation_date": "xxxx-xx-xx",
            "user_settings": {
                "go_off_grid_test_banner_enabled": false,
                "storm_mode_enabled": false,
                "powerwall_onboarding_settings_set": true,
                "powerwall_tesla_electric_interested_in": false,
                "vpp_tour_enabled": true,
                "sync_grid_alert_enabled": true,
                "breaker_alert_enabled": false
            },
            "components": {
                "solar": true,
                "solar_type": "pv_panel",
                "battery": true,
                "grid": true,
                "backup": true,
                "gateway": "teg",
                "load_meter": true,
                "tou_capable": true,
                "storm_mode_capable": true,
                "flex_energy_request_capable": false,
                "car_charging_data_supported": false,
                "off_grid_vehicle_charging_reserve_supported": true,
                "vehicle_charging_performance_view_enabled": false,
                "vehicle_charging_solar_offset_view_enabled": false,
                "battery_solar_offset_view_enabled": true,
                "solar_value_enabled": true,
                "energy_value_header": "Energy Value",
                "energy_value_subheader": "Estimated Value",
                "energy_service_self_scheduling_enabled": true,
                "show_grid_import_battery_source_cards": true,
                "set_islanding_mode_enabled": true,
                "wifi_commissioning_enabled": true,
                "backup_time_remaining_enabled": true,
                "rate_plan_manager_supported": true,
                "battery_type": "solar_powerwall",
                "configurable": true,
                "grid_services_enabled": false,
                "inverters": [
                    {
                        "device_id": "xxxxxxxxxxxxxxxxxx",
                        "din": "xxxxxxxxx",
                        "is_active": true,
                        "site_id": "xxxxxxxxxxxxxxxxxx",
                    }
                ],
                "edit_setting_permission_to_export": true,
                "edit_setting_grid_charging": true,
                "edit_setting_energy_exports": true
            },
            "version": "23.28.2 27626f98",
            "battery_count": 2,
            "tariff_content": { # removed for brevity
            },
            "tariff_id": "SCE-TOU-PRIME",
            "nameplate_power": 10800,
            "nameplate_energy": 27000,
            "installation_time_zone": "America/Los_Angeles",
            "off_grid_vehicle_charging_reserve_percent": 65,
            "max_site_meter_power_ac": 1000000000,
            "min_site_meter_power_ac": -1000000000,
            "geolocation": {
                "latitude": XX.XXXXXXX,
                "longitude": XX.XXXXXXX,
                "source": "Site Address Preference"
            },
            "address": {
                "address_line1": "xxxxxx",
                "city": "xxxxxx",
                "state": "xx",
                "zip": "xxxxx",
                "country": "xx"
            },
            "vpp_backup_reserve_percent": 80
        }
    }
        """
        # GET api/1/energy_sites/{site_id}/site_info
        (response, _) = self._site_api("SITE_CONFIG", SITE_CONFIG_TTL, language="en", force=force)
        return response

    def get_time_remaining(self, force: bool = False) -> Optional[float]:
        """
        Get backup time remaining from Tesla Cloud

        {'response': {'time_remaining_hours': 7.909122698326978}}
        """
        # GET api/1/energy_sites/{site_id}/backup_time_remaining
        (response, _) = self._site_api("ENERGY_SITE_BACKUP_TIME_REMAINING", self.pwcacheexpire, language="en",
                                       force=force)

        # {'response': {'time_remaining_hours': 7.909122698326978}}
        if response is None or not isinstance(response, dict):
            return None
        if 'response' in response and 'time_remaining_hours' in response.get('response'):
            return response['response']['time_remaining_hours']

        return 0.0

    def get_api_system_status_soe(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        battery = self.get_battery(force=force)
        if battery is None:
            data = None
        else:
            percentage_charged = lookup(battery, ("response", "percentage_charged")) or 0
            # percentage_charged is scaled to keep 5% buffer at bottom
            soe = (percentage_charged + (5 / 0.95)) * 0.95
            data = {
                "percentage": soe
            }
        return data

    def get_api_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        # TOOO: Fix start_time and up_time_seconds
        force = kwargs.get('force', False)
        config = self.get_site_config(force=force)
        if config is None:
            data = None
        else:
            data = {
                "din": lookup(config, ("response", "id")),  # 1232100-00-E--TGxxxxxxxxxxxx
                "start_time": lookup(config, ("response", "installation_date")),  # "2023-10-13 04:01:45 +0800"
                "up_time_seconds": None,  # "1541h38m20.998412744s"
                "is_new": False,
                "version": lookup(config, ("response", "version")),  # 23.28.2 27626f98
                "git_hash": "27626f98a66cad5c665bbe1d4d788cdb3e94fd34",
                "commission_count": 0,
                "device_type": lookup(config, ("response", "components", "gateway")),  # teg
                "teg_type": "unknown",
                "sync_type": "v2.1",
                "cellular_disabled": False,
                "can_reboot": True
            }
        return data

    def get_api_system_status_grid_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        power = self.get_site_power(force=force)
        if power is None:
            data = None
        else:
            if lookup(power, ("response", "grid_status")) in ["Active", "Unknown"]:
                grid_status = "SystemGridConnected"
            elif not lookup(power, ("response", "grid_status")):
                # If no grid_status, assume on_grid
                grid_status = "SystemGridConnected"
            else:  # off_grid or off_grid_unintentional
                grid_status = "SystemIslandedActive"
            data = {
                "grid_status": grid_status,  # SystemIslandedActive or SystemTransitionToGrid
                "grid_services_active": lookup(power, ("response", "grid_services_active"))
                # true when participating in VPP event
            }
        return data

    def get_api_site_info_site_name(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.get_site_config(force=force)
        if config is None:
            data = None
        else:
            sitename = lookup(config, ("response", "site_name"))
            tz = lookup(config, ("response", "installation_time_zone"))
            data = {
                "site_name": sitename,
                "timezone": tz
            }
        return data

    def get_api_site_info(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.get_site_config(force=force)
        if config is None:
            data = None
        else:
            nameplate_power = int(lookup(config, ("response", "nameplate_power")) or 0) / 1000
            nameplate_energy = int(lookup(config, ("response", "nameplate_energy")) or 0) / 1000
            max_site_meter_power_ac = lookup(config, ("response", "max_site_meter_power_ac"))
            min_site_meter_power_ac = lookup(config, ("response", "min_site_meter_power_ac"))
            utility = lookup(config, ("response", "tariff_content", "utility"))
            sitename = lookup(config, ("response", "site_name"))
            tz = lookup(config, ("response", "installation_time_zone"))
            data = {
                "max_system_energy_kWh": nameplate_energy,
                "max_system_power_kW": nameplate_power,
                "site_name": sitename,
                "timezone": tz,
                "max_site_meter_power_kW": max_site_meter_power_ac,
                "min_site_meter_power_kW": min_site_meter_power_ac,
                "nominal_system_energy_kWh": nameplate_energy,
                "nominal_system_power_kW": nameplate_power,
                "panel_max_current": None,
                "grid_code": {
                    "grid_code": None,
                    "grid_voltage_setting": None,
                    "grid_freq_setting": None,
                    "grid_phase_setting": None,
                    "country": None,
                    "state": None,
                    "utility": utility
                }
            }
        return data

    # pylint: disable=unused-argument
    # noinspection PyUnusedLocal
    def get_api_devices_vitals(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        # Protobuf payload - not implemented - use /vitals instead
        data = None
        log.warning("Protobuf payload - not implemented for /api/devices/vitals - use /vitals instead")
        return data

    def get_vitals(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        # Simulated Vitals
        force = kwargs.get('force', False)
        config = self.get_site_config(force=force)
        power = self.get_site_power(force=force)
        if config is None or power is None:
            data = None
        else:
            din = lookup(config, ("response", "id"))
            parts = din.split("--")
            if len(parts) == 2:
                part_number = parts[0]
                serial_number = parts[1]
            else:
                part_number = None
                serial_number = None
            version = lookup(config, ("response", "version"))
            # Get grid status
            #    also "grid_status": "Active"
            island_status = lookup(power, ("response", "island_status"))
            if island_status == "on_grid":
                alert = "SystemConnectedToGrid"
            elif island_status == "off_grid_intentional":
                alert = "ScheduledIslandContactorOpen"
            elif island_status == "off_grid":
                alert = "UnscheduledIslandContactorOpen"
            else:
                alert = ""
                if lookup(power, ("response", "grid_status")) in ["Active", "Unknown"]:
                    alert = "SystemConnectedToGrid"
            data = {
                f'STSTSM--{part_number}--{serial_number}': {
                    'partNumber': part_number,
                    'serialNumber': serial_number,
                    'manufacturer': 'Simulated',
                    'firmwareVersion': version,
                    'lastCommunicationTime': int(time.time()),
                    'teslaEnergyEcuAttributes': {
                        'ecuType': 207
                    },
                    'STSTSM-Location': 'Simulated',
                    'alerts': [
                        alert
                    ]
                }
            }
        return data

    def get_api_meters_aggregates(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.get_site_config(force=force)
        power = self.get_site_power(force=force)
        if config is None or power is None:
            data = None
        else:
            timestamp = lookup(power, ("response", "timestamp"))
            solar_power = lookup(power, ("response", "solar_power"))
            battery_power = lookup(power, ("response", "battery_power"))
            load_power = lookup(power, ("response", "load_power"))
            grid_power = lookup(power, ("response", "grid_power"))
            battery_count = lookup(config, ("response", "battery_count"))
            inverters = lookup(config, ("response", "components", "inverters"))
            if inverters is not None:
                solar_inverters = len(inverters)
            elif lookup(config, ("response", "components", "solar")):
                solar_inverters = 1
            else:
                solar_inverters = 0
            data = API_METERS_AGGREGATES_STUB
            data['site'].update({
                "last_communication_time": timestamp,
                "instant_power": grid_power,
            })
            data['battery'].update({
                "last_communication_time": timestamp,
                "instant_power": battery_power,
                "num_meters_aggregated": battery_count,
            })
            data['load'].update({
                "last_communication_time": timestamp,
                "instant_power": load_power,

            })
            data['solar'].update({
                "last_communication_time": timestamp,
                "instant_power": solar_power,
                "num_meters_aggregated": solar_inverters,
            })
        return data

    def get_api_operation(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.get_site_config(force)
        if config is None:
            data = None
        else:
            default_real_mode = lookup(config, ("response", "default_real_mode"))
            backup_reserve_percent = lookup(config, ("response", "backup_reserve_percent")) or 0
            # backup_reserve_percent is scaled to keep 5% buffer at bottom
            backup = (backup_reserve_percent + (5 / 0.95)) * 0.95
            data = {
                "real_mode": default_real_mode,
                "backup_reserve_percent": backup
            }
        return data

    def get_api_system_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        power = self.get_site_power(force=force)
        config = self.get_site_config(force=force)
        battery = self.get_battery(force=force)
        if power is None or config is None or battery is None:
            data = None
        else:
            # timestamp = lookup(power, ("response", "timestamp"))
            solar_power = lookup(power, ("response", "solar_power"))
            # battery_power = lookup(power, ("response", "battery_power"))
            # load_power = lookup(power, ("response", "load_power"))
            grid_services_power = lookup(power, ("response", "grid_services_power"))
            # grid_status = lookup(power, ("response", "grid_status"))
            # grid_services_active = lookup(power, ("response", "grid_services_active"))
            battery_count = lookup(config, ("response", "battery_count"))
            total_pack_energy = lookup(battery, ("response", "total_pack_energy"))
            energy_left = lookup(battery, ("response", "energy_left"))
            nameplate_power = lookup(config, ("response", "nameplate_power"))
            # nameplate_energy = lookup(config, ("response", "nameplate_energy"))
            if lookup(power, ("response", "island_status")) == "on_grid":
                grid_status = "SystemGridConnected"
            else:  # off_grid or off_grid_unintentional
                grid_status = "SystemIslandedActive"
                # "grid_status": "Active"
                if lookup(power, ("response", "grid_status")) in ["Active", "Unknown"]:
                    grid_status = "SystemGridConnected"
            data = API_SYSTEM_STATUS_STUB  # TODO: see inside API_SYSTEM_STATUS_STUB definition
            data.update({
                "nominal_full_pack_energy": total_pack_energy,
                "nominal_energy_remaining": energy_left,
                "max_charge_power": nameplate_power,
                "max_discharge_power": nameplate_power,
                "max_apparent_power": nameplate_power,
                "grid_services_power": grid_services_power,
                "system_island_state": grid_status,
                "available_blocks": battery_count,
                "solar_real_power_limit": solar_power,
                "blocks_controlled": battery_count,
            })

        return data

    def set_grid_charging(self, mode: str) -> bool:
        """
        Enable/Disable grid charging mode (mode: "on" or "off")
        """
        if mode in ["on", "yes"] or mode is True:
            mode = False
        elif mode in ["off", "no"] or mode is False:
            mode = True
        else:
            log.debug(f"Invalid mode: {mode}")
            return False
        response = self._site_api("ENERGY_SITE_IMPORT_EXPORT_CONFIG", ttl=SITE_CONFIG_TTL, force=True,
                                   disallow_charge_from_grid_with_solar_installed = mode)
        # invalidate cache
        super()._invalidate_cache("SITE_CONFIG")
        self.pwcachetime["SITE_CONFIG"] = 0
        return response

    def set_grid_export(self, mode: str) -> bool:
        """
        Set grid export mode (battery_ok, pv_only, or never) 
        
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
        # POST api/1/energy_sites/{site_id}/grid_import_export
        response = self._site_api("ENERGY_SITE_IMPORT_EXPORT_CONFIG", ttl=SITE_CONFIG_TTL, force=True,
                                    customer_preferred_export_rule = mode)
        # invalidate cache
        super()._invalidate_cache("SITE_CONFIG")
        self.pwcachetime["SITE_CONFIG"] = 0
        return response

    def get_grid_charging(self, force=False):
        """ Get allow grid charging allowed mode (True or False) """
        components = self.get_site_config(force=force).get("response").get("components") or {}
        state = components.get("disallow_charge_from_grid_with_solar_installed")
        return not state

    def get_grid_export(self, force=False):
        """ Get grid export mode (battery_ok, pv_only, or never) """
        components = self.get_site_config(force=force).get("response").get("components") or {}
        # Check to see if non_export_configured - pre-PTO setting
        if components.get("non_export_configured"):
            return "never"
        mode = components.get("customer_preferred_export_rule") or "battery_ok"
        return mode

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def api_logout(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return {"status": "ok"}

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def api_login_basic(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return {"status": "ok"}

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_meters_site(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads(METERS_SITE)

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_unimplemented_api(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return None

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_unimplemented_timeout(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return "TIMEOUT!"

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_auth_toggle_supported(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return {"toggle_auth_supported": True}

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_sitemaster(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return {"status": "StatusUp", "running": True, "connected_to_tesla": True, "power_supply_mode": False,
                "can_reboot": "Yes"}

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_powerwalls(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads(POWERWALLS)

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_customer_registration(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads('{"privacy_notice":null,"limited_warranty":null,"grid_services":null,"marketing":null,'
                          '"registered":true,"timed_out_registration":false}')

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_system_update_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads('{"state":"/update_succeeded","info":{"status":["nonactionable"]},'
                          '"current_time":1702756114429,"last_status_time":1702753309227,"version":"23.28.2 27626f98",'
                          '"offline_updating":false,"offline_update_error":"","estimated_bytes_per_second":null}')

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_system_status_grid_faults(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads('[]')

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_solars(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads('[{"brand":"Tesla","model":"Solar Inverter 7.6","power_rating_watts":7600}]')

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_solars_brands(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads(SOLARS_BRANDS)

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_customer(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return {"registered": True}

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_meters(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads(METERS)

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_installer(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads(INSTALLER)

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_synchrometer_ct_voltage_references(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads('{"ct1":"Phase1","ct2":"Phase2","ct3":"Phase1"}')

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_troubleshooting_problems(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return json.loads('{"problems":[]}')

    # noinspection PyUnusedLocal
    @not_implemented_mock_data
    def get_api_solar_powerwall(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        return {}

    def setup(self, email=None):
        """
        Set up the Tesla Cloud connection
        """
        print("Tesla Account Setup")
        print("-" * 60)
        tuser = ""
        # Check for .pypowerwall.auth file
        if os.path.isfile(self.authfile):
            print("  Found existing Tesla Cloud setup file ({})".format(self.authfile))
            with open(self.authfile) as json_file:
                try:
                    data = json.load(json_file)
                    tuser = list(data.keys())[0]
                    print(f"  Using Tesla User: {tuser}")
                    # Ask user if they want to overwrite the existing file
                    response = input("\n  Overwrite existing file? [y/N]: ").strip()
                    if response.lower() == "y":
                        tuser = ""
                        os.remove(self.authfile)
                    else:
                        self.email = tuser
                except Exception as err:
                    log.debug(f"Unable to use existing authfile {self.authfile}: {err}")
                    tuser = ""

        if tuser == "":
            # Create new AUTHFILE
            if email not in (None, "") and "@" in email:
                tuser = email.strip()
                print(f"\n  Email address: {tuser}")
            else:
                while True:
                    response = input("\n  Email address: ").strip()
                    if "@" not in response:
                        print("  - Error: Invalid email address")
                    else:
                        tuser = response
                        break

            # Update the Tesla User
            self.email = tuser

            # Create Tesla instance
            tesla = Tesla(self.email, cache_file=self.authfile)

            if not tesla.authorized:
                # Login to Tesla account and cache token
                state = tesla.new_state()
                code_verifier = tesla.new_code_verifier()

                try:
                    print("\nOpen the below address in your browser to login.\n")
                    print(tesla.authorization_url(state=state, code_verifier=code_verifier))
                except Exception as err:
                    log.error(f"Connection failure - {repr(err)}")

                print("\nAfter login, paste the URL of the 'Page Not Found' webpage below.\n")

                tesla.close()
                tesla = Tesla(self.email, state=state, code_verifier=code_verifier, cache_file=self.authfile)

                if not tesla.authorized:
                    try:
                        tesla.fetch_token(authorization_response=input("Enter URL after login: "))
                        print("-" * 60)
                    except Exception as err:
                        log.error(f"Connection failure - {repr(err)}")
                        return False

        # Connect to Tesla Cloud
        self.siteid = None
        if not self.connect():
            print("\nERROR: Failed to connect to Tesla Cloud")
            return False

        sites = self.getsites()
        if sites is None or len(sites) == 0:
            print("\nERROR: No sites found for %s" % self.email)
            return False

        print(f"\n{len(sites)} Sites Found (* = default)")
        print("-" * 60)

        # Check for existing site file
        if os.path.isfile(self.sitefile):
            with open(self.sitefile) as file:
                try:
                    self.siteid = int(file.read())
                except Exception as exc:
                    log.debug(f"Unable to read siteid from {self.sitefile}, using '0' instead: {exc}")
                    self.siteid = 0

        idx = 1
        self.siteindex = 0
        siteids = []
        for s in sites:
            if s["energy_site_id"] == self.siteid:
                sitelabel = "*"
                self.siteindex = idx - 1
            else:
                sitelabel = " "
            siteids.append(s["energy_site_id"])
            if "site_name" in s and "resource_type" in s:
                print(" %s%d - %s (%s) - Type: %s" % (sitelabel, idx, s["site_name"],
                                                      s["energy_site_id"], s["resource_type"]))
            else:
                print(" %s%d - %s (%s) - Type: %s" % (sitelabel, idx, "Unknown",
                                                      s["energy_site_id"], "Unknown"))
            idx += 1
        # Ask user to select a site
        while True:
            response = input(f"\n  Select a site [{self.siteindex + 1}]: ").strip()
            if response.isdigit():
                idx = int(response)
                if 1 <= idx < (len(sites) + 1):
                    self.siteindex = idx - 1
                    break
                else:
                    print(f"  - Invalid: {response} is not a valid site number")
            else:
                break
        # Lookup the site id
        self.siteid = siteids[self.siteindex]
        self.site = sites[self.siteindex]
        site_name = sites[self.siteindex].get('site_name') or 'Unknown'
        print("\nSelected site %d - %s (%s)" % (self.siteindex + 1, site_name, self.siteid))
        # Write the site id to the sitefile
        with open(self.sitefile, "w") as f:
            f.write(str(self.siteid))

        return True

    def close_session(self):
        if self.tesla:
            self.tesla.logout()
        else:
            log.error("Tesla cloud not connected")
        self.auth = {}

    def vitals(self) -> Optional[dict]:
        return self.poll('/vitals')

    def post_api_operation(self, **kwargs):
        payload = kwargs.get('payload', {})
        din = kwargs.get('din')

        if not payload.get('backup_reserve_percent') and not payload.get('real_mode'):
            raise PyPowerwallCloudInvalidPayload("/api/operation payload missing required parameters. Either "
                                                 "'backup_reserve_percent or 'real_mode', or both must present.")

        if not din:
            log.warning("No valid DIN provided, will adjust the first battery on site.")

        batteries = self.tesla.battery_list()
        log.debug(f"Got batteries: {batteries}")
        for battery in batteries:
            if din and battery.get('gateway_id') != din:
                continue
            try:
                op_level = battery.set_backup_reserve_percent(payload['backup_reserve_percent'])
                op_mode = battery.set_operation(payload['real_mode'])
                log.debug(f"Op Level: {op_level}")
                log.debug(f"Op Mode: {op_mode}")
                return {
                    'set_backup_reserve_percent': {
                        'backup_reserve_percent': payload['backup_reserve_percent'],
                        'din': din,
                        'result': op_level
                    },
                    'set_operation': {
                        'real_mode': payload['real_mode'],
                        'din': din,
                        'result': op_mode
                    }
                }
            except Exception as exc:
                return {'error': f"{exc}"}
        return {
            'set_backup_reserve_percent': {
                'backup_reserve_percent': payload['backup_reserve_percent'],
                'din': din,
                'result': 'BatteryNotFound'
            },
            'set_operation': {
                'real_mode': payload['real_mode'],
                'din': din,
                'result': 'BatteryNotFound'
            }
        }


if __name__ == "__main__":
    import sys
    # Command Line Debugging Mode
    print(f"pyPowerwall - Powerwall Gateway Cloud Test [v{__version__}]")
    set_debug(quiet=False, debug=True, color=True)

    tesla_user = None
    # Check for .pypowerwall.auth file
    AUTHPATH = os.environ.get('PW_AUTH_PATH', "")
    auth_file = os.path.join(os.path.expanduser(AUTHPATH), AUTHFILE)
    if os.path.isfile(auth_file):
        # Read the json file
        with open(auth_file) as tjson_file:
            # noinspection PyBroadException
            try:
                tdata = json.load(tjson_file)
                tesla_user = list(tdata.keys())[0]
                log.info(f"Using Tesla User: {tesla_user}")
            except Exception:
                tesla_user = None

    while not tesla_user:
        tresponse = input("Tesla User Email address: ").strip()
        if "@" not in tresponse:
            log.info("Invalid email address\n")
        else:
            tesla_user = tresponse
            break

    cloud = PyPowerwallCloud(tesla_user, authpath=AUTHPATH)

    if not cloud.connect():
        log.info("Failed to connect to Tesla Cloud")
        cloud.setup()
        if not cloud.connect():
            log.critical("Failed to connect to Tesla Cloud")
            sys.exit(1)

    log.info("Connected to Tesla Cloud")

    log.info("Site Data")
    tsites = cloud.getsites()
    log.info(tsites)

    items = ['/api/status', '/api/system_status/grid_status', '/api/site_info/site_name',
             '/api/devices/vitals', '/api/system_status/soe', '/api/meters/aggregates',
             '/api/operation', '/api/system_status', '/api/synchrometer/ct_voltage_references',
             '/vitals']
    for i in items:
        log.info(f"poll({i}):")
        log.info(cloud.poll(i))

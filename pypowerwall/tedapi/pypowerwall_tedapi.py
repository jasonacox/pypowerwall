import json
import logging
import os
import time
from typing import Optional, Union, List

from pypowerwall.tedapi.tedapi import TeslaGateway, GW_IP

from pypowerwall.tedapi.decorators import not_implemented_mock_data
from pypowerwall.tedapi.exceptions import *
from pypowerwall.tedapi.mock_data import *
from pypowerwall.tedapi.stubs import *
from pypowerwall.pypowerwall_base import PyPowerwallBase


log = logging.getLogger(__name__)


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


# noinspection PyMethodMayBeStatic
class PyPowerwallGateway(PyPowerwallBase):
    def __init__(self, password = None, ip = GW_IP, pwcacheexpire: int = 5, timeout: int = 5):
        super().__init__(email)
        self.tedapi = None
        self.din = None
        self.password = password
        self.ip = ip
        self.apilock = {}  # holds lock flag for pending tedapi api requests
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire cache
        self.siteindex = 0  # site index to use
        self.siteid = siteid  # site id to use
        self.counter = 0  # counter for SITE_DATA API
        self.timeout = timeout
        self.poll_api_map = self.init_poll_api_map()
        self.post_api_map = self.init_post_api_map()
        self.auth = {'AuthCookie': 'tedapi', 'UserRecord': 'tedapi'}  # Bogus local auth record

        log.debug(f" -- tedapi: Tesla Gateway IP: {self.ip} with: {self.password}")

    def init_post_api_map(self) -> dict:
        return {
            "/api/operation": self.post_api_operation,
        }

    def init_poll_api_map(self) -> dict:
        # API map for local to tedapi call conversion
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
        log.debug('Tesla tedapi mode enabled')
        # Check to see if we can connect to the tedapi
        if not self.connect():
            err = "Unable to connect to Tesla Gateway - run pypowerwall setup"
            log.debug(err)
            raise ConnectionError(err)

    def connect(self):
        """
        Connect to Tesla Gateway via teslapy
        """
        # Create Tesla instance
        self.tedapi = TeslaGateway(self.ip, self.password)
        # Get din from Tesla Gateway
        self.din = self.tedapi.get_din()
        if self.din is None:
            log.error("Failed to retrieve din from Tesla Gateway")
            return False
        log.debug(f"Connected to Tesla Gateway DIN: {self.din}")
        return True

    # Function to map Powerwall API to Tesla Gateway Data
    def poll(self, api: str, force: bool = False,
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla Gateway Data
        """
        if self.tedapi is None:
            raise PyPowerwallGatewaNotConnected
        # API Map - Determine what data we need based on Powerwall APIs
        log.debug(f" -- tedapi: Request for {api}")

        func = self.poll_api_map.get(api)
        if func:
            kwargs = {
                'force': force,
                'recursive': recursive,
                'raw': raw
            }
            return func(**kwargs)
        else:
            # raise PyPowerwallGatewayNotImplemented(api)
            # or pass a custom error response:
            return {"ERROR": f"Unknown API: {api}"}

    def post(self, api: str, payload: Optional[dict], din: Optional[str],
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla Gateway Data
        """
        # raise PyPowerwallGatewayNotImplemented(api)
        # or pass a custom error response:
        return {"ERROR": f"Unknown API: {api}"}

    # Functions to get data from Tesla Gateway

    def _site_api(self, name: str, ttl: int, force: bool, **kwargs):
        """
        Private function to get site data from Tesla Gateway using
        tedapi API.  This function uses a lock to prevent threads
        from sending multiple requests to Tesla Gateway at the same time.
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
        if self.tedapi is None:
            log.debug(f" -- tedapi: No connection to Tesla Gateway")
            return None, False
        # Check for lock and wait if api request already sent
        if name in self.apilock:
            locktime = time.perf_counter()
            while self.apilock[name]:
                time.sleep(0.2)
                if time.perf_counter() >= locktime + self.timeout:
                    log.debug(f" -- tedapi: Timeout waiting for {name} (unable to acquire lock)")
                    return None, False
        # Check to see if we have cached data
        if self.pwcache.get(name) is not None and not force:
            if self.pwcachetime[name] > time.perf_counter() - ttl:
                log.debug(f" -- tedapi: Returning cached {name} data")
                return self.pwcache[name], True

        response = None
        try:
            # Set lock
            self.apilock[name] = True
            response = self.tedapi.api(name, **kwargs)
        except Exception as err:
            log.error(f"Failed to retrieve {name} - {repr(err)}")
        else:
            log.debug(f" -- tedapi: Retrieved {name} data")
            self.pwcache[name] = response
            self.pwcachetime[name] = time.perf_counter()
        finally:
            # Release lock
            self.apilock[name] = False
            return response, False

    def get_site_config(self, force: bool = False):
        """
        Get site configuration data from Tesla Gateway

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
        Get backup time remaining from Tesla Gateway

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
            if lookup(power, ("response", "grid_status")) == "Active":
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
                if lookup(power, ("response", "grid_status")) == "Active":
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
                if lookup(power, ("response", "grid_status")) == "Active":
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
        Set up the Tesla Gateway connection
        """
        print("Tesla Account Setup")
        print("-" * 60)
        tuser = ""
        # Check for .pypowerwall.auth file
        if os.path.isfile(self.authfile):
            print("  Found existing Tesla Gateway setup file ({})".format(self.authfile))
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

        # Connect to Tesla Gateway
        self.siteid = None
        if not self.connect():
            print("\nERROR: Failed to connect to Tesla Gateway")
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
            log.error(f"Tesla tedapi not connected")
        self.auth = {}

    def vitals(self) -> Optional[dict]:
        return self.poll('/vitals')

    def post_api_operation(self, **kwargs):
        payload = kwargs.get('payload', {})
        din = kwargs.get('din')

        if not payload.get('backup_reserve_percent') and not payload.get('real_mode'):
            raise PyPowerwallGatewayInvalidPayload("/api/operation payload missing required parameters. Either "
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
    # Test code
    set_debug(quiet=False, debug=True, color=True)

    # Ask user for IP address and password
    ip = input(f"Enter IP address [{GW_IP}]: ").strip()
    if ip == "":
        ip = GW_IP
    password = input("Enter password: ").strip()

    if ip == "" or password == "":
        log.error("IP address and password are required")
        exit(1)

    tedapi = PyPowerwallGateway(ip, password)

    if not tedapi.connect():
        log.error("Failed to connect to Tesla Gateway")
        exit(1)
        
    log.info("Connected to Tesla Gateway")

    items = ['/api/status', '/api/system_status/grid_status', '/api/site_info/site_name',
             '/api/devices/vitals', '/api/system_status/soe', '/api/meters/aggregates',
             '/api/operation', '/api/system_status', '/api/synchrometer/ct_voltage_references',
             '/vitals']
    for i in items:
        log.info(f"poll({i}):")
        log.info(tedapi.poll(i))

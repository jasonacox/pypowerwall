import json
import logging
import os
import time
from typing import Optional, Union

from pypowerwall.fleetapi.fleetapi import FleetAPI, CONFIGFILE
from pypowerwall.fleetapi.decorators import not_implemented_mock_data
from pypowerwall.fleetapi.exceptions import * # pylint: disable=unused-wildcard-import
from pypowerwall.fleetapi.mock_data import *  # pylint: disable=unused-wildcard-import
from pypowerwall.fleetapi.stubs import *
from pypowerwall.pypowerwall_base import PyPowerwallBase
from pypowerwall import __version__

log = logging.getLogger(__name__)

# Defaults
COUNTER_MAX = 64  # Max counter value for SITE_DATA API
SITE_CONFIG_TTL = 59  # Site config cache TTL in seconds

fleet_api_urls = {
    "North America, Asia-Pacific": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "Europe, Middle East, Africa": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "China": "https://fleet-api.prd.cn.vn.cloud.tesla.cn"
}


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
    if len(keylist) == 1:
        return data.get(keylist[0])
    for key in keylist:
        if key in data:
            data = data[key]
        else:
            return None
    return data


# pylint: disable=too-many-public-methods
# noinspection PyMethodMayBeStatic
class PyPowerwallFleetAPI(PyPowerwallBase):
    def __init__(self, email: Optional[str], pwcacheexpire: int = 5, timeout: int = 5, siteid: Optional[int] = None,
                 authpath: str = ""):
        super().__init__(email)
        self.fleet = None
        self.apilock = {}  # holds lock flag for pending api requests
        self.siteindex = 0  # site index to use
        self.siteid = siteid  # site id to use
        self.counter = 0  # counter for SITE_DATA API
        self.timeout = timeout
        self.poll_api_map = self.init_poll_api_map()
        self.post_api_map = self.init_post_api_map()
        self.authpath = authpath
        self.configfile = os.path.join(self.authpath, CONFIGFILE)
        self.auth = {'AuthCookie': 'local', 'UserRecord': 'local'}  # Bogus local auth record

        # Initialize FleetAPI
        self.fleet = FleetAPI(configfile=self.configfile, site_id=self.siteid,
                              pwcacheexpire=pwcacheexpire, timeout=self.timeout)

        # Load Configuration
        if not os.path.isfile(self.fleet.configfile):
            log.debug(f" -- fleetapi: Configuration file not found: {self.configfile} - run setup")

        # Set siteid
        if self.siteid is None:
            self.siteid = self.fleet.site_id

        log.debug(f" -- fleetapi: Using site {self.siteid} for {self.email}")

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
        log.debug('Tesla fleetapi mode enabled')
        # Check to see if we can connect to the cloud
        if not self.connect():
            err = "Unable to connect to Tesla FleetAPI - run pypowerwall fleetapi setup"
            log.debug(err)
            raise ConnectionError(err)

    def connect(self):
        """
        Connect to Tesla FleetAPI
        """
        # Get site info
        sites = self.getsites()
        self.siteindex = 0
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
                if 'energy_site_id' in site:
                    if site['energy_site_id'] == self.siteid:
                        self.siteindex = idx
                        found = True
                        break
            if not found:
                log.error("Site %r not found for %s" % (self.siteid, self.email))
                return False
        # Set site
        siteref = sites[self.siteindex]
        self.siteid = siteref.get('energy_site_id')
        site_name = siteref.get('site_name', 'Unknown')
        log.debug(f"Connected to Tesla FleetAPI - Site {self.siteid} "
                  f"({site_name}) for {self.email}")
        return True

    # Function to map Powerwall API to Tesla FleetAPI Data
    def poll(self, api: str, force: bool = False,
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla FleetAPI Data
        """
        # API Map - Determine what data we need based on Powerwall APIs
        log.debug(f" -- fleetapi: Request for {api}")

        func = self.poll_api_map.get(api)
        if func:
            kwargs = {
                'force': force,
                'recursive': recursive,
                'raw': raw
            }
            return func(**kwargs)
        else:
            return {"ERROR": f"Unknown API: {api}"}

    def post(self, api: str, payload: Optional[dict], din: Optional[str],
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla FleetAPI Data
        """
        # API Map - Determine what data we need based on Powerwall APIs
        log.debug(f" -- fleetapi: Request for {api}")

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
            # raise PyPowerwallFleetAPINotImplemented(api)
            # or pass a custom error response:
            return {"ERROR": f"Unknown API: {api}"}

    def getsites(self):
        """
        Get list of Tesla Energy sites
        """
        if self.siteid is None:
            return None
        try:
            sitelist = self.fleet.getsites()
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

    # FleetAPI Functions
    def get_site_info(self):
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
        return self.fleet.get_site_info()

    def get_live_status(self):
        """
        {
            'solar_power': 0,
            'percentage_charged': 55.164177150990625,
            'backup_capable': True,
            'battery_power': 4080,
            'load_power': 4080,
            'grid_status': 'Active', # Solar Only will use "Unknown"
            'grid_services_active': False,
            'grid_power': 0,
            'grid_services_power': 0,
            'generator_power': 0,
            'island_status': 'on_grid',
            'storm_mode_active': False,
            'timestamp': '2024-05-11T22:43:20-07:00',
            'wall_connectors': []
        }
        """
        return self.fleet.get_live_status()

    def get_time_remaining(self, force: bool = False) -> Optional[float]:
        """
        Get backup time remaining from Tesla FleetAPI
        """
        response = self.fleet.get_backup_time_remaining(force=force)
        if response is None or not isinstance(response, dict):
            return None
        if response.get('time_remaining_hours'):
            return response['time_remaining_hours']
        return 0.0

    def get_api_system_status_soe(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        percentage_charged = self.fleet.battery_level(force=force) or 0
        data = {
            "percentage": percentage_charged
        }
        return data

    def get_api_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.fleet.get_site_info(force=force)
        if config is None:
            data = None
        else:
            data = {
                "din": config.get("id"),  # 1232100-00-E--TGxxxxxxxxxxxx
                "start_time": config.get("installation_date"),  # "2023-10-13 04:01:45 +0800"
                "up_time_seconds": None,  # "1541h38m20.998412744s"
                "is_new": False,
                "version": config.get("version"),  # 23.28.2 27626f98
                "git_hash": "27626f98a66cad5c665bbe1d4d788cdb3e94fd34",
                "commission_count": 0,
                "device_type": lookup(config, ("components", "gateway")),  # teg
                "teg_type": "unknown",
                "sync_type": "v2.1",
                "cellular_disabled": False,
                "can_reboot": True
            }
        return data

    def get_api_system_status_grid_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        power = self.fleet.get_live_status(force=force)
        if power is None:
            data = None
        else:
            if not power.get("grid_status") or power.get("grid_status") in ["Active", "Unknown"]:
                grid_status = "SystemGridConnected"
            else:  # off_grid or off_grid_unintentional
                grid_status = "SystemIslandedActive"
            data = {
                "grid_status": grid_status,  # SystemIslandedActive or SystemTransitionToGrid
                "grid_services_active": power.get("grid_services_active")
                # true when participating in VPP event
            }
        return data

    def get_api_site_info_site_name(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.fleet.get_site_info(force=force)
        if config is None:
            data = None
        else:
            sitename = config.get("site_name")
            tz = config.get("installation_time_zone")
            data = {
                "site_name": sitename,
                "timezone": tz
            }
        return data

    def get_api_site_info(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.fleet.get_site_info(force=force)
        if config is None:
            data = None
        else:
            nameplate_power = int(config.get("nameplate_power") or 0) / 1000
            nameplate_energy = int(config.get("nameplate_energy") or 0) / 1000
            max_site_meter_power_ac = config.get("max_site_meter_power_ac")
            min_site_meter_power_ac = config.get("min_site_meter_power_ac")
            utility = config.get("tariff_content", {}).get("utility")
            sitename = config.get("site_name")
            tz = config.get("installation_time_zone")
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
        config = self.fleet.get_site_info(force=force)
        power = self.fleet.get_live_status(force=force)
        if config is None or power is None:
            data = None
        else:
            din = config.get("id")
            parts = din.split("--")
            if len(parts) == 2:
                part_number = parts[0]
                serial_number = parts[1]
            else:
                part_number = None
                serial_number = None
            version = config.get("version")
            # Get grid status
            #    also "grid_status": "Active"
            island_status = power.get("island_status")
            if island_status == "on_grid":
                alert = "SystemConnectedToGrid"
            elif island_status == "off_grid_intentional":
                alert = "ScheduledIslandContactorOpen"
            elif island_status == "off_grid":
                alert = "UnscheduledIslandContactorOpen"
            else:
                alert = ""
                if power.get("grid_status") in ["Active", "Unknown"]:
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
        config = self.fleet.get_site_info(force=force)
        power = self.fleet.get_live_status(force=force)
        if config is None or power is None:
            data = None
        else:
            timestamp = power.get("timestamp")
            solar_power = power.get("solar_power")
            battery_power = power.get("battery_power")
            load_power = power.get("load_power")
            grid_power = power.get("grid_power")
            battery_count = config.get("battery_count")
            inverters = lookup(config, ("components", "inverters"))

            if inverters is not None:
                solar_inverters = len(inverters)
            elif lookup(config, ("components", "solar")):
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
        config = self.fleet.get_site_info(force=force)
        if config is None:
            data = None
        else:
            default_real_mode = config.get("default_real_mode")
            backup_reserve_percent = config.get("backup_reserve_percent") or 0
            backup = (backup_reserve_percent + (5 / 0.95)) * 0.95
            data = {
                "real_mode": default_real_mode,
                "backup_reserve_percent": backup
            }
        return data

    def get_api_system_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        power = self.fleet.get_live_status(force=force)
        config = self.fleet.get_site_info(force=force)
        if power is None or config is None:
            data = None
        else:
            solar_power = power.get("solar_power")
            grid_services_power = power.get("grid_services_power")
            battery_count = config.get("battery_count")
            total_pack_energy = self.fleet.total_pack_energy(force=force)
            energy_left = self.fleet.energy_left(force=force)
            nameplate_power = config.get("nameplate_power")

            if power.get("island_status") == "on_grid":
                grid_status = "SystemGridConnected"
            else:  # off_grid or off_grid_unintentional
                grid_status = "SystemIslandedActive"
                # "grid_status": "Active"
                if power.get("grid_status") in ["Active", "Unknown"]:
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

    # pylint: disable=unused-argument
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
        Set up the Tesla FleetAPI connection
        """
        return self.fleet.setup()

    def close_session(self):
        return True

    def vitals(self) -> Optional[dict]:
        return self.poll('/vitals')

    def post_api_operation(self, **kwargs):
        payload = kwargs.get('payload', {})
        din = kwargs.get('din')
        resp = {}

        if not payload.get('backup_reserve_percent') and not payload.get('real_mode'):
            raise PyPowerwallFleetAPIInvalidPayload("/api/operation payload missing required parameters. Either "
                                                 "'backup_reserve_percent or 'real_mode', or both must present.")

        if din:
            log.debug("FleetAPI mode operates on entire site, not din. Ignoring din parameter.")

        if payload.get('backup_reserve_percent') is not None:
            backup_reserve_percent = payload['backup_reserve_percent']
            if backup_reserve_percent is False:
                backup_reserve_percent = 0
            op_level = self.fleet.set_battery_reserve(backup_reserve_percent)
            resp['set_backup_reserve_percent'] = {
                'backup_reserve_percent': payload['backup_reserve_percent'],
                'result': op_level
            }
        if payload.get('real_mode') is not None:
            real_mode = payload['real_mode']
            op_mode = self.fleet.set_operating_mode(real_mode)
            resp['set_operation'] = {
                'real_mode': payload['real_mode'],
                'result': op_mode
            }
        return resp

    def set_grid_charging(self, mode) -> bool:
        return self.fleet.set_grid_charging(mode)

    def set_grid_export(self, mode:str) -> bool:
        return self.fleet.set_grid_export(mode)

    def get_grid_export(self, force=False) -> str:
        return self.fleet.get_grid_export(force=force)

    def get_grid_charging(self, force=False) -> bool:
        return self.fleet.get_grid_charging(force=force)

if __name__ == "__main__":
    import sys
    # Command Line Debugging Mode
    print(f"pyPowerwall - Powerwall Gateway FleetAPI Test [v{__version__}]")
    set_debug(quiet=False, debug=True, color=True)

    fleet = PyPowerwallFleetAPI(email="")

    if not fleet.connect():
        log.info("Failed to connect to Tesla FleetAPI")
        fleet.setup()
        if not fleet.connect():
            log.critical("Failed to connect to Tesla FleetAPI")
            sys.exit(1)

    log.info("Connected to Tesla FleetAPI")

    log.info("Site Data")
    tsites = fleet.getsites()
    log.info(tsites)

    items = ['/api/status', '/api/system_status/grid_status', '/api/site_info/site_name',
             '/api/devices/vitals', '/api/system_status/soe', '/api/meters/aggregates',
             '/api/operation', '/api/system_status', '/api/synchrometer/ct_voltage_references',
             '/vitals']
    for i in items:
        log.info(f"poll({i}):")
        log.info(fleet.poll(i))

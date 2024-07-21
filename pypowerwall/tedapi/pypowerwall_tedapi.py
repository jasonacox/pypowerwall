import json
import logging
from typing import Optional, Union
import math

from pypowerwall.tedapi import TEDAPI, GW_IP, lookup
from pypowerwall.tedapi.decorators import not_implemented_mock_data
from pypowerwall.tedapi.exceptions import * # pylint: disable=unused-wildcard-import
from pypowerwall.tedapi.mock_data import *  # pylint: disable=unused-wildcard-import
from pypowerwall.tedapi.stubs import *
from pypowerwall.pypowerwall_base import PyPowerwallBase
from pypowerwall import __version__

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

# Compute the line-to-line voltage of two and three phase legs
def compute_LL_voltage(v1n, v2n, v3n=None):
    """
    Compute the line-to-line voltage of two and three phase legs
    Args: v1n, v2n, v3n - line-to-neutral voltages
    """
    if not v3n:
        # single phase voltage - 180 degrees out of phase
        return v1n + v2n
    else:
        # three phase voltage - 120 degrees out of phase
        v12 = math.sqrt(v1n**2 + v2n**2 + v1n * v2n)
        v23 = math.sqrt(v2n**2 + v3n**2 + v2n * v3n)
        v31 = math.sqrt(v3n**2 + v1n**2 + v3n * v1n)
        avg_ll_voltage = (v12 + v23 + v31) / 3
        return avg_ll_voltage

# pylint: disable=too-many-public-methods
# noinspection PyMethodMayBeStatic
class PyPowerwallTEDAPI(PyPowerwallBase):
    def __init__(self, gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
                 pwconfigexpire: int = 300, host: str = GW_IP) -> None:
        super().__init__("nobody@nowhere.com")
        self.tedapi = None
        self.timeout = timeout
        self.pwcacheexpire = pwcacheexpire
        self.pwconfigexpire = pwconfigexpire
        self.host = host
        self.gw_pwd = gw_pwd
        self.debug = debug
        self.poll_api_map = self.init_poll_api_map()
        self.post_api_map = self.init_post_api_map()
        self.siteid = None
        self.auth = {'AuthCookie': 'local', 'UserRecord': 'local'}  # Bogus local auth record

        # Initialize TEDAPI
        self.tedapi = TEDAPI(self.gw_pwd, debug=self.debug, host=self.host, timeout=self.timeout)
        log.debug(f" -- tedapi: Attempting to connect to {self.host}...")
        if not self.tedapi.connect():
            raise ConnectionError(f"Unable to connect to Tesla TEDAPI at {self.host}")
        log.debug(f" -- tedapi: Connected to {self.host}")

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
            "/vitals": self.vitals,
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
        # Check to see if we can connect to the cloud
        if not self.connect():
            err = "Unable to connect to TEDAPI - Check network connectivity and Gateway password."
            log.debug(err)
            raise ConnectionError(err)

    def connect(self):
        return self.tedapi.connect()

    # Function to map Powerwall API to Tesla TEDAPI Data
    def poll(self, api: str, force: bool = False,
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla TEDAPI Data
        """
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
            return {"ERROR": f"Unknown API: {api}"}

    def post(self, api: str, payload: Optional[dict], din: Optional[str],
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        """
        Map Powerwall API to Tesla TEDAPI Data
        """
        # API Map - Determine what data we need based on Powerwall APIs
        log.debug(f" -- tedapi: Request for {api}")

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
            # raise PyPowerwallTEDAPINotImplemented(api)
            # or pass a custom error response:
            return {"ERROR": f"Unknown API: {api}"}

    def getsites(self):
        return None

    def change_site(self, siteid):
        log.debug(f"TEDAPI does not support sites - ignoring siteid: {siteid}")
        return False

    # TEDAPI Functions
    def get_site_info(self):
        """
        Get the site config from the TEDAPI
        """
        return self.tedapi.get_config()

    def get_live_status(self):
        """
        Get the live status from the TEDAPI
        """
        return self.tedapi.get_status()

    def get_time_remaining(self, force: bool = False) -> Optional[float]:
        return self.tedapi.backup_time_remaining(force=force)

    def get_api_system_status_soe(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        percentage_charged = self.tedapi.battery_level(force=force)
        if not percentage_charged:
            return None
        data = {
            "percentage": percentage_charged
        }
        return data

    def get_api_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        firmware_version = self.tedapi.get_firmware_version(force=force)
        if config is None:
            data = None
        else:
            data = {
                "din": config.get("vin"),
                "start_time": lookup(config,["site_info", "battery_commission_date"]),
                "up_time_seconds": None,
                "is_new": False,
                "version": firmware_version,
                "git_hash": None,
                "commission_count": 0,
                "device_type": None, 
                "teg_type": "unknown",
                "sync_type": "unknown",
                "cellular_disabled": False,
                "can_reboot": True
            }
        return data

    def get_api_system_status_grid_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        status = self.tedapi.get_status(force=force)
        grid_state = lookup(status, ["esCan", "bus", "ISLANDER", "ISLAND_GridConnection", "ISLAND_GridConnected"])
        if not grid_state:
            return None
        if grid_state == "ISLAND_GridConnected_Connected":
            grid_status = "SystemGridConnected"
        else:
            grid_status = "SystemIslandedActive"
        data = {
            "grid_status": grid_status,
            "grid_services_active": None, # TODO
        }
        return data

    def get_api_site_info_site_name(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        sitename = lookup(config, ["site_info", "site_name"])
        tz = lookup(config, ["site_info", "timezone"])
        data = {
            "site_name": sitename,
            "timezone": tz
        }
        return data

    def get_api_site_info(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        """
        "site_info": {
            "battery_commission_date": "2021-09-25T16:05:08-07:00",
            "backup_reserve_percent": 24,
            "max_site_meter_power_ac": 1000000000,
            "min_site_meter_power_ac": -1000000000,
            "nominal_system_energy_ac": 27,
            "nominal_system_power_ac": 10.8,
            "on_grid_solar_curtailment_enabled": true,
            "tariff_content": {},
            "grid_code": "60Hz_240V_s_UL1741SA:2019_California",
            "country": "United States",
            "state": "California",
            "utility": "Southern California Edison",
            "site_name": "Cox Energy Gateway",
            "timezone": "America/Los_Angeles",
            "ITC_cliff": 0,
            "panel_max_current": 100
        },
        """
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        if not isinstance(config, dict):
            return None
        data = {
            "max_system_energy_kWh": config.get("nominal_system_energy_ac"),
            "max_system_power_kW": config.get("nominal_system_power_ac"),
            "site_name": config.get("site_name"),
            "timezone": config.get("timezone"),
            "max_site_meter_power_kW": config.get("max_site_meter_power_ac"),
            "min_site_meter_power_kW": config.get("min_site_meter_power_ac"),
            "nominal_system_energy_kWh": config.get("nominal_system_energy_ac"),
            "nominal_system_power_kW": config.get("nominal_system_power_ac"),
            "panel_max_current": config.get("panel_max_current"),
            "grid_code": {
                "grid_code": config.get("grid_code"),
                "grid_voltage_setting": None,
                "grid_freq_setting": None,
                "grid_phase_setting": None,
                "country": config.get("country"),
                "state": config.get("state"),
                "utility": config.get("utility")
            }
        }
        return data

    # noinspection PyUnusedLocal
    def get_api_devices_vitals(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]: # pylint: disable=unused-argument
        # Protobuf payload - not implemented - use /vitals instead
        data = None
        log.warning("Protobuf payload - not implemented for /api/devices/vitals - use /vitals instead")
        return data

    def get_vitals(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]: # pylint: disable=unused-argument
        return self.tedapi.vitals(force=kwargs.get('force', False))

    def get_api_meters_aggregates(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        status = self.tedapi.get_status(force=force)
        # ensure both are dictionary objects
        if not isinstance(config, dict) or not isinstance(status, dict):
            return None
        timestamp = lookup(status, ("system", "time"))
        solar_power = self.tedapi.current_power(force=force, location="solar")
        battery_power = self.tedapi.current_power(force=force, location="battery")
        load_power = self.tedapi.current_power(force=force, location="load")
        grid_power = self.tedapi.current_power(force=force, location="site")
        # Compute load (home) voltages and current
        v_load = lookup(status, ("esCan","bus","ISLANDER", "ISLAND_AcMeasurements")) or {}
        v1n = v_load.get("ISLAND_VL1N_Main", 0)
        v2n = v_load.get("ISLAND_VL2N_Main", 0)
        v3n = v_load.get("ISLAND_VL3N_Main", 0)
        vll_load = compute_LL_voltage(v1n, v2n, v3n)
        # Compute site (grid) voltages
        v_site = lookup(status, ("esCan","bus","ISLANDER", "ISLAND_AcMeasurements")) or {}
        v1n = v_site.get("ISLAND_VL1N_Main", 0)
        v2n = v_site.get("ISLAND_VL2N_Main", 0)
        v3n = v_site.get("ISLAND_VL3N_Main", 0)
        vll_site = compute_LL_voltage(v1n, v2n, v3n)
        meter_x = lookup(status, ("esCan","bus","SYNC","METER_X_AcMeasurements")) or {}
        i1 = meter_x.get("METER_X_CTA_I", 0)
        i2 = meter_x.get("METER_X_CTB_I", 0)
        i3 = meter_x.get("METER_X_CTC_I", 0)
        i_site = i1 + i2 + i3
        # Compute solar (pv) voltages
        v_solar = lookup(status, ("esCan","bus","PVS")) or []
        sum_vll_solar = 0
        count_solar = 0
        for i in range(len(v_solar)):
            v = lookup(v_solar[i], ("PVS_Status", "PVS_vLL")) or 0
            if v:
                sum_vll_solar += v
                count_solar += 1
        vll_solar = sum_vll_solar / count_solar if count_solar else 0
        # Compute battery voltages
        v_battery = lookup(status, ("esCan","bus","PINV")) or []
        sum_vll_battery = 0
        count_battery = 0
        for i in range(len(v_battery)):
            v = lookup(v_battery[i], ("PINV_Status", "PINV_Vout")) or 0
            if v:
                sum_vll_battery += v
                count_battery += 1
        vll_battery = sum_vll_battery / count_battery if count_battery else 0
        # Load payload template
        data = API_METERS_AGGREGATES_STUB
        data['site'].update({
            "last_communication_time": timestamp,
            "instant_power": grid_power,
            "instant_average_voltage": vll_site,
            "instant_average_current": i_site,
            "instant_total_current": i_site,
            "num_meters_aggregated": 1,
            "disclaimer": "voltage and current calculated from tedapi data",
        })
        data['battery'].update({
            "last_communication_time": timestamp,
            "instant_power": battery_power,
            "num_meters_aggregated": count_battery,
            "instant_average_voltage": vll_battery,
        })
        data['load'].update({
            "last_communication_time": timestamp,
            "instant_power": load_power,
            "instant_average_voltage": vll_load,
            "disclaimer": "voltage calculated from tedapi data",
        })
        data['solar'].update({
            "last_communication_time": timestamp,
            "instant_power": solar_power,
            "num_meters_aggregated": count_solar,
            "instant_average_voltage": vll_solar,
            "disclaimer": "voltage calculated from tedapi data",
        })
        return data

    def get_api_operation(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        if not isinstance(config, dict):
            return None
        else:
            default_real_mode = config.get("default_real_mode")
            backup = lookup(config, ["site_info", "backup_reserve_percent"]) or 0
            data = {
                "real_mode": default_real_mode,
                "backup_reserve_percent": backup
            }
        return data

    def get_api_system_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        status = self.tedapi.get_status(force=force)
        config = self.tedapi.get_config(force=force)
        if not isinstance(status, dict) or not isinstance(config, dict):
            return None
        status = self.tedapi.get_status(force=force)
        grid_state = lookup(status, ["esCan", "bus", "ISLANDER", "ISLAND_GridConnection", "ISLAND_GridConnected"])
        if not grid_state:
            grid_status = None
        elif grid_state == "ISLAND_GridConnected_Connected":
            grid_status = "SystemGridConnected"
        else:
            grid_status = "SystemIslandedActive"
        total_pack_energy = lookup(status, ["control", "systemStatus", "nominalFullPackEnergyWh"]) or 0
        energy_left = lookup(status, ["control", "systemStatus", "nominalEnergyRemainingWh"]) or 0
        batteryBlocks = lookup(config, ["control", "batteryBlocks"]) or []
        battery_count = len(batteryBlocks) or 0
        data = API_SYSTEM_STATUS_STUB  # TODO: see inside API_SYSTEM_STATUS_STUB definition
        blocks = self.tedapi.get_blocks(force=force)
        b = []
        for bk in blocks:
            b.append(blocks[bk])
        data.update({
            "nominal_full_pack_energy": total_pack_energy,
            "nominal_energy_remaining": energy_left,
            "max_charge_power": None,
            "max_discharge_power": None,
            "max_apparent_power": None,
            "grid_services_power": None,
            "system_island_state": grid_status,
            "available_blocks": battery_count,
            "solar_real_power_limit": None,
            "blocks_controlled": battery_count,
            "battery_blocks": b
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
        Set up the Tesla TEDAPI connection
        """
        return None

    def close_session(self):
        return True

    def vitals(self) -> Optional[dict]:
        return self.tedapi.vitals()

    def post_api_operation(self, **kwargs):
        log.error("No support for TEDAPI POST APIs.")


if __name__ == "__main__":
    import sys
    # Command Line Debugging Mode
    print(f"pyPowerwall - Powerwall Gateway TEDAPI Test [v{__version__}]")
    set_debug(quiet=False, debug=True, color=True)

    # Get the Gateway Password from the command line
    if len(sys.argv) < 2:
        log.error("Usage: python -m pypowerwall.tedapi.pypowerwall_tedapi <gateway_password>")
        sys.exit(1)
    password = sys.argv[1]

    # Create TEDAPI Object and get Configuration and Status
    tedapi = PyPowerwallTEDAPI(password, debug=True)

    if not tedapi.connect():
        log.info("Failed to connect to Tesla TEDAPI")
        sys.exit(1)

    log.info("Connected to Tesla TEDAPI")

    log.info("Site Data")
    items = ['/api/status', '/api/system_status/grid_status', '/api/site_info/site_name',
             '/api/devices/vitals', '/api/system_status/soe', '/api/meters/aggregates',
             '/api/operation', '/api/system_status', '/api/synchrometer/ct_voltage_references',
             '/vitals']
    for i in items:
        log.info(f"poll({i}):")
        log.info(tedapi.poll(i))

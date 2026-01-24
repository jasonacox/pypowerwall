import json
import logging
import math
from typing import Optional, Union

from pypowerwall import __version__
from pypowerwall.pypowerwall_base import PyPowerwallBase
from pypowerwall.tedapi import GW_IP, TEDAPI, lookup
from pypowerwall.tedapi.decorators import not_implemented_mock_data
from pypowerwall.tedapi.exceptions import *  # pylint: disable=unused-wildcard-import
from pypowerwall.tedapi.mock_data import *  # pylint: disable=unused-wildcard-import
from pypowerwall.tedapi.stubs import *

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

# Compute the line-to-line voltage of single, two and three phase legs
def compute_LL_voltage(v1n=0, v2n=0, v3n=0):
    """
    Compute the line-to-line voltage for various electrical system configurations.
    
    This function handles single-phase, split-phase, and three-phase electrical systems
    by analyzing voltage magnitudes and applying appropriate calculations based on the
    number of legs with significant voltage (above 100V threshold).
    
    Args:
        v1n (float): Line 1 to neutral voltage (default: 0)
        v2n (float): Line 2 to neutral voltage (default: 0) 
        v3n (float): Line 3 to neutral voltage (default: 0)
    
    Returns:
        float: Calculated line-to-line voltage based on system configuration:
               - Sum of all 3 if no significant voltages detected (low voltage scenario)
               - Single voltage value for single-phase systems (one active leg)
               - Sum of voltages for split-phase systems (two active legs, 180° out of phase)
               - Average of all line-to-line voltages for three-phase systems (120° out of phase)
    
    Note:
        Uses 100V threshold to distinguish significant voltages from residual voltages
        that may appear on inactive legs in single-phase systems.
    """
    # Define a threshold for significant voltage
    SIGNIFICANT_VOLTAGE = 100

    # Check for single leg line voltage (UK)
    active_voltages = [v for v in (v1n, v2n, v3n) if v and abs(v) > SIGNIFICANT_VOLTAGE]
    if not active_voltages:
        # Low voltage scenario - return the sum of all voltages (handle None values)
        return (v1n or 0) + (v2n or 0) + (v3n or 0)
    if len(active_voltages) == 1:
        # single phase voltage - one leg, active leg
        return active_voltages[0]
    if len(active_voltages) == 2:
        # split phase voltage - two legs, 180 degrees out of phase
        return active_voltages[0] + active_voltages[1]
    else:
        # three phase voltage - 120 degrees out of phase
        # Ensure None values are converted to 0 for arithmetic operations
        v1 = v1n or 0
        v2 = v2n or 0
        v3 = v3n or 0
        v12 = math.sqrt(v1**2 + v2**2 + v1 * v2)
        v23 = math.sqrt(v2**2 + v3**2 + v2 * v3)
        v31 = math.sqrt(v3**2 + v1**2 + v3 * v1)
        avg_ll_voltage = (v12 + v23 + v31) / 3
        return avg_ll_voltage

# pylint: disable=too-many-public-methods
# noinspection PyMethodMayBeStatic
class PyPowerwallTEDAPI(PyPowerwallBase):
    def __init__(self, gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
                 pwconfigexpire: int = 5, host: str = GW_IP, poolmaxsize: int = 10) -> None:
        super().__init__("nobody@nowhere.com")
        self.tedapi = None
        self.timeout = timeout
        self.pwcacheexpire = pwcacheexpire
        self.pwconfigexpire = pwconfigexpire
        self.poolmaxsize = poolmaxsize
        self.host = host
        self.gw_pwd = gw_pwd
        self.debug = debug
        self.poll_api_map = self.init_poll_api_map()
        self.post_api_map = self.init_post_api_map()
        self.siteid = None
        self.auth = {'AuthCookie': 'local', 'UserRecord': 'local'}  # Bogus local auth record

        # Initialize TEDAPI
        self.tedapi = TEDAPI(gw_pwd=self.gw_pwd, debug=self.debug, host=self.host, 
                             timeout=self.timeout, pwcacheexpire=self.pwcacheexpire,
                             pwconfigexpire=self.pwconfigexpire, poolmaxsize=self.poolmaxsize)
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
            log.debug(f" -- tedapi: Calling {func.__name__} for {api}")
            kwargs = {
                'force': force,
                'recursive': recursive,
                'raw': raw
            }
            return func(**kwargs)
        else:
            log.error(f" -- tedapi: Unknown API: {api}")
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
        try:
            percentage_charged = self.tedapi.battery_level(force=force)
            if percentage_charged is None:
                log.debug("get_api_system_status_soe: battery_level returned None")
                return None
            data = {
                "percentage": percentage_charged
            }
            return data
        except Exception as e:
            log.error(f"get_api_system_status_soe: Exception {type(e).__name__}: {e}")
            raise

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

    def extract_grid_status(self, status) -> Optional[str]:
        if status is None:
            return None
        alerts = lookup(status, ["control", "alerts", "active"]) or []
        if "SystemConnectedToGrid" in alerts:
            return "SystemGridConnected"
        grid_state = lookup(status, ["esCan", "bus", "ISLANDER", "ISLAND_GridConnection", "ISLAND_GridConnected"])
        if not grid_state:
            log.debug("extract_grid_status: grid_state not found in expected path")
            return None
        if grid_state == "ISLAND_GridConnected_Connected":
            return "SystemGridConnected"
        return "SystemIslandedActive"

    def get_api_system_status_grid_status(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        try:
            status = self.tedapi.get_status(force=force)
            if status is None:
                log.debug("get_api_system_status_grid_status: get_status returned None")
                return None
            grid_status = self.extract_grid_status(status)
            if grid_status is None:
                log.debug("get_api_system_status_grid_status: extract_grid_status returned None")
                return None
            data = {
                "grid_status": grid_status,
                "grid_services_active": None, # TODO
            }
            return data
        except Exception as e:
            log.error(f"get_api_system_status_grid_status: Exception {type(e).__name__}: {e}")
            raise

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
        """
        Return Powerwall-style /api/meters/aggregates using TEDAPI data.
        Each section (site, load, solar, battery) is handled by a helper for clarity.
        """
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        status = self.tedapi.get_status(force=force)
        if not isinstance(config, dict) or not isinstance(status, dict):
            return None
        timestamp = lookup(status, ("system", "time"))
        data = API_METERS_AGGREGATES_STUB

        # --- Site (Grid) ---
        site_vals = self._extract_site_section(status, config, force)
        data['site'].update(site_vals)

        # --- Load (Home) ---
        load_vals = self._extract_load_section(status, config, force)
        data['load'].update(load_vals)

        # --- Solar ---
        solar_vals = self._extract_solar_section(status, config, force)
        data['solar'].update(solar_vals)

        # --- Battery ---
        battery_vals = self._extract_battery_section(status, config, force)
        data['battery'].update(battery_vals)

        # Add timestamp to all
        for section in (data['site'], data['load'], data['solar'], data['battery']):
            section['last_communication_time'] = timestamp

        return data

    def _extract_site_section(self, status, config, force):
        """Extract site (grid) section using Meter X, then Meter Z, then Neurio. Handles 2-phase and 3-phase setups. Sets i_a_current/i_b_current negative if InstRealPower is negative."""
        grid_power = self.tedapi.current_power(force=force, location="site")
        meter_x = lookup(status, ("esCan","bus","SYNC","METER_X_AcMeasurements")) or {}
        meter_z = lookup(status, ("esCan","bus","MSA","METER_Z_AcMeasurements")) or {}
        neurio_readings = lookup(status, ("neurio", "readings"))
        v1n = v2n = v3n = 0
        i1 = i2 = i3 = 0
        used_meter = None
        # Prefer Meter X
        if meter_x and not meter_x.get("isMIA", False):
            v_site = lookup(status, ("esCan","bus","ISLANDER", "ISLAND_AcMeasurements")) or {}
            v1n = v_site.get("ISLAND_VL1N_Main", 0)
            v2n = v_site.get("ISLAND_VL2N_Main", 0)
            v3n = v_site.get("ISLAND_VL3N_Main", 0)
            i1 = meter_x.get("METER_X_CTA_I", 0)
            i2 = meter_x.get("METER_X_CTB_I", 0)
            i3 = meter_x.get("METER_X_CTC_I", 0)
            # Set i1 negative if real power is negative
            inst_real_power_a = meter_x.get("METER_X_CTA_InstRealPower")
            if inst_real_power_a is not None and inst_real_power_a < 0:
                i1 = -abs(i1)
            inst_real_power_b = meter_x.get("METER_X_CTB_InstRealPower")
            if inst_real_power_b is not None and inst_real_power_b < 0:
                i2 = -abs(i2)
            inst_real_power_c = meter_x.get("METER_X_CTC_InstRealPower")
            if inst_real_power_c is not None and inst_real_power_c < 0:
                i3 = -abs(i3)
            used_meter = "Meter X"
        # Fallback to Meter Z
        elif meter_z and not meter_z.get("isMIA", False):
            v_site = lookup(status, ("esCan","bus","ISLANDER", "ISLAND_AcMeasurements")) or {}
            v1n = v_site.get("ISLAND_VL1N_Main", 0)
            v2n = v_site.get("ISLAND_VL2N_Main", 0)
            v3n = v_site.get("ISLAND_VL3N_Main", 0)
            i1 = meter_z.get("METER_Z_CTA_I", 0)
            i2 = meter_z.get("METER_Z_CTB_I", 0)
            i3 = meter_z.get("METER_Z_CTC_I", 0)
            inst_real_power_a = meter_z.get("METER_Z_CTA_InstRealPower")
            if inst_real_power_a is not None and inst_real_power_a < 0:
                i1 = -abs(i1)
            inst_real_power_b = meter_z.get("METER_Z_CTB_InstRealPower")
            if inst_real_power_b is not None and inst_real_power_b < 0:
                i2 = -abs(i2)
            inst_real_power_c = meter_z.get("METER_Z_CTC_InstRealPower")
            if inst_real_power_c is not None and inst_real_power_c < 0:
                i3 = -abs(i3)
            used_meter = "Meter Z"
        # Fallback to Neurio
        elif neurio_readings and len(neurio_readings) > 0:
            neurio_data = self.tedapi.aggregate_neurio_data(
                config_data=config,
                status_data=status,
                meter_config_data=self.tedapi.derive_meter_config(config)
            )
            i = 1
            for d in neurio_data[1].values():
                if d["Location"] != "site":
                    continue
                current = math.copysign(d.get("InstCurrent", 0), d.get("InstRealPower", 0))
                voltage = d.get("InstVoltage", 0)
                if i == 1:
                    i1 = current
                    v1n = voltage
                elif i == 2:
                    i2 = current
                    v2n = voltage
                elif i == 3:
                    i3 = current
                    v3n = voltage
                i += 1
            used_meter = "Neurio"
        # Handle 2-phase (single phase) vs 3-phase
        if v3n == 0:
            v3n = None
        vll_site = compute_LL_voltage(v1n, v2n, v3n)
        if vll_site == 0:
            vll_site = None
        i_site = grid_power / vll_site if vll_site else None
        return {
            "instant_power": grid_power,
            "instant_average_voltage": vll_site,
            "instant_average_current": i_site,
            "i_a_current": i1,
            "i_b_current": i2,
            "i_c_current": i3,
            "instant_total_current": i_site,
            "num_meters_aggregated": 1,
            "disclaimer": f"site: voltage/current from {used_meter or 'unknown'}"
        }

    def _extract_load_section(self, status, config, force):
        """Extract load (home) section using only ISLAND_AcMeasurements for voltage. No per-phase current available."""
        load_power = self.tedapi.current_power(force=force, location="load")
        v_load = lookup(status, ("esCan","bus","ISLANDER", "ISLAND_AcMeasurements")) or {}
        v1n = v_load.get("ISLAND_VL1N_Load", 0)
        v2n = v_load.get("ISLAND_VL2N_Load", 0)
        v3n = v_load.get("ISLAND_VL3N_Load", 0)
        vll_load = compute_LL_voltage(v1n, v2n, v3n)
        if vll_load == 0:
            vll_load = None
        i_load = load_power / vll_load if vll_load else None
        return {
            "instant_power": load_power,
            "instant_average_voltage": vll_load,
            "instant_average_current": i_load,
            "i_a_current": 0,
            "i_b_current": 0,
            "i_c_current": 0,
            "instant_total_current": i_load,
            "num_meters_aggregated": 1,
            "disclaimer": "load: voltage from ISLAND_AcMeasurements, current calculated from power",
        }

    def _extract_solar_section(self, status, config, force):
        """Extract solar section using PVAC for voltage and current."""
        solar_power = self.tedapi.current_power(force=force, location="solar")
        v_solar_sum = 0
        count_solar = 0
        # Check for PW3 data first
        if self.tedapi.pw3:
            pw3_data = self.tedapi.get_pw3_vitals()
            for p in pw3_data:
                if p.startswith("PVAC--"):
                    v = pw3_data[p].get("PVAC_Vout")
                    if v:
                        v_solar_sum += v
                        count_solar += 1
        # Check for legacy PVAC data
        for p in lookup(status, ['esCan', 'bus', 'PVAC']) or {}:
            if not p['packageSerialNumber']:
                continue
            v_solar_sum += lookup(p, ['PVAC_Status', 'PVAC_Vout'])
            count_solar += 1
        vll_solar = v_solar_sum / count_solar if count_solar else 0
        meter_y = lookup(status, ("esCan","bus","SYNC","METER_Y_AcMeasurements")) or {}
        yi1 = meter_y.get("METER_Y_CTA_I", 0)
        yi2 = meter_y.get("METER_Y_CTB_I", 0)
        yi3 = meter_y.get("METER_Y_CTC_I", 0)
        # If no voltage data check METER_Y_AcMeasurements
        if not vll_solar:
            yv1 = meter_y.get("METER_Y_VL1N", 0)
            yv2 = meter_y.get("METER_Y_VL2N", 0)
            yv3 = meter_y.get("METER_Y_VL3N", 0)
            vll_solar = compute_LL_voltage(yv1, yv2, yv3)
        if vll_solar == 0:
            vll_solar = None
        i_solar = solar_power / vll_solar if vll_solar else None
        return {
            "instant_power": solar_power,
            "instant_average_voltage": vll_solar,
            "instant_average_current": i_solar,
            "i_a_current": yi1,
            "i_b_current": yi2,
            "i_c_current": yi3,
            "instant_total_current": i_solar,
            "num_meters_aggregated": count_solar,
            "disclaimer": "solar: voltage from PVAC, calculated current from power",
        }

    def _extract_battery_section(self, status, config, force):
        """Extract battery section using PINV."""
        battery_power = self.tedapi.current_power(force=force, location="battery")
        sum_vll_battery = 0
        count_battery = 0
        # Check for PW3 data first
        if self.tedapi.pw3:
            pw3_data = self.tedapi.get_pw3_vitals()
            for p in pw3_data:
                if p.startswith("TEPINV--"):
                    v = pw3_data[p].get("PINV_Vout")
                    if v:
                        sum_vll_battery += v
                        count_battery += 1
        # Check for legacy PINV data
        v_battery = lookup(status, ("esCan","bus","PINV")) or []
        for p in range(len(v_battery)):
            v = lookup(v_battery[p], ("PINV_Status", "PINV_Vout")) or 0
            if v:
                sum_vll_battery += v
                count_battery += 1
        vll_battery = sum_vll_battery / count_battery if count_battery else 0
        if vll_battery == 0:
            vll_battery = None
        i_battery = battery_power / vll_battery if vll_battery else None
        return {
            "instant_power": battery_power,
            "instant_average_voltage": vll_battery,
            "instant_average_current": i_battery,
            "instant_total_current": i_battery,
            "num_meters_aggregated": count_battery,
            "disclaimer": "battery: voltage from PINV, calculated current from power",
        }

    def get_api_operation(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
        force = kwargs.get('force', False)
        config = self.tedapi.get_config(force=force)
        if not isinstance(config, dict):
            return None
        else:
            default_real_mode = config.get("default_real_mode")
            backup = lookup(config, ["site_info", "backup_reserve_percent"])
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
        grid_status = self.extract_grid_status(status)
        total_pack_energy = lookup(status, ["control", "systemStatus", "nominalFullPackEnergyWh"])
        energy_left = lookup(status, ["control", "systemStatus", "nominalEnergyRemainingWh"])
        batteryBlocks = lookup(config, ["control", "batteryBlocks"]) or []
        battery_count = len(batteryBlocks)
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

    def vitals(self, **kwargs) -> Optional[Union[dict, list, str, bytes]]:
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

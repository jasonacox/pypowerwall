#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 Python library to pull live Powerwall or Solar history data from Tesla Owner API 
 (Tesla cloud).

 Author: Jason A. Cox based on tesla-history.py by Michael Birse
 For more information see https://github.com/jasonacox/pypowerwall

 Classes
    TeslaCloud(email, timezone, pwcacheexpire, timeout)

 Parameters
    email                   # (required) email used for logging into the gateway
    timezone                # (required) desired timezone
    pwcacheexpire = 5       # Set API cache timeout in seconds
    timeout = 10            # Timeout for HTTPS calls in seconds

"""
import sys
import os
import time
import logging
import json
try:
    from teslapy import Tesla, Retry, JsonDict, Battery, SolarPanel
except:
    sys.exit("ERROR: Missing python teslapy module. Run 'pip install teslapy'.")

AUTHFILE = ".pypowerwall.auth" # Stores auth session information

# pypowerwall cloud module version
version_tuple = (0, 0, 1)
version = __version__ = '%d.%d.%d' % version_tuple
__author__ = 'jasonacox'

log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

def set_debug(toggle=True, color=True):
    """Enable verbose logging"""
    if(toggle):
        if(color):
            logging.basicConfig(format='\x1b[31;1m%(levelname)s:%(message)s\x1b[0m',level=logging.DEBUG)
        else:
            logging.basicConfig(format='%(levelname)s:%(message)s',level=logging.DEBUG)
        log.setLevel(logging.DEBUG)
        log.debug("%s [%s]\n" % (__name__, __version__))
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

class TeslaCloud:
    def __init__(self, email, pwcacheexpire=5, timeout=10):
        self.authfile = AUTHFILE
        self.email = email
        self.timeout = timeout
        self.site = None
        self.tesla = None   
        self.retry = None
        self.pwcachetime = {}                   # holds the cached data timestamps for api
        self.pwcache = {}                       # holds the cached data for api
        self.pwcacheexpire = pwcacheexpire      # seconds to expire cache 
    
    def connect(self):
        # Create retry instance for use after successful login
        self.retry = Retry(total=2, status_forcelist=(500, 502, 503, 504), backoff_factor=10)

        # Create Tesla instance
        self.tesla = Tesla(self.email, cache_file=self.authfile)

        if not self.tesla.authorized:
            # Login to Tesla account and cache token
            state = self.tesla.new_state()
            code_verifier = self.tesla.new_code_verifier()

            try:
                self.tesla.fetch_token(authorization_response=self.tesla.authorization_url(state=state, code_verifier=code_verifier))
            except Exception as err:
                log.error("ERROR: Login failure - ",err)
                return False
        else:
            # Enable retries
            self.tesla.close()
            self.tesla = Tesla(self.email, retry=self.retry, cache_file=self.authfile)
        
        # Get site info
        # TODO: Select the right site
        self.site = self.getsites()[0]

        log.debug(f"TeslaCloud connected for {self.email}")
        return True

    def get_battery(self):
        """
        Get site power data from Tesla Cloud\
        
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
        if self.tesla is None:
            return None
        # Check to see if we have cached data
        if 'get_battery' in self.pwcache:
            if self.pwcachetime['get_battery'] > time.time() - self.pwcacheexpire:
                return self.pwcache['get_battery']
        response = self.site.api("SITE_SUMMARY")
        self.pwcache['get_battery'] = response
        self.pwcachetime['get_battery'] = time.time()
        return response
    
    def get_site_power(self):
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
                "grid_status": "Active",
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
        if self.tesla is None:
            return None
        # Check to see if we have cached data
        if 'get_site_power' in self.pwcache:
            if self.pwcachetime['get_site_power'] > time.time() - self.pwcacheexpire:
                return self.pwcache['get_site_power']
        response = self.site.api("SITE_DATA")
        self.pwcache['get_site_power'] = response
        self.pwcachetime['get_site_power'] = time.time()
        return response
    
    def get_site_config(self):
        """
        Get site configuration data from Tesla Cloud
        
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
        if self.tesla is None:
            return None
        # Check to see if we have cached data
        if 'get_site_config' in self.pwcache:
            if self.pwcachetime['get_site_config'] > time.time() - self.pwcacheexpire:
                return self.pwcache['get_site_config']
        response = self.site.api("SITE_CONFIG")
        self.pwcache['get_site_config'] = response
        self.pwcachetime['get_site_config'] = time.time()
        return response

    
    def poll(self, api):
        """
        Map Powerwall API to Tesla Cloud Data

        """
        if self.tesla is None:
            return None
        # Check to see if we have cached data
        if api in self.pwcache:
            if self.pwcachetime[api] > time.time() - self.pwcacheexpire:
                return self.pwcache[api]

        # Determine what data we need based on Powerwall APIs
        # TODO: Consider making this a map?

        log.debug(f" -- cloud: Request for {api}") 
        ## Variable
        if api == '/api/status':
            # Pull from Tesla Cloud
            config = self.get_site_config()
            # Map to Powerwall API
            data = {
                "din": lookup(config, ("response", "id")),                          # 1232100-00-E--TGxxxxxxxxxxxx
                "start_time": lookup(config, ("response", "installation_date")),    # "2023-10-13 04:01:45 +0800"
                "up_time_seconds": None,                                            # "1541h38m20.998412744s"
                "is_new": False,
                "version": lookup(config, ("response", "version")),                 # 23.28.2 27626f98
                "git_hash": None,
                "commission_count": 0,
                "device_type": lookup(config, ("response", "components", "gateway")),   # teg 
                "teg_type": "unknown",
                "sync_type": "v2.1",
                "cellular_disabled": False,
                "can_reboot": True
            }
        elif api == '/api/system_status/grid_status':
            power = self.get_site_power()
            if lookup(power, ("response", "island_status")) == "on_grid": 
                grid_status = "SystemGridConnected"
            else: # off_grid or off_grid_unintentional
                grid_status = "SystemIslandedActive"
            if lookup(power, ("response", "grid_status")) == "Active":
                grid_services_active = True
            else:
                grid_services_active = False
            data = {
                "grid_status": grid_status, # SystemIslandedActive or SystemTransitionToGrid
                "grid_services_active": grid_services_active
            }

        elif api == '/api/site_info/site_name':
            config = self.get_site_config()
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
        elif api == '/api/devices/vitals':
            # Protobuf payload - not implemented - use /vitals instead
            data = {} 
        elif api == '/vitals':
            # TODO: Assemble vitals data payload
            data = {}
        elif api in ['/api/system_status/soe','/soe']:
            # TODO check to see if SOE is true value or 5% reserved
            power = self.get_site_power()
            data = {
                "percentage": lookup(power, ("response", "percentage_charged")) or 0,
            }
        elif api == '/api/meters/aggregates':
            power = self.get_site_power()
            timestamp = lookup(power, ("response", "timestamp"))
            solar_power = lookup(power, ("response", "solar_power"))
            battery_power = lookup(power, ("response", "battery_power"))
            load_power = lookup(power, ("response", "load_power"))
            grid_power = lookup(power, ("response", "grid_power"))
            config = self.get_site_config()
            battery_count = lookup(config, ("response", "battery_count"))
            solar_inverters = len(lookup(config, ("response", "components", "inverters")) or 0)

            data = {
                "site": {
                    "last_communication_time": timestamp,
                    "instant_power": grid_power,
                    "instant_reactive_power": 0,
                    "instant_apparent_power": 0,
                    "frequency": 0,
                    "energy_exported": 0,
                    "energy_imported": 0,
                    "instant_average_voltage": 0,
                    "instant_average_current": 0,
                    "i_a_current": 0,
                    "i_b_current": 0,
                    "i_c_current": 0,
                    "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                    "timeout": 1500000000,
                    "num_meters_aggregated": 1,
                    "instant_total_current": None
                },
                "battery": {
                    "last_communication_time": timestamp,
                    "instant_power": battery_power,
                    "instant_reactive_power": 0,
                    "instant_apparent_power": 0,
                    "frequency": 0,
                    "energy_exported": 0,
                    "energy_imported": 0,
                    "instant_average_voltage": 0,
                    "instant_average_current": 0,
                    "i_a_current": 0,
                    "i_b_current": 0,
                    "i_c_current": 0,
                    "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                    "timeout": 1500000000,
                    "num_meters_aggregated": battery_count,
                    "instant_total_current": 0
                },
                "load": {
                    "last_communication_time": timestamp,
                    "instant_power": load_power,
                    "instant_reactive_power": 0,
                    "instant_apparent_power": 0,
                    "frequency": 0,
                    "energy_exported": 0,
                    "energy_imported": 0,
                    "instant_average_voltage": 0,
                    "instant_average_current": 0,
                    "i_a_current": 0,
                    "i_b_current": 0,
                    "i_c_current": 0,
                    "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                    "timeout": 1500000000,
                    "instant_total_current": 0
                },
                "solar": {
                    "last_communication_time": timestamp,
                    "instant_power": solar_power,
                    "instant_reactive_power": 0,
                    "instant_apparent_power": 0,
                    "frequency": 0,
                    "energy_exported": 0,
                    "energy_imported": 0,
                    "instant_average_voltage": 0,
                    "instant_average_current": 0,
                    "i_a_current": 0,
                    "i_b_current": 0,
                    "i_c_current": 0,
                    "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                    "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                    "timeout": 1000000000,
                    "num_meters_aggregated": solar_inverters,
                    "instant_total_current": 0
                }
            }
        elif api == '/api/operation':
            config = self.get_site_config()
            default_real_mode = lookup(config, ("response", "default_real_mode"))
            backup_reserve_percent = lookup(config, ("response", "backup_reserve_percent"))

            data = {
                "real_mode": default_real_mode,
                "backup_reserve_percent": backup_reserve_percent,
                "freq_shift_load_shed_soe": 0,
                "freq_shift_load_shed_delta_f": 0
            }
        elif api == '/api/system_status':
            power = self.get_site_power()
            config = self.get_site_config()
            battery = self.get_battery()
            timestamp = lookup(power, ("response", "timestamp"))
            solar_power = lookup(power, ("response", "solar_power"))
            battery_power = lookup(power, ("response", "battery_power"))
            load_power = lookup(power, ("response", "load_power"))
            grid_power = lookup(power, ("response", "grid_power"))
            grid_status = lookup(power, ("response", "grid_status"))
            grid_services_active = lookup(power, ("response", "grid_services_active"))
            battery_count = lookup(config, ("response", "battery_count"))
            total_pack_energy = lookup(battery, ("response", "total_pack_energy"))
            energy_left = lookup(battery, ("response", "energy_left"))
            nameplate_power = lookup(config, ("response", "nameplate_power"))
            nameplate_energy = lookup(config, ("response", "nameplate_energy"))
            if lookup(power, ("response", "island_status")) == "on_grid": 
                grid_status = "SystemGridConnected"
            else: # off_grid or off_grid_unintentional
                grid_status = "SystemIslandedActive"
            
            data = { # TODO: Fill in 0 values
                "command_source": "Configuration",
                "battery_target_power": 0,
                "battery_target_reactive_power": 0,
                "nominal_full_pack_energy": total_pack_energy,
                "nominal_energy_remaining": energy_left,
                "max_power_energy_remaining": 0, # TODO: Calculate
                "max_power_energy_to_be_charged": 0, # TODO: Calculate
                "max_charge_power": nameplate_power,
                "max_discharge_power": nameplate_power,
                "max_apparent_power": nameplate_power,
                "instantaneous_max_discharge_power": 0,
                "instantaneous_max_charge_power": 0,
                "instantaneous_max_apparent_power": 0,
                "hardware_capability_charge_power": 0,
                "hardware_capability_discharge_power": 0,
                "grid_services_power": grid_power,
                "system_island_state": grid_status,
                "available_blocks": battery_count,
                "available_charger_blocks": 0,
                "battery_blocks": [], # TODO: Populate with battery blocks
                "ffr_power_availability_high": 0,
                "ffr_power_availability_low": 0,
                "load_charge_constraint": 0,
                "max_sustained_ramp_rate": 0,
                "grid_faults": [], # TODO: Populate with grid faults
                "can_reboot": "Yes",
                "smart_inv_delta_p": 0,
                "smart_inv_delta_q": 0,
                "last_toggle_timestamp": "2023-10-13T04:08:05.957195-07:00",
                "solar_real_power_limit": solar_power,
                "score": 10000,
                "blocks_controlled": battery_count,
                "primary": True,
                "auxiliary_load": 0,
                "all_enable_lines_high": True,
                "inverter_nominal_usable_power": 0,
                "expected_energy_remaining": 0
            }
        
        ## Possible Actions
        elif api == '/api/logout':
            data = '{"status":"ok"}'
        elif api == '/api/login/Basic':
            data = '{"status":"ok"}'

        ## Static Mock Values
        elif api == '/api/meters/site':
            data = json.loads('[{"id":0,"location":"site","type":"synchrometerX","cts":[true,true,false,false],"inverted":[false,false,false,false],"connection":{"short_id":"1232100-00-E--TG123456789E4G","device_serial":"JBL12345Y1F012synchrometerX","https_conf":{}},"Cached_readings":{"last_communication_time":"2023-12-16T11:48:34.135766872-08:00","instant_power":2495,"instant_reactive_power":-212,"instant_apparent_power":2503.9906149983867,"frequency":0,"energy_exported":4507438.170261594,"energy_imported":6995047.554439916,"instant_average_voltage":210.8945063295865,"instant_average_current":20.984,"i_a_current":13.3045,"i_b_current":7.6795,"i_c_current":0,"last_phase_voltage_communication_time":"2023-12-16T11:48:34.035339849-08:00","v_l1n":121.72,"v_l2n":121.78,"last_phase_power_communication_time":"2023-12-16T11:48:34.135766872-08:00","real_power_a":1584,"real_power_b":911,"reactive_power_a":-129,"reactive_power_b":-83,"last_phase_energy_communication_time":"0001-01-01T00:00:00Z","serial_number":"JBL12345Y1F012","version":"fa0c1ad02efda3","timeout":1500000000,"instant_total_current":20.984}}]')
        
        elif api == '/api/meters/solar':
            data = json.loads(None)

        elif api == '/api/auth/toggle/supported':
            data = json.loads('{"toggle_auth_supported":true}')

        elif api == '/api/sitemaster':
            data = json.loads('{"status":"StatusUp","running":true,"connected_to_tesla":true,"power_supply_mode":false,"can_reboot":"Yes"}')
        
        elif api == '/api/powerwalls':
            data = json.loads('{"enumerating": false, "updating": false, "checking_if_offgrid": false, "running_phase_detection": false, "phase_detection_last_error": "no phase information", "bubble_shedding": false, "on_grid_check_error": "on grid check not run", "grid_qualifying": false, "grid_code_validating": false, "phase_detection_not_available": true, "powerwalls": [{"Type": "", "PackagePartNumber": "2012170-25-E", "PackageSerialNumber": "TG1234567890G1", "type": "SolarPowerwall", "grid_state": "Grid_Uncompliant", "grid_reconnection_time_seconds": 0, "under_phase_detection": false, "updating": false, "commissioning_diagnostic": {"name": "Commissioning", "category": "InternalComms", "disruptive": false, "inputs": null, "checks": [{"name": "CAN connectivity", "status": "fail", "start_time": "2023-12-16T08:34:17.3068631-08:00", "end_time": "2023-12-16T08:34:17.3068696-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Enable switch", "status": "fail", "start_time": "2023-12-16T08:34:17.306875474-08:00", "end_time": "2023-12-16T08:34:17.306880724-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Internal communications", "status": "fail", "start_time": "2023-12-16T08:34:17.306886099-08:00", "end_time": "2023-12-16T08:34:17.306891223-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Firmware up-to-date", "status": "fail", "start_time": "2023-12-16T08:34:17.306896598-08:00", "end_time": "2023-12-16T08:34:17.306901723-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}], "alert": false}, "update_diagnostic": {"name": "Firmware Update", "category": "InternalComms", "disruptive": true, "inputs": null, "checks": [{"name": "Solar Inverter firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Solar Safety firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Grid code", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Powerwall firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Battery firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Inverter firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Grid code", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}], "alert": false}, "bc_type": null, "in_config": true}, {"Type": "", "PackagePartNumber": "3012170-05-B", "PackageSerialNumber": "TG1234567890G1", "type": "ACPW", "grid_state": "Grid_Uncompliant", "grid_reconnection_time_seconds": 0, "under_phase_detection": false, "updating": false, "commissioning_diagnostic": {"name": "Commissioning", "category": "InternalComms", "disruptive": false, "inputs": null, "checks": [{"name": "CAN connectivity", "status": "fail", "start_time": "2023-12-16T08:34:17.320856307-08:00", "end_time": "2023-12-16T08:34:17.320940302-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Enable switch", "status": "fail", "start_time": "2023-12-16T08:34:17.320949301-08:00", "end_time": "2023-12-16T08:34:17.320955301-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Internal communications", "status": "fail", "start_time": "2023-12-16T08:34:17.320960676-08:00", "end_time": "2023-12-16T08:34:17.320966176-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Firmware up-to-date", "status": "fail", "start_time": "2023-12-16T08:34:17.32097155-08:00", "end_time": "2023-12-16T08:34:17.3209768-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}], "alert": false}, "update_diagnostic": {"name": "Firmware Update", "category": "InternalComms", "disruptive": true, "inputs": null, "checks": [{"name": "Powerwall firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Battery firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Inverter firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Grid code", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}], "alert": false}, "bc_type": null, "in_config": true}], "gateway_din": "1232100-00-E--TG1234567890G1", "sync": {"updating": false, "commissioning_diagnostic": {"name": "Commissioning", "category": "InternalComms", "disruptive": false, "inputs": null, "checks": [{"name": "CAN connectivity", "status": "fail", "start_time": "2023-12-16T08:34:17.321101293-08:00", "end_time": "2023-12-16T08:34:17.321107918-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}, {"name": "Firmware up-to-date", "status": "fail", "start_time": "2023-12-16T08:34:17.321113792-08:00", "end_time": "2023-12-16T08:34:17.321118917-08:00", "message": "Cannot perform this action with site controller running. From landing page, either \\"STOP SYSTEM\\" or \\"RUN WIZARD\\" to proceed.", "results": {}, "debug": {}, "checks": null}], "alert": false}, "update_diagnostic": {"name": "Firmware Update", "category": "InternalComms", "disruptive": true, "inputs": null, "checks": [{"name": "Synchronizer firmware", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Islanding configuration", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}, {"name": "Grid code", "status": "not_run", "start_time": null, "end_time": null, "progress": 0, "results": null, "debug": null, "checks": null}], "alert": false}}, "msa": null, "states": null}')
        
        elif api == '/api/customer/registration':
            data = json.loads('{"privacy_notice":null,"limited_warranty":null,"grid_services":null,"marketing":null,"registered":true,"timed_out_registration":false}')
        
        elif api == '/api/system/update/status':
            data = json.loads('{"state":"/update_succeeded","info":{"status":["nonactionable"]},"current_time":1702756114429,"last_status_time":1702753309227,"version":"23.28.2 27626f98","offline_updating":false,"offline_update_error":"","estimated_bytes_per_second":null}')

        elif api == '/api/site_info':
            data = json.loads('{"max_system_energy_kWh":27,"max_system_power_kW":10.8,"site_name":"Tesla Energy Gateway","timezone":"America/Los_Angeles","max_site_meter_power_kW":1000000000,"min_site_meter_power_kW":-1000000000,"nominal_system_energy_kWh":27,"nominal_system_power_kW":10.8,"panel_max_current":100,"grid_code":{"grid_code":"60Hz_240V_s_UL1741SA:2019_California","grid_voltage_setting":240,"grid_freq_setting":60,"grid_phase_setting":"Split","country":"United States","state":"California","utility":"Southern California Edison"}}')

        elif api == '/api/system_status/grid_faults':
            data = json.loads('[]')

        elif api == '/api/site_info/grid_codes':
            data = "TIMEOUT!"

        elif api == '/api/solars':
            data = json.loads('[{"brand":"Tesla","model":"Solar Inverter 7.6","power_rating_watts":7600}]')

        elif api == '/api/solars/brands':
            data = json.loads('["ABB","Ablerex Electronics","Advanced Energy Industries","Advanced Solar Photonics","AE Solar Energy","AEconversion Gmbh","AEG Power Solutions","Aero-Sharp","Afore New Energy Technology Shanghai Co","Agepower Limit","Alpha ESS Co","Alpha Technologies","Altenergy Power System","American Electric Technologies","AMETEK Solidstate Control","Andalay Solar","Apparent","Asian Power Devices","AU Optronics","Auxin Solar","Ballard Power Systems","Beacon Power","Beijing Hua Xin Liu He Investment (Australia) Pty","Beijing Kinglong New Energy","Bergey Windpower","Beyond Building Group","Beyond Building Systems","BYD Auto Industry Company Limited","Canadian Solar","Carlo Gavazzi","CFM Equipment Distributors","Changzhou Nesl Solartech","Chiconypower","Chilicon","Chilicon Power","Chint Power Systems America","Chint Solar Zhejiang","Concept by US","Connect Renewable Energy","Danfoss","Danfoss Solar","Darfon Electronics","DASS tech","Delta Energy Systems","Destin Power","Diehl AKO Stiftung","Diehl AKO Stiftung \u0026  KG","Direct Grid Technologies","Dow Chemical","DYNAPOWER COMPANY","E-Village Solar","EAST GROUP CO LTD","Eaton","Eguana Technologies","Elettronica Santerno","Eltek","Emerson Network Power","Enecsys","Energy Storage Australia Pty","EnluxSolar","Enphase Energy","Eoplly New Energy Technology","EPC Power","ET Solar Industry","ETM Electromatic","Exeltech","Flextronics Industrial","Flextronics International USA","Fronius","FSP Group","GAF","GE Energy","Gefran","Geoprotek","Global Mainstream Dynamic Energy Technology","Green Power Technologies","GreenVolts","GridPoint","Growatt","Gsmart Ningbo Energy Storage Technology Co","Guangzhou Sanjing Electric Co","Hangzhou Sunny Energy Science and Technology Co","Hansol Technics","Hanwha Q CELLS \u0026 Advanced Materials Corporation","Heart Transverter","Helios","HiQ Solar","HiSEL Power","Home Director","Hoymiles Converter Technology","Huawei Technologies","Huawei Technologies Co","HYOSUNG","i-Energy Corporation","Ideal Power","Ideal Power Converters","IMEON ENERGY","Ingeteam","Involar","INVOLAR","INVT Solar Technology Shenzhen Co","iPower","IST Energy","Jema Energy","Jiangsu GoodWe Power Supply Technology Co","Jiangsu Weiheng Intelligent Technology Co","Jiangsu Zeversolar New Energy","Jiangsu Zeversolar New Energy Co","Jiangyin Hareon Power","Jinko Solar","KACO","Kehua Hengsheng Co","Kostal Solar Electric","LeadSolar Energy","Leatec Fine Ceramics","LG Electronics","Lixma Tech","Mage Solar","Mage Solar USA","Mariah Power","MIL-Systems","Ming Shen Energy Technology","Mohr Power","Motech Industries","NeoVolta","Nextronex Energy Systems","Nidec ASI","Ningbo Ginlong Technologies","Ningbo Ginlong Technologies Co","Northern Electric","ONE SUN MEXICO  DE C.V.","Open Energy","OPTI International","OPTI-Solar","OutBack Power Technologies","Panasonic Corporation Eco Solutions Company","Perfect Galaxy","Petra Solar","Petra Systems","Phoenixtec Power","Phono Solar Technology","Pika Energy","Power Electronics","Power-One","Powercom","PowerWave Energy Pty","Princeton Power Systems","PurpleRubik New Energy Technology Co","PV Powered","Redback Technologies Limited","RedEarth Energy Storage Pty","REFU Elektronik","Renac Power Technology Co","Renergy","Renesola Zhejiang","Renovo Power Systems","Resonix","Rhombus Energy Solutions","Ritek Corporation","Sainty Solar","Samil Power","SanRex","SANYO","Sapphire Solar Pty","Satcon Technology","SatCon Technology","Schneider","Schneider Inverters USA","Schuco USA","Selectronic Australia","Senec GmbH","Shanghai Sermatec Energy Technology Co","Shanghai Trannergy Power Electronics Co","Sharp","Shenzhen BYD","Shenzhen Growatt","Shenzhen Growatt Co","Shenzhen INVT Electric Co","SHENZHEN KSTAR NEW ENERGY COMPANY LIMITED","Shenzhen Litto New Energy Co","Shenzhen Sinexcel Electric","Shenzhen Sinexcel Electric Co","Shenzhen SOFARSOLAR Co","Siemens Industry","Silicon Energy","Sineng Electric Co","SMA","Sol-Ark","Solar Juice Pty","Solar Liberty","Solar Power","Solarbine","SolarBridge Technologies","SolarCity","SolarEdge Technologies","Solargate","Solaria Corporation","Solarmax","SolarWorld","SolaX Power Co","SolaX Power Network Technology (Zhe jiang)","SolaX Power Network Technology Zhejiang Co","Solectria Renewables","Solis","Sonnen GmbH","Sonnetek","Southwest Windpower","Sparq Systems","Sputnik Engineering","STARFISH HERO CO","Sungrow Power Supply","Sungrow Power Supply Co","Sunna Tech","SunPower","SunPower  (Original Mfr.Fronius)","Sunset","Sustainable Energy Technologies","Sustainable Solar Services","Suzhou Hypontech Co","Suzhou Solarwii Micro Grid Technology Co","Sysgration","Tabuchi Electric","Talesun Solar","Tesla","The Trustee for Soltaro Unit Trust","TMEIC","TOPPER SUN Energy Tech","Toshiba International","Trannergy","Trina Energy Storage Solutions (Jiangsu)","Trina Energy Storage Solutions Jiangsu Co","Trina Solar Co","Ubiquiti Networks International","United Renewable Energy Co","Westinghouse Solar","Windterra Systems","Xantrex Technology","Xiamen Kehua Hengsheng","Xiamen Kehua Hengsheng Co","Xslent Energy Technologies","Yaskawa Solectria Solar","Yes! Solar","Zhongli Talesun Solar","ZIGOR","シャープ (Sharp)","パナソニック (Panasonic)","三菱電機 (Mitsubishi)","京セラ (Kyocera)","東芝 (Toshiba)","長州産業 (Choshu Sangyou)","ｶﾅﾃﾞｨｱﾝ  ｿｰﾗｰ"]')

        elif api == '/api/customer':
            data = json.loads('{"registered":true}')

        elif api == '/api/meters':
            data = json.loads('[{"serial":"VAH1234AB1234","short_id":"73533","type":"neurio_w2_tcp","connected":true,"cts":[{"type":"solarRGM","valid":[true,false,false,false],"inverted":[false,false,false,false],"real_power_scale_factor":2}],"ip_address":"PWRview-73533","mac":"01-23-45-56-78-90"},{"serial":"JBL12345Y1F012synchrometerY","short_id":"1232100-00-E--TG123456789EGG","type":"synchrometerY"},{"serial":"JBL12345Y1F012synchrometerX","short_id":"1232100-00-E--TG123456789EGG","type":"synchrometerX","cts":[{"type":"site","valid":[true,true,false,false],"inverted":[false,false,false,false]}]}]')

        elif api == '/api/installer':
            data = json.loads('{"company":"Tesla","customer_id":"","phone":"","email":"","location":"","mounting":"","wiring":"","backup_configuration":"Whole Home","solar_installation":"New","solar_installation_type":"PV Panel","run_sitemaster":true,"verified_config":true,"installation_types":["Residential"]}')

        elif api == '/api/networks':
            data = json.loads('[{"network_name":"ethernet_tesla_internal_default","interface":"EthType","enabled":true,"dhcp":true,"extra_ips":[{"ip":"192.168.90.2","netmask":24}],"active":true,"primary":true,"lastTeslaConnected":true,"lastInternetConnected":true,"iface_network_info":{"network_name":"ethernet_tesla_internal_default","ip_networks":[{"IP":"","Mask":"////AA=="}],"gateway":"","interface":"EthType","state":"DeviceStateReady","state_reason":"DeviceStateReasonNone","signal_strength":0,"hw_address":""}},{"network_name":"gsm_tesla_internal_default","interface":"GsmType","enabled":true,"dhcp":null,"active":true,"primary":false,"lastTeslaConnected":false,"lastInternetConnected":false,"iface_network_info":{"network_name":"gsm_tesla_internal_default","ip_networks":[{"IP":"","Mask":"/////w=="}],"gateway":"","interface":"GsmType","state":"DeviceStateReady","state_reason":"DeviceStateReasonNone","signal_strength":71,"hw_address":""}}]')

        elif api == '/api/system/networks':
            data = "TIMEOUT!"

        elif api == '/api/meters/readings':
            data = "TIMEOUT!"

        elif api == '/api/synchrometer/ct_voltage_references':
            data = json.loads('{"ct1":"Phase1","ct2":"Phase2","ct3":"Phase1"}')

        elif api == '/api/troubleshooting/problems':
            data = json.loads('{"problems":[]}')

        else:
            data = {"ERROR": f"Unknown API: {api}"}

        self.pwcache[api] = data
        self.pwcachetime[api] = time.time()
        return data
    
    def getsites(self):
        """
        Get list of Tesla Energy sites
        """
        if self.tesla is None:
            return None
        try:
            sitelist = self.tesla.battery_list() + self.tesla.solar_list()
        except Exception as err:
            log.error(f"ERROR: Failed to retrieve sitelist - {repr(err)}")
            return None
        return sitelist
    
    def setup(self):
        """
        Set up the Tesla Cloud connection
        """
        print("\nTesla Account Setup")
        print("-" * 19)

        while True:
            response = input("Email address: ").strip()
            if "@" not in response:
                print("Invalid email address\n")
            else:
                TUSER = response
                break

        # Update the Tesla User
        self.email = TUSER

        # Create retry instance for use after successful login
        retry = Retry(total=2, status_forcelist=(500, 502, 503, 504), backoff_factor=10)

        # Create Tesla instance
        tesla = Tesla(self.email, cache_file=AUTHFILE)

        if not tesla.authorized:
            # Login to Tesla account and cache token
            state = tesla.new_state()
            code_verifier = tesla.new_code_verifier()

            try:
                print("Open the below address in your browser to login.\n")
                print(tesla.authorization_url(state=state, code_verifier=code_verifier))
            except Exception as err:
                log.error(f"ERROR: Connection failure - {repr(err)}")

            print("\nAfter login, paste the URL of the 'Page Not Found' webpage below.\n")

            tesla.close()
            tesla = Tesla(self.email, retry=retry, state=state, code_verifier=code_verifier, cache_file=AUTHFILE)

            if not tesla.authorized:
                try:
                    tesla.fetch_token(authorization_response=input("Enter URL after login: "))
                    print("-" * 40)
                except Exception as err:
                    sys_exit(f"ERROR: Login failure - {repr(err)}")
        else:
            # Enable retries
            tesla.close()
            tesla = Tesla(self.email, retry=retry, cache_file=AUTHFILE)

if __name__ == "__main__":

    # Test code
    set_debug(False)
    # Check for .pypowerwall.auth file
    if os.path.isfile(AUTHFILE):
        # Read the json file
        with open(AUTHFILE) as json_file:
            try:
                data = json.load(json_file)
                TUSER = list(data.keys())[0]
                print(f"Using Tesla User: {TUSER}")
            except Exception as err:
                TUSER = None

    while not TUSER:
        response = input("Tesla User Email address: ").strip()
        if "@" not in response:
            print("Invalid email address\n")
        else:
            TUSER = response
            break

    cloud = TeslaCloud(TUSER)

    if not cloud.connect():
        print("Failed to connect to Tesla Cloud")
        cloud.setup()
        if not cloud.connect():
            print("Failed to connect to Tesla Cloud")
            exit(1)

    print("Connected to Tesla Cloud")   

    #print("\nSite Data")
    #sites = cloud.getsites()
    #print(sites)

    #print("\Battery")
    #r = cloud.get_battery()
    #print(r)

    #print("\Site Power")
    #r = cloud.get_site_power()
    #print(r)

    #print("\Site Config")
    #r = cloud.get_site_config()
    #print(r)

    # Test Poll
    items = ['/api/status','/api/system_status/grid_status','/api/site_info/site_name','/api/devices/vitals','/api/system_status/soe','/api/meters/aggregates','/api/operation','/api/system_status'] #, '/api/logout','/api/login/Basic','/vitals','/api/meters/site','/api/meters/solar','/api/sitemaster','/api/powerwalls','/api/installer','/api/customer/registration','/api/system/update/status','/api/site_info','/api/system_status/grid_faults','/api/site_info/grid_codes','/api/solars','/api/solars/brands','/api/customer','/api/meters','/api/installer','/api/networks','/api/system/networks','/api/meters/readings','/api/synchrometer/ct_voltage_references']
    for i in items:
        print(f"poll({i}):")
        print(cloud.poll(i))
        print("\n")

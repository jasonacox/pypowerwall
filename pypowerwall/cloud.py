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
try:
    from teslapy import Tesla, Retry, JsonDict, Battery, SolarPanel
except:
    sys.exit("ERROR: Missing python teslapy module. Run 'pip install teslapy'.")
import pypowerwall
import logging
import json

AUTHFILE = f"pypowerwall.auth"
ALLOWLIST = [
    '/api/status', '/api/site_info/site_name', '/api/meters/site',
    '/api/meters/solar', '/api/sitemaster', '/api/powerwalls', 
    '/api/customer/registration', '/api/system_status', '/api/system_status/grid_status',
    '/api/system/update/status', '/api/site_info', '/api/system_status/grid_faults',
    '/api/operation', '/api/site_info/grid_codes', '/api/solars', '/api/solars/brands',
    '/api/customer', '/api/meters', '/api/installer', '/api/networks', 
    '/api/system/networks', '/api/meters/readings', '/api/synchrometer/ct_voltage_references',
    '/api/troubleshooting/problems', '/api/auth/toggle/supported'
    ]

version_tuple = pypowerwall.version_tuple
version = __version__ = '%d.%d.%d' % version_tuple
__author__ = pypowerwall.__author__

log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

def lookup(data, keylist):
    """
    Search data for list of keys and return the first matching key's value if found, otherwise return None
    """
    for key in keylist:
        if key in data:
            return data[key]
    return None

class TeslaCloud:
    def __init__(self, email, pwcacheexpire=5, timeout=10):
        self.email = email
        self.timeout = timeout
        self.site = None
        self.tesla = None   
        self.retry = None
        self.pwcachetime = {}                   # holds the cached data timestamps for api
        self.pwcache = {}                       # holds the cached data for api
        self.pwcacheexpire = pwcacheexpire      # seconds to expire cache 
        
        # Create retry instance for use after successful login
        self.retry = Retry(total=2, status_forcelist=(500, 502, 503, 504), backoff_factor=10)

        # Create Tesla instance
        self.tesla = Tesla(email, cache_file=AUTHFILE)

        if not self.tesla.authorized:
            # Login to Tesla account and cache token
            state = self.tesla.new_state()
            code_verifier = self.tesla.new_code_verifier()

            try:
                self.tesla.fetch_token(authorization_response=self.tesla.authorization_url(state=state, code_verifier=code_verifier))
            except Exception as err:
                log.error(f"ERROR: Login failure - {repr(err)}")
        else:
            # Enable retries
            self.tesla.close()
            self.tesla = Tesla(email, retry=self.retry, cache_file=AUTHFILE)

    def poll(self, api):
        """
        Poll the Tesla Cloud API to get data for the API request

        TODO: Make this work - placeholders only
        """
        if self.tesla is None:
            return None
        # Check to see if we have cached data
        if api in self.pwcache:
            if self.pwcachetime[api] > time.time() - self.pwcacheexpire:
                return self.pwcache[api]
        else:
            # Determine what data we need based on Powerwall APIs (ALLOWLIST)
            # TODO: Consider making this a map?

            ## Variable
            if api == '/api/status':
                data = {
                    "din": "1232100-00-E--TG1234567890G1",
                    "start_time": "2023-10-13 04:01:45 +0800",
                    "up_time_seconds": "1541h38m20.998412744s",
                    "is_new": False,
                    "version": "23.28.2 27626f98", # firmware version
                    "git_hash": "27626f98a66cad5c665bbe1d4d788cdb3e94fd33",
                    "commission_count": 0,
                    "device_type": "teg",
                    "teg_type": "unknown",
                    "sync_type": "v2.1",
                    "cellular_disabled": False,
                    "can_reboot": True
                }
            elif api == '/api/system_status/grid_status':
                data = {
                    "grid_status":"SystemGridConnected", # SystemIslandedActive or SystemTransitionToGrid
                    "grid_services_active":False
                }

            elif api == '/api/site_info/site_name':
                data = {
                    "max_system_energy_kWh": 27,
                    "max_system_power_kW": 10.8,
                    "site_name": "Tesla Energy Gateway",
                    "timezone": "America/Los_Angeles",
                    "max_site_meter_power_kW": 1000000000,
                    "min_site_meter_power_kW": -1000000000,
                    "nominal_system_energy_kWh": 27,
                    "nominal_system_power_kW": 10.8,
                    "panel_max_current": 100,
                    "grid_code": {
                        "grid_code": "60Hz_240V_s_UL1741SA:2019_California",
                        "grid_voltage_setting": 240,
                        "grid_freq_setting": 60,
                        "grid_phase_setting": "Split",
                        "country": "United States",
                        "state": "California",
                        "utility": "Southern California Edison"
                    }
                }
            elif api == '/api/devices/vitals':
                # Protobuf payload - not implemented - use /vitals instead
                data = None 
            elif api == '/api/system_status/soe':
                data = {"percentage": 20.52609259375742}
            elif api == '/api/meters/aggregates':
                data = {
                    "site": {
                        "last_communication_time": "2023-12-17T08:56:25.338327717-08:00",
                        "instant_power": 10,
                        "instant_reactive_power": -157,
                        "instant_apparent_power": 157.31814898478814,
                        "frequency": 0,
                        "energy_exported": 4324306.770189472,
                        "energy_imported": 6818833.341005325,
                        "instant_average_voltage": 210.88584607554864,
                        "instant_average_current": 5.4485,
                        "i_a_current": 0,
                        "i_b_current": 0,
                        "i_c_current": 0,
                        "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                        "timeout": 1500000000,
                        "num_meters_aggregated": 1,
                        "instant_total_current": 5.4485
                    },
                    "battery": {
                        "last_communication_time": "2023-12-17T08:56:25.323519663-08:00",
                        "instant_power": -450,
                        "instant_reactive_power": 0,
                        "instant_apparent_power": 450,
                        "frequency": 60.031,
                        "energy_exported": 12334715,
                        "energy_imported": 13870768,
                        "instant_average_voltage": 243.70000000000002,
                        "instant_average_current": 9.5,
                        "i_a_current": 0,
                        "i_b_current": 0,
                        "i_c_current": 0,
                        "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                        "timeout": 1500000000,
                        "num_meters_aggregated": 2,
                        "instant_total_current": 9.5
                    },
                    "load": {
                        "last_communication_time": "2023-12-17T08:56:25.323519663-08:00",
                        "instant_power": 919,
                        "instant_reactive_power": -117,
                        "instant_apparent_power": 926.4178322981483,
                        "frequency": 0,
                        "energy_exported": 0,
                        "energy_imported": 27318851.570815854,
                        "instant_average_voltage": 210.88584607554864,
                        "instant_average_current": 4.357807871424304,
                        "i_a_current": 0,
                        "i_b_current": 0,
                        "i_c_current": 0,
                        "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                        "timeout": 1500000000,
                        "instant_total_current": 4.357807871424304
                    },
                    "solar": {
                        "last_communication_time": "2023-12-17T08:56:25.378490115-08:00",
                        "instant_power": 1360,
                        "instant_reactive_power": 50,
                        "instant_apparent_power": 1360.9188072769073,
                        "frequency": 60.028,
                        "energy_exported": 26360378,
                        "energy_imported": 0,
                        "instant_average_voltage": 243.15,
                        "instant_average_current": 5.592105263157895,
                        "i_a_current": 0,
                        "i_b_current": 0,
                        "i_c_current": 0,
                        "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
                        "last_phase_energy_communication_time": "0001-01-01T00:00:00Z",
                        "timeout": 1000000000,
                        "num_meters_aggregated": 1,
                        "instant_total_current": 5.592105263157895
                    }
                }
            elif api == '/api/operation':
                data = {
                    "real_mode": "self_consumption",
                    "backup_reserve_percent": 81,
                    "freq_shift_load_shed_soe": 65,
                    "freq_shift_load_shed_delta_f": -0.32
                }
            elif api == '/api/system_status':
                data = {
                    "command_source": "Configuration",
                    "battery_target_power": -3866.6666666666665,
                    "battery_target_reactive_power": 0,
                    "nominal_full_pack_energy": 25995,
                    "nominal_energy_remaining": 16693,
                    "max_power_energy_remaining": 0,
                    "max_power_energy_to_be_charged": 0,
                    "max_charge_power": 10800,
                    "max_discharge_power": 10800,
                    "max_apparent_power": 10800,
                    "instantaneous_max_discharge_power": 24000,
                    "instantaneous_max_charge_power": 14000,
                    "instantaneous_max_apparent_power": 11520,
                    "hardware_capability_charge_power": 0,
                    "hardware_capability_discharge_power": 0,
                    "grid_services_power": -0,
                    "system_island_state": "SystemGridConnected",
                    "available_blocks": 2,
                    "available_charger_blocks": 0,
                    "battery_blocks": [
                        {
                            "Type": "",
                            "PackagePartNumber": "2012170-25-E",
                            "PackageSerialNumber": "TG123456789012",
                            "disabled_reasons": [],
                            "pinv_state": "PINV_GridFollowing",
                            "pinv_grid_state": "Grid_Compliant",
                            "nominal_energy_remaining": 8528,
                            "nominal_full_pack_energy": 13305,
                            "p_out": -1990,
                            "q_out": 20,
                            "v_out": 243.70000000000002,
                            "f_out": 60.007999999999996,
                            "i_out": 40.900000000000006,
                            "energy_charged": 7036162,
                            "energy_discharged": 6249327,
                            "off_grid": False,
                            "vf_mode": False,
                            "wobble_detected": False,
                            "charge_power_clamped": False,
                            "backup_ready": True,
                            "OpSeqState": "Active",
                            "version": "27626f98a66cad"
                        },
                        {
                            "Type": "",
                            "PackagePartNumber": "3012170-05-B",
                            "PackageSerialNumber": "TG123456789012",
                            "disabled_reasons": [],
                            "pinv_state": "PINV_GridFollowing",
                            "pinv_grid_state": "Grid_Compliant",
                            "nominal_energy_remaining": 8165,
                            "nominal_full_pack_energy": 12690,
                            "p_out": -1890.0000000000002,
                            "q_out": 20,
                            "v_out": 243.70000000000002,
                            "f_out": 60.007999999999996,
                            "i_out": 39.400000000000006,
                            "energy_charged": 6835113,
                            "energy_discharged": 6076726,
                            "off_grid": False,
                            "vf_mode": False,
                            "wobble_detected": False,
                            "charge_power_clamped": False,
                            "backup_ready": True,
                            "OpSeqState": "Active",
                            "version": "27626f98a66cad"
                        }
                    ],
                    "ffr_power_availability_high": 11600,
                    "ffr_power_availability_low": 11600,
                    "load_charge_constraint": 0,
                    "max_sustained_ramp_rate": 2700000,
                    "grid_faults": [],
                    "can_reboot": "Yes",
                    "smart_inv_delta_p": 0,
                    "smart_inv_delta_q": 0,
                    "last_toggle_timestamp": "2023-10-13T04:08:05.957195-07:00",
                    "solar_real_power_limit": 3909.4999669342515,
                    "score": 10000,
                    "blocks_controlled": 2,
                    "primary": True,
                    "auxiliary_load": 0,
                    "all_enable_lines_high": True,
                    "inverter_nominal_usable_power": 11600,
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

            elif api == '/api/sitemaster':
                data = json.loads('{"status":"StatusUp","running":true,"connected_to_tesla":true,"power_supply_mode":false,"can_reboot":"Yes"}')
            
            elif api == '/api/powerwalls':
                data = json.loads('{"enumerating":false,"updating":false,"checking_if_offgrid":false,"running_phase_detection":false,"phase_detection_last_error":"no phase information","bubble_shedding":false,"on_grid_check_error":"on grid check not run","grid_qualifying":false,"grid_code_validating":false,"phase_detection_not_available":true,"powerwalls":[{"Type":"","PackagePartNumber":"2012170-25-E","PackageSerialNumber":"TG1234567890G1","type":"SolarPowerwall","grid_state":"Grid_Uncompliant","grid_reconnection_time_seconds":0,"under_phase_detection":false,"updating":false,"commissioning_diagnostic":{"name":"Commissioning","category":"InternalComms","disruptive":false,"inputs":null,"checks":[{"name":"CAN connectivity","status":"fail","start_time":"2023-12-16T08:34:17.3068631-08:00","end_time":"2023-12-16T08:34:17.3068696-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Enable switch","status":"fail","start_time":"2023-12-16T08:34:17.306875474-08:00","end_time":"2023-12-16T08:34:17.306880724-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Internal communications","status":"fail","start_time":"2023-12-16T08:34:17.306886099-08:00","end_time":"2023-12-16T08:34:17.306891223-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Firmware up-to-date","status":"fail","start_time":"2023-12-16T08:34:17.306896598-08:00","end_time":"2023-12-16T08:34:17.306901723-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null}],"alert":false},"update_diagnostic":{"name":"Firmware Update","category":"InternalComms","disruptive":true,"inputs":null,"checks":[{"name":"Solar Inverter firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Solar Safety firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Grid code","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Powerwall firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Battery firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Inverter firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Grid code","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null}],"alert":false},"bc_type":null,"in_config":true},{"Type":"","PackagePartNumber":"3012170-05-B","PackageSerialNumber":"TG1234567890G1","type":"ACPW","grid_state":"Grid_Uncompliant","grid_reconnection_time_seconds":0,"under_phase_detection":false,"updating":false,"commissioning_diagnostic":{"name":"Commissioning","category":"InternalComms","disruptive":false,"inputs":null,"checks":[{"name":"CAN connectivity","status":"fail","start_time":"2023-12-16T08:34:17.320856307-08:00","end_time":"2023-12-16T08:34:17.320940302-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Enable switch","status":"fail","start_time":"2023-12-16T08:34:17.320949301-08:00","end_time":"2023-12-16T08:34:17.320955301-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Internal communications","status":"fail","start_time":"2023-12-16T08:34:17.320960676-08:00","end_time":"2023-12-16T08:34:17.320966176-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Firmware up-to-date","status":"fail","start_time":"2023-12-16T08:34:17.32097155-08:00","end_time":"2023-12-16T08:34:17.3209768-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null}],"alert":false},"update_diagnostic":{"name":"Firmware Update","category":"InternalComms","disruptive":true,"inputs":null,"checks":[{"name":"Powerwall firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Battery firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Inverter firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Grid code","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null}],"alert":false},"bc_type":null,"in_config":true}],"gateway_din":"1232100-00-E--TG1234567890G1","sync":{"updating":false,"commissioning_diagnostic":{"name":"Commissioning","category":"InternalComms","disruptive":false,"inputs":null,"checks":[{"name":"CAN connectivity","status":"fail","start_time":"2023-12-16T08:34:17.321101293-08:00","end_time":"2023-12-16T08:34:17.321107918-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null},{"name":"Firmware up-to-date","status":"fail","start_time":"2023-12-16T08:34:17.321113792-08:00","end_time":"2023-12-16T08:34:17.321118917-08:00","message":"Cannot perform this action with site controller running. From landing page, either \"STOP SYSTEM\" or \"RUN WIZARD\" to proceed.","results":{},"debug":{},"checks":null}],"alert":false},"update_diagnostic":{"name":"Firmware Update","category":"InternalComms","disruptive":true,"inputs":null,"checks":[{"name":"Synchronizer firmware","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Islanding configuration","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null},{"name":"Grid code","status":"not_run","start_time":null,"end_time":null,"progress":0,"results":null,"debug":null,"checks":null}],"alert":false}},"msa":null,"states":null}')
            
            elif api == '/api/customer/registration':
                data = json.loads('{"privacy_notice":null,"limited_warranty":null,"grid_services":null,"marketing":null,"registered":true,"timed_out_registration":false}')
            
            elif api == '/api/system/update/status':
                data = json.loads('{"state":"/update_succeeded","info":{"status":["nonactionable"]},"current_time":1702756114429,"last_status_time":1702753309227,"version":"23.28.2 27626f98","offline_updating":false,"offline_update_error":"","estimated_bytes_per_second":null}')

            elif api == '/api/site_info':
                data = json.loads('{"max_system_energy_kWh":27,"max_system_power_kW":10.8,"site_name":"Tesla Energy Gateway","timezone":"America/Los_Angeles","max_site_meter_power_kW":1000000000,"min_site_meter_power_kW":-1000000000,"nominal_system_energy_kWh":27,"nominal_system_power_kW":10.8,"panel_max_current":100,"grid_code":{"grid_code":"60Hz_240V_s_UL1741SA:2019_California","grid_voltage_setting":240,"grid_freq_setting":60,"grid_phase_setting":"Split","country":"United States","state":"California","utility":"Southern California Edison"}}')

            elif api == '/api/system_status/grid_faults':
                data = json.loads('[]')

            elif api == '/api/site_info/grid_codes':
                data = json.loads('"TIMEOUT!"')

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
                data = json.loads('"TIMEOUT!"')

            elif api == '/api/meters/readings':
                data = json.loads('"TIMEOUT!"')

            elif api == '/api/synchrometer/ct_voltage_references':
                data = json.loads('{"ct1":"Phase1","ct2":"Phase2","ct3":"Phase1"}')
                
        return data
    
    def getsites(self):
        """
        Get list of Tesla Energy sites

        TODO: Make this work
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

        TODO: Make this work
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


# TODO: Test code
# pyPowerWall - Tesla TEDAPI Class
# -*- coding: utf-8 -*-
"""
 Tesla TEADAPI Class
 
 This module allows you to access the Tesla Powerwall Gateway 
 TEDAPI on 192.168.91.1 as used by the Tesla One app.

 Class:
    TEDAPI(gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
              pwconfigexpire: int = 300, host: str = GW_IP) - Initialize TEDAPI
    
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

# Imports

import logging
import math
import sys
import time
import json
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from pypowerwall import __version__
from . import tedapi_pb2
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# TEDAPI Fixed Gateway IP Address
GW_IP = "192.168.91.1"

# Rate Limit Codes
BUSY_CODES = [429, 503]

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

# TEDAPI Class
class TEDAPI:
    def __init__(self, gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
                 pwconfigexpire: int = 300, host: str = GW_IP) -> None:
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
        self.apilock = {} # holds the api lock status
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

    def get_din(self, force=False):
        """
        Get the DIN from the Powerwall Gateway
        """
        # Check Cache
        if not force and "din" in self.pwcachetime:
            if time.time() - self.pwcachetime["din"] < self.pwcacheexpire:
                log.debug("Using Cached DIN")
                return self.pwcache["din"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Fetch DIN from Powerwall
        log.debug("Fetching DIN from Powerwall...")
        url = f'https://{self.gw_ip}/tedapi/din'
        r = requests.get(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False, timeout=self.timeout)
        if r.status_code in BUSY_CODES:
            # Rate limited - Switch to cooldown mode for 5 minutes
            self.pwcooldown = time.perf_counter() + 300
            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
            return None
        if r.status_code == 403:
            log.error("Access Denied: Check your Gateway Password")
            return None
        if r.status_code != 200:
            log.error(f"Error fetching DIN: {r.status_code}")
            return None
        din = r.text
        log.debug(f"Connected: Powerwall Gateway DIN: {din}")
        self.pwcachetime["din"] = time.time()
        self.pwcache["din"] = din
        return din

    def get_config(self,force=False):
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
        # Check for lock and wait if api request already sent
        if 'config' in self.apilock:
            locktime = time.perf_counter()
            while self.apilock['config']:
                time.sleep(0.2)
                if time.perf_counter() >= locktime + self.timeout:
                    log.debug(" -- tedapi: Timeout waiting for config (unable to acquire lock)")
                    return None
        # Check Cache
        if not force and "config" in self.pwcachetime:
            if time.time() - self.pwcachetime["config"] < self.pwconfigexpire:
                log.debug("Using Cached Payload")
                return self.pwcache["config"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get configuration")
                return None
        # Fetch Configuration from Powerwall
        log.debug("Get Configuration from Powerwall")
        # Build Protobuf to fetch config
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.config.send.num = 1
        pb.message.config.send.file = "config.json"
        pb.tail.value = 1
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            # Set lock
            self.apilock['config'] = True
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                          headers={'Content-type': 'application/octet-string'},
                                          data=pb.SerializeToString(), timeout=self.timeout)
            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                self.apilock['config'] = False
                return None
            if r.status_code != 200:
                log.error(f"Error fetching config: {r.status_code}")
                self.apilock['config'] = False
                return None
            # Decode response
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(r.content)
            payload = tedapi.message.config.recv.file.text
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                log.error(f"Error Decoding JSON: {e}")
                data = {}
            log.debug(f"Configuration: {data}")
            self.pwcachetime["config"] = time.time()
            self.pwcache["config"] = data
        except Exception as e:
            log.error(f"Error fetching config: {e}")
            data = None
        finally:
            # Release lock
            self.apilock['config'] = False
        return data

    def get_status(self, force=False):
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
        # Check for lock and wait if api request already sent
        if 'status' in self.apilock:
            locktime = time.perf_counter()
            while self.apilock['status']:
                time.sleep(0.2)
                if time.perf_counter() >= locktime + self.timeout:
                    log.debug(" -- tedapi: Timeout waiting for status (unable to acquire lock)")
                    return None
        # Check Cache
        if not force and "status" in self.pwcachetime:
            if time.time() - self.pwcachetime["status"] < self.pwcacheexpire:
                log.debug("Using Cached Payload")
                return self.pwcache["status"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get status")
                return None
        # Fetch Current Status from Powerwall
        log.debug("Get Status from Powerwall")
        # Build Protobuf to fetch status
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = " query DeviceControllerQuery {\n  control {\n    systemStatus {\n        nominalFullPackEnergyWh\n        nominalEnergyRemainingWh\n    }\n    islanding {\n        customerIslandMode\n        contactorClosed\n        microGridOK\n        gridOK\n    }\n    meterAggregates {\n      location\n      realPowerW\n    }\n    alerts {\n      active\n    },\n    siteShutdown {\n      isShutDown\n      reasons\n    }\n    batteryBlocks {\n      din\n      disableReasons\n    }\n    pvInverters {\n      din\n      disableReasons\n    }\n  }\n  system {\n    time\n    sitemanagerStatus {\n      isRunning\n    }\n    updateUrgencyCheck  {\n      urgency\n      version {\n        version\n        gitHash\n      }\n      timestamp\n    }\n  }\n  neurio {\n    isDetectingWiredMeters\n    readings {\n      serial\n      dataRead {\n        voltageV\n        realPowerW\n        reactivePowerVAR\n        currentA\n      }\n      timestamp\n    }\n    pairings {\n      serial\n      shortId\n      status\n      errors\n      macAddress\n      isWired\n      modbusPort\n      modbusId\n      lastUpdateTimestamp\n    }\n  }\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  esCan {\n    bus {\n      PVAC {\n        packagePartNumber\n        packageSerialNumber\n        subPackagePartNumber\n        subPackageSerialNumber\n        PVAC_Status {\n          isMIA\n          PVAC_Pout\n          PVAC_State\n          PVAC_Vout\n          PVAC_Fout\n        }\n        PVAC_InfoMsg {\n          PVAC_appGitHash\n        }\n        PVAC_Logging {\n          isMIA\n          PVAC_PVCurrent_A\n          PVAC_PVCurrent_B\n          PVAC_PVCurrent_C\n          PVAC_PVCurrent_D\n          PVAC_PVMeasuredVoltage_A\n          PVAC_PVMeasuredVoltage_B\n          PVAC_PVMeasuredVoltage_C\n          PVAC_PVMeasuredVoltage_D\n          PVAC_VL1Ground\n          PVAC_VL2Ground\n        }\n        alerts {\n          isComplete\n          isMIA\n          active\n        }\n      }\n      PINV {\n        PINV_Status {\n          isMIA\n          PINV_Fout\n          PINV_Pout\n          PINV_Vout\n          PINV_State\n          PINV_GridState\n        }\n        PINV_AcMeasurements {\n          isMIA\n          PINV_VSplit1\n          PINV_VSplit2\n        }\n        PINV_PowerCapability {\n          isComplete\n          isMIA\n          PINV_Pnom\n        }\n        alerts {\n          isComplete\n          isMIA\n          active\n        }\n      }\n      PVS {\n        PVS_Status {\n          isMIA\n          PVS_State\n          PVS_vLL\n          PVS_StringA_Connected\n          PVS_StringB_Connected\n          PVS_StringC_Connected\n          PVS_StringD_Connected\n          PVS_SelfTestState\n        }\n        alerts {\n          isComplete\n          isMIA\n          active\n        }\n      }\n      THC {\n        packagePartNumber\n        packageSerialNumber\n        THC_InfoMsg {\n          isComplete\n          isMIA\n          THC_appGitHash\n        }\n        THC_Logging {\n          THC_LOG_PW_2_0_EnableLineState\n        }\n      }\n      POD {\n        POD_EnergyStatus {\n          isMIA\n          POD_nom_energy_remaining\n          POD_nom_full_pack_energy\n        }\n        POD_InfoMsg {\n            POD_appGitHash\n        }\n      }\n      MSA {\n        packagePartNumber\n        packageSerialNumber\n        MSA_InfoMsg {\n          isMIA\n          MSA_appGitHash\n          MSA_assemblyId\n        }\n        METER_Z_AcMeasurements {\n          isMIA\n          lastRxTime\n          METER_Z_CTA_InstRealPower\n          METER_Z_CTA_InstReactivePower\n          METER_Z_CTA_I\n          METER_Z_VL1G\n          METER_Z_CTB_InstRealPower\n          METER_Z_CTB_InstReactivePower\n          METER_Z_CTB_I\n          METER_Z_VL2G\n        }\n        MSA_Status {\n          lastRxTime\n        }\n      }\n      SYNC {\n        packagePartNumber\n        packageSerialNumber\n        SYNC_InfoMsg {\n          isMIA\n          SYNC_appGitHash\n        }\n        METER_X_AcMeasurements {\n          isMIA\n          isComplete\n          lastRxTime\n          METER_X_CTA_InstRealPower\n          METER_X_CTA_InstReactivePower\n          METER_X_CTA_I\n          METER_X_VL1N\n          METER_X_CTB_InstRealPower\n          METER_X_CTB_InstReactivePower\n          METER_X_CTB_I\n          METER_X_VL2N\n          METER_X_CTC_InstRealPower\n          METER_X_CTC_InstReactivePower\n          METER_X_CTC_I\n          METER_X_VL3N\n        }\n        METER_Y_AcMeasurements {\n          isMIA\n          isComplete\n          lastRxTime\n          METER_Y_CTA_InstRealPower\n          METER_Y_CTA_InstReactivePower\n          METER_Y_CTA_I\n          METER_Y_VL1N\n          METER_Y_CTB_InstRealPower\n          METER_Y_CTB_InstReactivePower\n          METER_Y_CTB_I\n          METER_Y_VL2N\n          METER_Y_CTC_InstRealPower\n          METER_Y_CTC_InstReactivePower\n          METER_Y_CTC_I\n          METER_Y_VL3N\n        }\n        SYNC_Status {\n          lastRxTime\n        }\n      }\n      ISLANDER {\n        ISLAND_GridConnection {\n          ISLAND_GridConnected\n          isComplete\n        }\n        ISLAND_AcMeasurements {\n          ISLAND_VL1N_Main\n          ISLAND_FreqL1_Main\n          ISLAND_VL2N_Main\n          ISLAND_FreqL2_Main\n          ISLAND_VL3N_Main\n          ISLAND_FreqL3_Main\n          ISLAND_VL1N_Load\n          ISLAND_FreqL1_Load\n          ISLAND_VL2N_Load\n          ISLAND_FreqL2_Load\n          ISLAND_VL3N_Load\n          ISLAND_FreqL3_Load\n          ISLAND_GridState\n          lastRxTime\n          isComplete\n          isMIA\n        }\n      }\n    }\n    enumeration {\n      inProgress\n      numACPW\n      numPVI\n    }\n    firmwareUpdate {\n      isUpdating\n      powerwalls {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n      msa {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n      sync {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n      pvInverters {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n    }\n    phaseDetection {\n      inProgress\n      lastUpdateTimestamp\n      powerwalls {\n        din\n        progress\n        phase\n      }\n    }\n    inverterSelfTests {\n      isRunning\n      isCanceled\n      pinvSelfTestsResults {\n        din\n        overall {\n          status\n          test\n          summary\n          setMagnitude\n          setTime\n          tripMagnitude\n          tripTime\n          accuracyMagnitude\n          accuracyTime\n          currentMagnitude\n          timestamp\n          lastError\n        }\n        testResults {\n          status\n          test\n          summary\n          setMagnitude\n          setTime\n          tripMagnitude\n          tripTime\n          accuracyMagnitude\n          accuracyTime\n          currentMagnitude\n          timestamp\n          lastError\n        }\n      }\n    }\n  }\n}\n"
        pb.message.payload.send.code = b'0\201\206\002A\024\261\227\245\177\255\265\272\321r\032\250\275j\305\030\2300\266\022B\242\264pO\262\024vd\267\316\032\f\376\322V\001\f\177*\366\345\333g_/`\v\026\225_qc\023$\323\216y\276~\335A1\022x\002Ap\a_\264\037]\304>\362\356\005\245V\301\177*\b\307\016\246]\037\202\242\353I~\332\317\021\336\006\033q\317\311\264\315\374\036\365s\272\225\215#o!\315z\353\345z\226\365\341\f\265\256r\373\313/\027\037'
        pb.message.payload.send.b.value = "{}"
        pb.tail.value = 1
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            # Set lock
            self.apilock['status'] = True
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                          headers={'Content-type': 'application/octet-string'},
                                          data=pb.SerializeToString(), timeout=self.timeout)
            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                self.apilock['status'] = False
                return None
            if r.status_code != 200:
                log.error(f"Error fetching status: {r.status_code}")
                self.apilock['status'] = False
                return None
            # Decode response
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(r.content)
            payload = tedapi.message.payload.recv.text
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                log.error(f"Error Decoding JSON: {e}")
                data = {}
            log.debug(f"Status: {data}")
            self.pwcachetime["status"] = time.time()
            self.pwcache["status"] = data
        except Exception as e:
            log.error(f"Error fetching status: {e}")
            data = None
        finally:
            # Release lock
            self.apilock['status'] = False
        return data

    def get_device_controller(self, force=False):
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
        # Check for lock and wait if api request already sent
        if 'controller' in self.apilock:
            locktime = time.perf_counter()
            while self.apilock['controller']:
                time.sleep(0.2)
                if time.perf_counter() >= locktime + self.timeout:
                    log.debug(" -- tedapi: Timeout waiting for controller data (unable to acquire lock)")
                    return None
        # Check Cache
        if not force and "controller" in self.pwcachetime:
            if time.time() - self.pwcachetime["controller"] < self.pwcacheexpire:
                log.debug("Using Cached Payload")
                return self.pwcache["controller"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get controller data")
                return None
        # Fetch Current Status from Powerwall
        log.debug("Get controller data from Powerwall")
        # Build Protobuf to fetch controller data
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = 'query DeviceControllerQuery($msaComp:ComponentFilter$msaSignals:[String!]){control{systemStatus{nominalFullPackEnergyWh nominalEnergyRemainingWh}islanding{customerIslandMode contactorClosed microGridOK gridOK disableReasons}meterAggregates{location realPowerW}alerts{active}siteShutdown{isShutDown reasons}batteryBlocks{din disableReasons}pvInverters{din disableReasons}}system{time supportMode{remoteService{isEnabled expiryTime sessionId}}sitemanagerStatus{isRunning}updateUrgencyCheck{urgency version{version gitHash}timestamp}}neurio{isDetectingWiredMeters readings{firmwareVersion serial dataRead{voltageV realPowerW reactivePowerVAR currentA}timestamp}pairings{serial shortId status errors macAddress hostname isWired modbusPort modbusId lastUpdateTimestamp}}teslaRemoteMeter{meters{din reading{timestamp firmwareVersion ctReadings{voltageV realPowerW reactivePowerVAR energyExportedWs energyImportedWs currentA}}firmwareUpdate{updating numSteps currentStep currentStepProgress progress}}detectedWired{din serialPort}}pw3Can{firmwareUpdate{isUpdating progress{updating numSteps currentStep currentStepProgress progress}}enumeration{inProgress}}esCan{bus{PVAC{packagePartNumber packageSerialNumber subPackagePartNumber subPackageSerialNumber PVAC_Status{isMIA PVAC_Pout PVAC_State PVAC_Vout PVAC_Fout}PVAC_InfoMsg{PVAC_appGitHash}PVAC_Logging{isMIA PVAC_PVCurrent_A PVAC_PVCurrent_B PVAC_PVCurrent_C PVAC_PVCurrent_D PVAC_PVMeasuredVoltage_A PVAC_PVMeasuredVoltage_B PVAC_PVMeasuredVoltage_C PVAC_PVMeasuredVoltage_D PVAC_VL1Ground PVAC_VL2Ground}alerts{isComplete isMIA active}}PINV{PINV_Status{isMIA PINV_Fout PINV_Pout PINV_Vout PINV_State PINV_GridState}PINV_AcMeasurements{isMIA PINV_VSplit1 PINV_VSplit2}PINV_PowerCapability{isComplete isMIA PINV_Pnom}alerts{isComplete isMIA active}}PVS{PVS_Status{isMIA PVS_State PVS_vLL PVS_StringA_Connected PVS_StringB_Connected PVS_StringC_Connected PVS_StringD_Connected PVS_SelfTestState}PVS_Logging{PVS_numStringsLockoutBits PVS_sbsComplete}alerts{isComplete isMIA active}}THC{packagePartNumber packageSerialNumber THC_InfoMsg{isComplete isMIA THC_appGitHash}THC_Logging{THC_LOG_PW_2_0_EnableLineState}}POD{POD_EnergyStatus{isMIA POD_nom_energy_remaining POD_nom_full_pack_energy}POD_InfoMsg{POD_appGitHash}}SYNC{packagePartNumber packageSerialNumber SYNC_InfoMsg{isMIA SYNC_appGitHash SYNC_assemblyId}METER_X_AcMeasurements{isMIA isComplete METER_X_CTA_InstRealPower METER_X_CTA_InstReactivePower METER_X_CTA_I METER_X_VL1N METER_X_CTB_InstRealPower METER_X_CTB_InstReactivePower METER_X_CTB_I METER_X_VL2N METER_X_CTC_InstRealPower METER_X_CTC_InstReactivePower METER_X_CTC_I METER_X_VL3N}METER_Y_AcMeasurements{isMIA isComplete METER_Y_CTA_InstRealPower METER_Y_CTA_InstReactivePower METER_Y_CTA_I METER_Y_VL1N METER_Y_CTB_InstRealPower METER_Y_CTB_InstReactivePower METER_Y_CTB_I METER_Y_VL2N METER_Y_CTC_InstRealPower METER_Y_CTC_InstReactivePower METER_Y_CTC_I METER_Y_VL3N}}ISLANDER{ISLAND_GridConnection{ISLAND_GridConnected isComplete}ISLAND_AcMeasurements{ISLAND_VL1N_Main ISLAND_FreqL1_Main ISLAND_VL2N_Main ISLAND_FreqL2_Main ISLAND_VL3N_Main ISLAND_FreqL3_Main ISLAND_VL1N_Load ISLAND_FreqL1_Load ISLAND_VL2N_Load ISLAND_FreqL2_Load ISLAND_VL3N_Load ISLAND_FreqL3_Load ISLAND_GridState isComplete isMIA}}}enumeration{inProgress numACPW numPVI}firmwareUpdate{isUpdating powerwalls{updating numSteps currentStep currentStepProgress progress}msa{updating numSteps currentStep currentStepProgress progress}msa1{updating numSteps currentStep currentStepProgress progress}sync{updating numSteps currentStep currentStepProgress progress}pvInverters{updating numSteps currentStep currentStepProgress progress}}phaseDetection{inProgress lastUpdateTimestamp powerwalls{din progress phase}}inverterSelfTests{isRunning isCanceled pinvSelfTestsResults{din overall{status test summary setMagnitude setTime tripMagnitude tripTime accuracyMagnitude accuracyTime currentMagnitude timestamp lastError}testResults{status test summary setMagnitude setTime tripMagnitude tripTime accuracyMagnitude accuracyTime currentMagnitude timestamp lastError}}}}components{msa:components(filter:$msaComp){partNumber serialNumber signals(names:$msaSignals){name value textValue boolValue timestamp}activeAlerts{name}}}ieee20305{longFormDeviceID polledResources{url name pollRateSeconds lastPolledTimestamp}controls{defaultControl{mRID setGradW opModEnergize opModMaxLimW opModImpLimW opModExpLimW opModGenLimW opModLoadLimW}activeControls{opModEnergize opModMaxLimW opModImpLimW opModExpLimW opModGenLimW opModLoadLimW}}registration{dateTimeRegistered pin}}}'
        pb.message.payload.send.code = b'0\x81\x87\x02B\x01A\x95\x12\xe3B\xd1\xca\x1a\xd3\x00\xf6}\x0bE@/\x9a\x9f\xc0\r\x06%\xac,\x0ej!)\nd\xef\xe67\x8b\xafb\xd7\xf8&\x0b.\xc1\xac\xd9!\x1f\xd6\x83\xffkIm\xf3\\J\xd8\xeeiTY\xde\x7f\xc5xR\x02A\x1dC\x03H\xfb8"\xb0\xe4\xd6\x18\xde\x11\xc45\xb2\xa9VB\xa6J\x8f\x08\x9d\xba\x86\xf1 W\xcdJ\x8c\x02*\x05\x12\xcb{<\x9b\xc8g\xc9\x9d9\x8bR\xb3\x89\xb8\xf1\xf1\x0f\x0e\x16E\xed\xd7\xbf\xd5&)\x92.\x12'
        pb.message.payload.send.b.value = '{"msaComp":{"types" :["PVS","PVAC", "TESYNC", "TEPINV", "TETHC", "STSTSM",  "TEMSA", "TEPINV" ]},\n\t"msaSignals":[\n\t"MSA_pcbaId",\n\t"MSA_usageId",\n\t"MSA_appGitHash",\n\t"MSA_HeatingRateOccurred",\n\t"THC_AmbientTemp",\n\t"METER_Z_CTA_InstRealPower",\n\t"METER_Z_CTA_InstReactivePower",\n\t"METER_Z_CTA_I",\n\t"METER_Z_VL1G",\n\t"METER_Z_CTB_InstRealPower",\n\t"METER_Z_CTB_InstReactivePower",\n\t"METER_Z_CTB_I",\n\t"METER_Z_VL2G"]}'
        pb.tail.value = 1
        url = f'https://{self.gw_ip}/tedapi/v1'
        try:
            # Set lock
            self.apilock['controller'] = True
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                          headers={'Content-type': 'application/octet-string'},
                                          data=pb.SerializeToString(), timeout=self.timeout)
            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                self.apilock['controller'] = False
                return None
            if r.status_code != 200:
                log.error(f"Error fetching controller data: {r.status_code}")
                self.apilock['controller'] = False
                return None
            # Decode response
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(r.content)
            payload = tedapi.message.payload.recv.text
            log.debug(f"Payload: {payload}")
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                log.error(f"Error Decoding JSON: {e}")
                data = {}
            log.debug(f"Status: {data}")
            self.pwcachetime["controller"] = time.time()
            self.pwcache["controller"] = data
        except Exception as e:
            log.error(f"Error fetching controller data: {e}")
            data = None
        finally:
            # Release lock
            self.apilock['controller'] = False
        return data

    def get_firmware_version(self, force=False, details=False):
        """
        Get the Powerwall Firmware Version

        Args:
            force (bool): Force a refresh of the firmware version
            details (bool): Return additional system information including
                            gateway part number, serial number, and wireless devices
        """
        payload = None
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get firmware version")
                return None
        # Check Cache
        if not force and "firmware" in self.pwcachetime:
            if time.time() - self.pwcachetime["firmware"] < self.pwcacheexpire:
                log.debug("Using Cached Firmware")
                return self.pwcache["firmware"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Fetch Current Status from Powerwall
        log.debug("Get Firmware Version from Powerwall")
        # Build Protobuf to fetch status
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.firmware.request = ""
        pb.tail.value = 1
        url = f'https://{GW_IP}/tedapi/v1'
        try:
            # Set lock
            self.apilock['firmware'] = True
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                          headers={'Content-type': 'application/octet-string'},
                                          data=pb.SerializeToString(), timeout=self.timeout)
            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                self.apilock['firmware'] = False
                return None
            if r.status_code != 200:
                log.error(f"Error fetching firmware version: {r.status_code}")
                self.apilock['firmware'] = False
                return None
            # Decode response
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(r.content)
            firmware_version = tedapi.message.firmware.system.version.text
            if details:
                payload = {
                    "system": {
                        "gateway": {
                            "partNumber": tedapi.message.firmware.system.gateway.partNumber,
                            "serialNumber": tedapi.message.firmware.system.gateway.serialNumber
                        },
                        "din": tedapi.message.firmware.system.din,
                        "version": {
                            "text": tedapi.message.firmware.system.version.text,
                            "githash": tedapi.message.firmware.system.version.githash
                        },
                        "five": tedapi.message.firmware.system.five,
                        "six": tedapi.message.firmware.system.six,
                        "wireless": {
                            "device": []
                        }
                    }
                }
                try:
                    for device in tedapi.message.firmware.system.wireless.device:
                        payload["system"]["wireless"]["device"].append({
                            "company": device.company.value,
                            "model": device.model.value,
                            "fcc_id": device.fcc_id.value,
                            "ic": device.ic.value
                        })
                except Exception as e:
                    log.debug(f"Error parsing wireless devices: {e}")
                log.debug(f"Firmware Version: {payload}")
            else:
                payload = firmware_version
            log.debug(f"Firmware Version: {firmware_version}")
            self.pwcachetime["firmware"] = time.time()
            self.pwcache["firmware"] = firmware_version
        except Exception as e:
            log.error(f"Error fetching firmware version: {e}")
            payload = None
        finally:
            # Release lock
            self.apilock['firmware'] = False
        return payload

    def get_components(self, force=False):
        """
        Get the Powerwall 3 Device Information

        Note: Provides empty response for previous Powerwall versions
        """
        components = None
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get configuration")
                return None
        # Check Cache
        if not force and "components" in self.pwcachetime:
            if time.time() - self.pwcachetime["components"] < self.pwconfigexpire:
                log.debug("Using Cached Components")
                return self.pwcache["components"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Fetch Configuration from Powerwall
        log.debug("Get PW3 Components from Powerwall")
        # Build Protobuf to fetch config
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = " query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n"
        pb.message.payload.send.code = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
        pb.message.payload.send.b.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
        pb.tail.value = 1
        url = f'https://{GW_IP}/tedapi/v1'
        try:
            # Set lock
            self.apilock['components'] = True
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                          headers={'Content-type': 'application/octet-string'},
                                          data=pb.SerializeToString(), timeout=self.timeout)
            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                self.apilock['components'] = False
                return None
            if r.status_code != 200:
                log.error(f"Error fetching components: {r.status_code}")
                self.apilock['components'] = False
                return None
            # Decode response
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(r.content)
            payload = tedapi.message.payload.recv.text
            log.debug(f"Payload (len={len(payload)}): {payload}")
            # Append payload to components
            components = json.loads(payload)
            log.debug(f"Components: {components}")
            self.pwcachetime["components"] = time.time()
            self.pwcache["components"] = components
        except Exception as e:
            log.error(f"Error fetching components: {e}")
            components = None
        finally:
            # Release lock
            self.apilock['components'] = False
        return components


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
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get configuration")
                return None
        # Check Cache
        if not force and "pw3_vitals" in self.pwcachetime:
            if time.time() - self.pwcachetime["pw3_vitals"] < self.pwconfigexpire:
                log.debug("Using Cached Components")
                return self.pwcache["pw3_vitals"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        components = self.get_components(force)
        din = self.din
        if not components:
            log.error("Unable to get Powerwall 3 Components")
            return None

        response = {}
        config = self.get_config(force)
        battery_blocks = config['battery_blocks']

        # Loop through all the battery blocks (Powerwalls)
        for battery in battery_blocks:
            pw_din = battery['vin'] # 1707000-11-J--TG12xxxxxx3A8Z
            pw_part, pw_serial = pw_din.split('--')
            battery_type = battery['type']
            if "Powerwall3" not in battery_type:
                continue
            # Fetch Device ComponentsQuery from each Powerwall
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = 1
            pb.message.sender.local = 1
            pb.message.sender.din = din  # DIN of Primary Powerwall 3 / System
            pb.message.recipient.din = pw_din  # DIN of Powerwall of Interest
            pb.message.payload.send.num = 2
            pb.message.payload.send.payload.value = 1
            pb.message.payload.send.payload.text = " query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n"
            pb.message.payload.send.code = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
            pb.message.payload.send.b.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
            pb.tail.value = 2
            url = f'https://{GW_IP}/tedapi/device/{pw_din}/v1'
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                            headers={'Content-type': 'application/octet-string'},
                            data=pb.SerializeToString(), timeout=self.timeout)
            if r.status_code == 200:
                # Decode response
                tedapi = tedapi_pb2.Message()
                tedapi.ParseFromString(r.content)
                payload = tedapi.message.payload.recv.text
                if payload:
                    data = json.loads(payload)
                    # TEDPOD
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
                else:
                    log.debug(f"No payload for {pw_din}")
            else:
                log.debug(f"Error fetching components: {r.status_code}")
        return response


    def get_battery_blocks(self, force=False):
        """
        Return Powerwall Battery Blocks
        """
        config = self.get_config(force)
        battery_blocks = config.get('battery_blocks') or []
        return battery_blocks


    def get_battery_block(self, din=None, force=False):
        """
        Get the Powerwall 3 Battery Block Information

        Args:
            din (str): DIN of Powerwall 3 to query
            force (bool): Force a refresh of the battery block

        Note: Provides 404 response for previous Powerwall versions
        """
        data = None
        # Make sure we have a DIN
        if not din:
            log.error("No DIN specified - Unable to get battery block")
            return None
        # Check Cache
        if not force and din in self.pwcachetime:
            if time.time() - self.pwcachetime[din] < self.pwcacheexpire:
                log.debug("Using Cached Battery Block")
                return self.pwcache[din]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Fetch Battery Block from Powerwall
        log.debug(f"Get Battery Block from Powerwall ({din})")
        # Build Protobuf to fetch config
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.sender.din = self.din  # DIN of Primary Powerwall 3 / System
        pb.message.recipient.din = din  # DIN of Powerwall of Interest
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = " query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n"
        pb.message.payload.send.code = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
        pb.message.payload.send.b.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
        pb.tail.value = 2   
        url = f'https://{self.gw_ip}/tedapi/device/{din}/v1'
        try:
            # Set lock
            self.apilock[din] = True
            r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
                                        headers={'Content-type': 'application/octet-string'},
                                        data=pb.SerializeToString(), timeout=self.timeout)
            log.debug(f"Response Code: {r.status_code}")
            if r.status_code in BUSY_CODES:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                self.apilock[din] = False
                return None
            if r.status_code == 404:
                log.debug(f"Device not found: {din}")
                self.apilock[din] = False
                return None
            if r.status_code != 200:
                log.error(f"Error fetching config: {r.status_code}")
                self.apilock[din] = False
                return None
            # Decode response
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(r.content)
            payload = tedapi.message.config.recv.file.text
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                log.error(f"Error Decoding JSON: {e}")
                data = {}
            log.debug(f"Configuration: {data}")
            self.pwcachetime[din] = time.time()
            self.pwcache[din] = data
        except Exception as e:
            log.error(f"Error fetching device: {e}")
            data = None
        finally:
            # Release lock
            self.apilock[din] = False
        return data

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
            if resp.status_code != 200:
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
        status = self.get_status(force)
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
        status = self.get_status(force)
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
        status = self.get_status(force)
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
        def calculate_ac_power(Vpeak, Ipeak):
            Vrms = Vpeak / math.sqrt(2)
            Irms = Ipeak / math.sqrt(2)
            power = Vrms * Irms
            return power

        def calculate_dc_power(V, I):
            power = V * I
            return power

        # status = self.get_status(force)
        config = self.get_config(force)
        status = self.get_device_controller(force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None

        # Build meter Lookup if available
        meter_config = {}
        if "meters" in config:
            # Loop through each meter and use device_serial as the key
            for meter in config['meters']:
                if meter['type'] == "neurio_w2_tcp":
                    device_serial = lookup(meter, ['connection', 'device_serial'])
                    if device_serial:
                        meter_config[device_serial] = {
                            "type": meter.get('type'),
                            "location": meter.get('location'),
                            "cts": meter.get('cts'),
                            "inverted": meter.get('inverted'),
                            "connection": meter.get('connection'),
                            "real_power_scale_factor": meter.get('real_power_scale_factor', 1)
                        }

        # Create Header
        tesla = {}
        header = {}
        header["VITALS"] = {
            "text": "Device vitals generated from Tesla Powerwall Gateway TEDAPI",
            "timestamp": time.time(),
            "gateway": self.gw_ip,
            "pyPowerwall": __version__,
        }

        # Create NEURIO block
        neurio = {}
        c = 1000
        # Loop through each Neurio device serial number
        for n in lookup(status, ['neurio', 'readings']) or {}:
            # Loop through each CT on the Neurio device
            sn = n.get('serial', str(c))
            cts = {}
            i = 0
            c = c + 1
            for ct in n['dataRead'] or {}:
                # Only show if we have a meter configuration and cts[i] is true
                cts_bool = lookup(meter_config, [sn, 'cts'])
                if isinstance(cts_bool, list) and i < len(cts_bool):
                    if not cts_bool[i]:
                        # Skip this CT
                        i = i + 1
                        continue
                factor = lookup(meter_config, [sn, 'real_power_scale_factor']) or 1
                device = f"NEURIO_CT{i}_"
                cts[device + "InstRealPower"] = lookup(ct, ['realPowerW']) * factor
                cts[device + "InstReactivePower"] = lookup(ct, ['reactivePowerVAR'])
                cts[device + "InstVoltage"] = lookup(ct, ['voltageV'])
                cts[device + "InstCurrent"] = lookup(ct, ['currentA'])
                cts[device + "Location"] = lookup(meter_config, [sn, 'location'])
                i = i + 1
            meter_manufacturer = None
            if lookup(meter_config, [sn, 'type']) == "neurio_w2_tcp":
                meter_manufacturer = "NEURIO"
            rest = {
                "componentParentDin": lookup(config, ['vin']),
                "firmwareVersion": None,
                "lastCommunicationTime": lookup(n, ['timestamp']),
                "manufacturer": meter_manufacturer,
                "meterAttributes": {
                    "meterLocation": []
                },
                "serialNumber": sn
            }
            neurio[f"NEURIO--{sn}"] = {**cts, **rest}

        # Create PVAC, PVS, and TESLA blocks - Assume the are aligned
        pvac = {}
        pvs = {}
        tesla = {}
        i = 0
        num = len(lookup(status, ['esCan', 'bus', 'PVAC']) or {})
        if num != len(lookup(status, ['esCan', 'bus', 'PVS']) or {}):
            log.debug("PVAC and PVS device count mismatch in TEDAPI")
        # Loop through each device serial number
        for p in lookup(status, ['esCan', 'bus', 'PVAC']) or {}:
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            pvac_name = f"PVAC--{packagePartNumber}--{packageSerialNumber}"
            V_A = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_A']
            V_B = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_B']
            V_C = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_C']
            V_D = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_D']
            I_A = p['PVAC_Logging']['PVAC_PVCurrent_A']
            I_B = p['PVAC_Logging']['PVAC_PVCurrent_B']
            I_C = p['PVAC_Logging']['PVAC_PVCurrent_C']
            I_D = p['PVAC_Logging']['PVAC_PVCurrent_D']
            P_A = calculate_dc_power(V_A, I_A)
            P_B = calculate_dc_power(V_B, I_B)
            P_C = calculate_dc_power(V_C, I_C)
            P_D = calculate_dc_power(V_D, I_D)
            pvac[pvac_name] = {
                "PVAC_Fout": lookup(p, ['PVAC_Status', 'PVAC_Fout']),
                "PVAC_GridState": None,
                "PVAC_InvState": None,
                "PVAC_Iout": None,
                "PVAC_LifetimeEnergyPV_Total": None,
                "PVAC_PVCurrent_A": I_A,
                "PVAC_PVCurrent_B": I_B,
                "PVAC_PVCurrent_C": I_C,
                "PVAC_PVCurrent_D": I_D,
                "PVAC_PVMeasuredPower_A": P_A, # computed
                "PVAC_PVMeasuredPower_B": P_B, # computed
                "PVAC_PVMeasuredPower_C": P_C, # computed
                "PVAC_PVMeasuredPower_D": P_D, # computed
                "PVAC_PVMeasuredVoltage_A": V_A,
                "PVAC_PVMeasuredVoltage_B": V_B,
                "PVAC_PVMeasuredVoltage_C": V_C,
                "PVAC_PVMeasuredVoltage_D": V_D,
                "PVAC_Pout": lookup(p, ['PVAC_Status', 'PVAC_Pout']),
                "PVAC_PvState_A": None, # These are placeholders
                "PVAC_PvState_B": None, # Compute from PVS below
                "PVAC_PvState_C": None, # PV_Disabled, PV_Active, PV_Active_Parallel
                "PVAC_PvState_D": None, # Not available in TEDAPI
                "PVAC_Qout": None,
                "PVAC_State": lookup(p, ['PVAC_Status', 'PVAC_State']),
                "PVAC_VHvMinusChassisDC": None,
                "PVAC_VL1Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL1Ground']),
                "PVAC_VL2Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL2Ground']),
                "PVAC_Vout": lookup(p, ['PVAC_Status', 'PVAC_Vout']),
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "PVI-PowerStatusSetpoint": None,
                "componentParentDin": None, # TODO: map to TETHC
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 296
                }
            }
            pvs_name = f"PVS--{packagePartNumber}--{packageSerialNumber}"
            pvs_data = lookup(status, ['esCan', 'bus', 'PVS'])
            if i < len(pvs_data):
                pvs_data = pvs_data[i]
                # Set String Connected states
                string_a = lookup(pvs_data, ['PVS_Status', 'PVS_StringA_Connected'])
                string_b = lookup(pvs_data, ['PVS_Status', 'PVS_StringB_Connected'])
                string_c = lookup(pvs_data, ['PVS_Status', 'PVS_StringC_Connected'])
                string_d = lookup(pvs_data, ['PVS_Status', 'PVS_StringD_Connected'])
                # Set PVAC PvState based on PVS String Connected states
                pvac[pvac_name]["PVAC_PvState_A"] = "PV_Active" if string_a else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_B"] = "PV_Active" if string_b else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_C"] = "PV_Active" if string_c else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_D"] = "PV_Active" if string_d else "PV_Disabled"
                pvs[pvs_name] = {
                    "PVS_EnableOutput": None,
                    "PVS_SelfTestState": lookup(pvs_data, ['PVS_Status', 'PVS_SelfTestState']),
                    "PVS_State": lookup(pvs_data, ['PVS_Status', 'PVS_State']),
                    "PVS_StringA_Connected": string_a,
                    "PVS_StringB_Connected": string_b,
                    "PVS_StringC_Connected": string_c,
                    "PVS_StringD_Connected": string_d,
                    "PVS_vLL": lookup(pvs_data, ['PVS_Status', 'PVS_vLL']),
                    "alerts": lookup(pvs_data, ['alerts', 'active']) or [],
                    "componentParentDin": pvac_name,
                    "firmwareVersion": None,
                    "lastCommunicationTime": None,
                    "manufacturer": "TESLA",
                    "partNumber": packagePartNumber,
                    "serialNumber": packageSerialNumber,
                    "teslaEnergyEcuAttributes": {
                        "ecuType": 297
                    }
                }
            tesla_name = f"TESLA--{packagePartNumber}--{packageSerialNumber}"
            if "solars" in config and i < len(config.get('solars', [{}])):
                tesla_nameplate = config['solars'][i].get('power_rating_watts', None)
                brand = config['solars'][i].get('brand', None)
            else:
                tesla_nameplate = None
                brand = None
            tesla[tesla_name] = {
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": brand.upper() if brand else "TESLA",
                "pvInverterAttributes": {
                    "nameplateRealPowerW": tesla_nameplate,
                },
                "serialNumber": f"{packagePartNumber}--{packageSerialNumber}",
            }
            i = i + 1

        # Create STSTSM block
        name = f"STSTSM--{lookup(config, ['vin'])}"
        ststsm = {}
        ststsm[name] =  {
            "STSTSM-Location": "Gateway",
            "alerts": lookup(status, ['control', 'alerts', 'active']) or [],
            "firmwareVersion": None,
            "lastCommunicationTime": None,
            "manufacturer": "TESLA",
            "partNumber": lookup(config, ['vin']).split('--')[0],
            "serialNumber": lookup(config, ['vin']).split('--')[-1],
            "teslaEnergyEcuAttributes": {
                "ecuType": 207
            }
        }

        # Get Dictionary of Powerwall Temperatures
        temp_sensors = {}
        for i in lookup(status, ['components', 'msa']) or []:
            if "signals" in i and "serialNumber" in i and i["serialNumber"]:
                for s in i["signals"]:
                    if "name" in s and s["name"] == "THC_AmbientTemp" and "value" in s:
                        temp_sensors[i["serialNumber"]] = s["value"]

        # Create TETHC, TEPINV and TEPOD blocks
        tethc = {} # parent
        tepinv = {}
        tepod = {}
        i = 0
        # Loop through each THC device serial number
        for p in lookup(status, ['esCan', 'bus', 'THC']) or {}:
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # TETHC block
            parent_name = f"TETHC--{packagePartNumber}--{packageSerialNumber}"
            tethc[parent_name] = {
                "THC_AmbientTemp": temp_sensors.get(packageSerialNumber, None),
                "THC_State": None,
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 224
                }
            }
            # TEPOD block
            name = f"TEPOD--{packagePartNumber}--{packageSerialNumber}"
            pod = lookup(status, ['esCan', 'bus', 'POD'])[i]
            energy_remaining = lookup(pod, ['POD_EnergyStatus', 'POD_nom_energy_remaining'])
            full_pack_energy = lookup(pod, ['POD_EnergyStatus', 'POD_nom_full_pack_energy'])
            if energy_remaining and full_pack_energy:
                energy_to_be_charged = full_pack_energy - energy_remaining
            else:
                energy_to_be_charged = None
            tepod[name] = {
                "POD_ActiveHeating": None,
                "POD_CCVhold": None,
                "POD_ChargeComplete": None,
                "POD_ChargeRequest": None,
                "POD_DischargeComplete": None,
                "POD_PermanentlyFaulted": None,
                "POD_PersistentlyFaulted": None,
                "POD_available_charge_power": None,
                "POD_available_dischg_power": None,
                "POD_enable_line": None,
                "POD_nom_energy_remaining": energy_remaining,
                "POD_nom_energy_to_be_charged": energy_to_be_charged, #computed
                "POD_nom_full_pack_energy": full_pack_energy,
                "POD_state": None,
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "componentParentDin": parent_name,
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 226
                }
            }
            # TEPINV block
            name = f"TEPINV--{packagePartNumber}--{packageSerialNumber}"
            pinv = lookup(status, ['esCan', 'bus', 'PINV'])[i]
            tepinv[name] = {
                "PINV_EnergyCharged": None,
                "PINV_EnergyDischarged": None,
                "PINV_Fout": lookup(pinv, ['PINV_Status', 'PINV_Fout']),
                "PINV_GridState": lookup(p, ['PINV_Status', 'PINV_GridState']),
                "PINV_HardwareEnableLine": None,
                "PINV_PllFrequency": None,
                "PINV_PllLocked": None,
                "PINV_Pnom": lookup(pinv, ['PINV_PowerCapability', 'PINV_Pnom']),
                "PINV_Pout": lookup(pinv, ['PINV_Status', 'PINV_Pout']),
                "PINV_PowerLimiter": None,
                "PINV_Qout": None,
                "PINV_ReadyForGridForming": None,
                "PINV_State": lookup(pinv, ['PINV_Status', 'PINV_State']),
                "PINV_VSplit1": lookup(pinv, ['PINV_AcMeasurements', 'PINV_VSplit1']),
                "PINV_VSplit2": lookup(pinv, ['PINV_AcMeasurements', 'PINV_VSplit2']),
                "PINV_Vout": lookup(pinv, ['PINV_Status', 'PINV_Vout']),
                "alerts": lookup(pinv, ['alerts', 'active']) or [],
                "componentParentDin": parent_name,
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 253
                }
            }
            i = i + 1

        # Create TESYNC block
        tesync = {}
        sync = lookup(status, ['esCan', 'bus', 'SYNC']) or {}
        islander = lookup(status, ['esCan', 'bus', 'ISLANDER']) or {}
        packagePartNumber = sync.get('packagePartNumber', None)
        packageSerialNumber = sync.get('packageSerialNumber', None)
        name = f"TESYNC--{packagePartNumber}--{packageSerialNumber}"
        tesync[name] = {
            "ISLAND_FreqL1_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL1_Load']),
            "ISLAND_FreqL1_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL1_Main']),
            "ISLAND_FreqL2_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL2_Load']),
            "ISLAND_FreqL2_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL2_Main']),
            "ISLAND_FreqL3_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL3_Load']),
            "ISLAND_FreqL3_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL3_Main']),
            "ISLAND_GridConnected": lookup(islander, ['ISLAND_GridConnection', 'ISLAND_GridConnected']),
            "ISLAND_GridState": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_GridState']),
            "ISLAND_L1L2PhaseDelta":lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1L2PhaseDelta']),
            "ISLAND_L1L3PhaseDelta": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1L3PhaseDelta']),
            "ISLAND_L1MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1MicrogridOk']),
            "ISLAND_L2L3PhaseDelta": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L2L3PhaseDelta']),
            "ISLAND_L2MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L2MicrogridOk']),
            "ISLAND_L3MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L3MicrogridOk']),
            "ISLAND_PhaseL1_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL1_Main_Load']),
            "ISLAND_PhaseL2_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL2_Main_Load']),
            "ISLAND_PhaseL3_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL3_Main_Load']),
            "ISLAND_ReadyForSynchronization": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_ReadyForSynchronization']),
            "ISLAND_VL1N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL1N_Load']),
            "ISLAND_VL1N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL1N_Main']),
            "ISLAND_VL2N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL2N_Load']),
            "ISLAND_VL2N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL2N_Main']),
            "ISLAND_VL3N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL3N_Load']),
            "ISLAND_VL3N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL3N_Main']),
            "METER_X_CTA_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_I']),
            "METER_X_CTA_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_InstReactivePower']),
            "METER_X_CTA_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_InstRealPower']),
            "METER_X_CTB_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_I']),
            "METER_X_CTB_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_InstReactivePower']),
            "METER_X_CTB_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_InstRealPower']),
            "METER_X_CTC_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_I']),
            "METER_X_CTC_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_InstReactivePower']),
            "METER_X_CTC_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_InstRealPower']),
            "METER_X_LifetimeEnergyExport": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_LifetimeEnergyExport']),
            "METER_X_LifetimeEnergyImport": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_LifetimeEnergyImport']),
            "METER_X_VL1N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL1N']),
            "METER_X_VL2N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL2N']),
            "METER_X_VL3N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL3N']),
            "METER_Y_CTA_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_I']),
            "METER_Y_CTA_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_InstReactivePower']),
            "METER_Y_CTA_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_InstRealPower']),
            "METER_Y_CTB_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_I']),
            "METER_Y_CTB_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_InstReactivePower']),
            "METER_Y_CTB_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_InstRealPower']),
            "METER_Y_CTC_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_I']),
            "METER_Y_CTC_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_InstReactivePower']),
            "METER_Y_CTC_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_InstRealPower']),
            "METER_Y_LifetimeEnergyExport": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_LifetimeEnergyExport']),
            "METER_Y_LifetimeEnergyImport": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_LifetimeEnergyImport']),
            "METER_Y_VL1N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL1N']),
            "METER_Y_VL2N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL2N']),
            "METER_Y_VL3N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL3N']),
            "SYNC_ExternallyPowered": None,
            "SYNC_SiteSwitchEnabled": None,
            "alerts": lookup(sync, ['alerts', 'active']) or [],
            "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
            "firmwareVersion": None,
            "manufacturer": "TESLA",
            "partNumber": packagePartNumber,
            "serialNumber": packageSerialNumber,
            "teslaEnergyEcuAttributes": {
                "ecuType": 259
            }
        }

        # Create TESLA block - tied to TESYNC
        name = f"TESLA--{packageSerialNumber}"
        tesla[name] = {
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "meterAttributes": {
                    "meterLocation": [
                        1
                    ]
                },
                "serialNumber": packageSerialNumber
            }

        # Create Vitals Dictionary
        vitals = {
            **header,
            **neurio,
            **pvac,
            **pvs,
            **ststsm,
            **tepinv,
            **tepod,
            **tesla,
            **tesync,
            **tethc,
        }
        # Merge in the Powerwall 3 data if available
        if self.pw3:
            pw3_data = self.get_pw3_vitals(force) or {}
            vitals.update(pw3_data)

        return vitals


    def get_blocks(self, force=False):
        """
        Get the list of battery blocks from the Powerwall Gateway
        """
        status = self.get_status(force)
        config = self.get_config(force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None
        block = {}
        i = 0
        # Loop through each THC device serial number
        for p in lookup(status, ['esCan', 'bus', 'THC']) or {}:
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
            i = i + 1
        return block

    # End of TEDAPI Class

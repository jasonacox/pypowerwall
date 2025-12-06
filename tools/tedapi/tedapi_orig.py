# pyPowerWall - Tesla TEDAPI Class
# -*- coding: utf-8 -*-
"""
 Tesla TEADAPI Class
 
 This module allows you to access the Tesla Powerwall Gateway 
 TEDAPI on 192.168.91.1 as used by the Tesla One app.

 Class:
    TEDAPI - Tesla TEDAPI Class

 Functions:
    get_din() - Get the DIN from the Powerwall Gateway
    get_config() - Get the Powerwall Gateway Configuration
    get_status() - Get the Powerwall Gateway Status

 Note:
    This module requires access to the Powerwall Gateway. You can add a route to
    using the command: sudo route add -host 192.168.91.1 <Powerwall_IP>
    The Powerwall Gateway password is required to access the TEDAPI.

 Author: Jason A. Cox
 Date: 1 Jun 2024
 For more information see https://github.com/jasonacox/pypowerwall
"""

# Imports
import requests
import logging
import tedapi_pb2 
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import json
import time

# TEDAPI Fixed Gateway IP Address
GW_IP = "192.168.91.1"

# Rate Limit Codes
BUSY_CODES = [429, 503]

# Setup Logging
log = logging.getLogger(__name__)

# TEDAPI Class
class TEDAPI:
    def __init__(self, gw_pwd, debug=False, pwcacheexpire: int = 5, timeout: int = 5):
        self.debug = debug 
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire cache
        self.pwcache = {}  # holds the cached data for api
        self.timeout = timeout
        self.pwcooldown = 0
        self.din = None
        # Require both gw_ip and gw_pwd
        if not gw_pwd:
            raise ValueError("Missing gw_ip or gw_pwd")
        if self.debug:
            log.setLevel(logging.DEBUG)
        self.gw_pwd = gw_pwd
        # Connect to Powerwall Gateway
        if not self.connect():
            log.error("Failed to connect to Powerwall Gateway")
            raise ValueError("Failed to connect to Powerwall Gateway")

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
        url = f'https://{GW_IP}/tedapi/din'
        r = requests.get(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False)
        if r.status_code in BUSY_CODES:
            # Rate limited - Switch to cooldown mode for 5 minutes
            self.pwcooldown = time.perf_counter() + 300
            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
            return None
        if r.status_code != 200:
            log.error(f"Error fetching DIN: {r.status_code}")
            return None
        din = r.text
        log.debug(f"Connected: Powerwall Gateway DIN: {din}")
        self.pwcachetime["din"] = time.time()
        self.pwcache["din"] = din
        return din
    
    def connect(self):
        """
        Connect to the Powerwall Gateway
        """
        # Test IP Connection to Powerwall Gateway
        log.debug(f"Testing Connection to Powerwall Gateway: {GW_IP}")
        url = f'https://{GW_IP}'
        try:
            r = requests.get(url, verify=False, timeout=5)
            r = True # no exception, so the request was successful
        except requests.exceptions.RequestException as e:
            r = False
            log.error("ERROR: Powerwall not Found",
                      f"Try: sudo route add -host <Powerwall_IP> {GW_IP}")
        if r:
            # Attempt to fetch DIN from Powerwall
            self.din = self.get_din()
            return True
        self.din = None
        return False
    
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
        # Check Cache
        if not force and "config" in self.pwcachetime:
            if time.time() - self.pwcachetime["config"] < self.pwcacheexpire:
                log.debug("Using Cached Payload")
                return self.pwcache["config"]
        if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
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
        url = f'https://{GW_IP}/tedapi/v1'
        r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
            headers={'Content-type': 'application/octet-string'},
            data=pb.SerializeToString())
        log.debug(f"Response Code: {r.status_code}")
        if r.status_code in BUSY_CODES:
            # Rate limited - Switch to cooldown mode for 5 minutes
            self.pwcooldown = time.perf_counter() + 300
            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
            return None
        if r.status_code != 200:
            log.error(f"Error fetching config: {r.status_code}")
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
        # Check Cache
        if not force and "status" in self.pwcachetime:
            if time.time() - self.pwcachetime["status"] < self.pwcacheexpire:
                log.debug("Using Cached Payload")
                return self.pwcache["status"]
        if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
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
        url = f'https://{GW_IP}/tedapi/v1'
        r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
            headers={'Content-type': 'application/octet-string'},
            data=pb.SerializeToString())
        log.debug(f"Response Code: {r.status_code}")
        if r.status_code in BUSY_CODES:
            # Rate limited - Switch to cooldown mode for 5 minutes
            self.pwcooldown = time.perf_counter() + 300
            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
            return None
        if r.status_code != 200:
            log.error(f"Error fetching status: {r.status_code}")
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
        return data
    
    # End of TEDAPI Class

# Test Code
if __name__ == "__main__":
    import sys

    # Print Header
    print("Tesla Powerwall Gateway TEDAPI Reader")
    print()

    # Command line arguments
    if len(sys.argv) > 1:
        gw_pwd = sys.argv[1]
    else:
        # Get GW_PWD from User
        gw_pwd = input("\nEnter Powerwall Gateway Password: ")

    # Create TEDAPI Object and get Configuration and Status
    print(f"Connecting to Powerwall Gateway {GW_IP}")
    ted = TEDAPI(gw_pwd)
    config = ted.get_config() or {}
    status = ted.get_status() or {}
    print()

    # Print Configuration
    print(" - Configuration:")
    site_info = config.get('site_info', {}) or {}
    site_name = site_info.get('site_name', 'Unknown')
    print(f"   - Site Name: {site_name}")
    battery_commission_date = site_info.get('battery_commission_date', 'Unknown')
    print(f"   - Battery Commission Date: {battery_commission_date}")
    vin = config.get('vin', 'Unknown')
    print(f"   - VIN: {vin}")
    number_of_powerwalls = len(config.get('battery_blocks', []))
    print(f"   - Number of Powerwalls: {number_of_powerwalls}")
    print()

    # Print power data
    print(" - Power Data:")
    nominalEnergyRemainingWh = status.get('control', {}).get('systemStatus', {}).get('nominalEnergyRemainingWh', 0)
    nominalFullPackEnergyWh = status.get('control', {}).get('systemStatus', {}).get('nominalFullPackEnergyWh', 0)
    soe = round(nominalEnergyRemainingWh / nominalFullPackEnergyWh * 100, 2)
    print(f"   - Battery Charge: {soe}% ({nominalEnergyRemainingWh}Wh of {nominalFullPackEnergyWh}Wh)")
    meterAggregates = status.get('control', {}).get('meterAggregates', [])
    for meter in meterAggregates:
        location = meter.get('location', 'Unknown').title()
        realPowerW = int(meter.get('realPowerW', 0))
        print(f"   - {location}: {realPowerW}W")
    print()

    # Save Configuration and Status to JSON files
    with open('status.json', 'w') as f:
        json.dump(status, f)
    with open('config.json', 'w') as f:
        json.dump(config, f)
    print(" - Configuration and Status saved to config.json and status.json")
    print()


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 Python library to pull live Powerwall device vitals data.
 Uses the Tesla Pros API (local TEG WiFi access point).

 Author: Jason A. Cox
 3 March 2024
 For more information see https://github.com/jasonacox/pypowerwall

 Classes
    TeslaGateway(password, ip, pwcacheexpire, timeout)

 Parameters
    password                # (required) Gateway password
    ip = "192.168.91.1"     # Address of Tesla Energy Gateway
    pwcacheexpire = 10      # Set API cache timeout in seconds
    timeout = 5             # Timeout for HTTPS calls in seconds

 Functions
    get_din()               # Return DIN of Gateway
    get_config()            # Return Configuration payload of Gateway
    get_status()            # Return Current Device Vitals of Gateway

 Requirements
    * You must be connected to the local WiFi network of the Tesla Energy Gateway (e.g. TEG-XXX)
    * The Gateway Password (found on the Gateway near the QR code)
    * This module requires the python google.protobuf module.  Install with:
      pip install protobuf

"""

import time
import sys
import logging
from . import tedapi_pb2 
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import json

# Defaults
GW_IP = "192.168.91.1"

# pypowerwall tedapi module version
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

# Class to interact
class TeslaGateway:
    def __init__(self, password, ip=GW_IP, pwcacheexpire=10, timeout=5):
        self.gw_pwd = password
        self.gw_ip = ip
        self.pwcacheexpire = pwcacheexpire
        self.timeout = timeout
        self.din = None
        self.config = None
        self.status = None
        self.cache = {}

    def debug_mode(self, state=True):
        # Turn on/off debug Mode
        set_debug(state)

    def get_din(self):
        # Fetch DIN from Powerwall
        if "din" in self.cache and self.cache["din"]["expires"] > time.perf_counter():
            return self.cache["din"]["value"]
        url = f'https://{self.gw_ip}/tedapi/din'
        log.debug(f"Fetching DIN from {url}")
        r = requests.get(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False)
        # check for error
        if r.status_code != 200:
            log.error(f"Error fetching DIN: {r.status_code}")
            return None
        self.din = r.text
        self.cache["din"] = {"value": r.text, "expires": time.perf_counter() + self.pwcacheexpire}
        return r.text

    def get_config(self):
        # Fetch Configuration from Powerwall
        if "config" in self.cache and self.cache["config"]["expires"] > time.perf_counter():
            return self.cache["config"]["value"]
        if self.din is None:
            self.get_din()
        pb = tedapi_pb2.ParentMessage()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.config.send.num = 1
        pb.message.config.send.file = "config.json"
        pb.tail.value = 1
        url = f'https://{self.gw_ip}/tedapi/v1'
        log.debug(f"Fetching Configuration from {url}")
        r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
            headers={'Content-type': 'application/octet-string'},
            data=pb.SerializeToString())
        # check for error
        if r.status_code != 200:
            log.error(f"Error fetching Configuration: {r.status_code}")
            return None
        tedapi = tedapi_pb2.ParentMessage()
        tedapi.ParseFromString(r.content)
        config = json.loads(tedapi.message.config.recv.file)
        self.cache["config"] = {"value": config, "expires": time.perf_counter() + self.pwcacheexpire}
        return config

    def get_status(self):
        # Fetch Current Status from Powerwall
        if "status" in self.cache and self.cache["status"]["expires"] > time.perf_counter():
            return self.cache["status"]["value"]
        if self.din is None:
            self.get_din()
        pb = tedapi_pb2.ParentMessage()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = " query DeviceControllerQuery {\n  control {\n    systemStatus {\n        nominalFullPackEnergyWh\n        nominalEnergyRemainingWh\n    }\n    islanding {\n        customerIslandMode\n        contactorClosed\n        microGridOK\n        gridOK\n    }\n    meterAggregates {\n      location\n      realPowerW\n    }\n    alerts {\n      active\n    },\n    siteShutdown {\n      isShutDown\n      reasons\n    }\n    batteryBlocks {\n      din\n      disableReasons\n    }\n    pvInverters {\n      din\n      disableReasons\n    }\n  }\n  system {\n    time\n    sitemanagerStatus {\n      isRunning\n    }\n    updateUrgencyCheck  {\n      urgency\n      version {\n        version\n        gitHash\n      }\n      timestamp\n    }\n  }\n  neurio {\n    isDetectingWiredMeters\n    readings {\n      serial\n      dataRead {\n        voltageV\n        realPowerW\n        reactivePowerVAR\n        currentA\n      }\n      timestamp\n    }\n    pairings {\n      serial\n      shortId\n      status\n      errors\n      macAddress\n      isWired\n      modbusPort\n      modbusId\n      lastUpdateTimestamp\n    }\n  }\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  esCan {\n    bus {\n      PVAC {\n        packagePartNumber\n        packageSerialNumber\n        subPackagePartNumber\n        subPackageSerialNumber\n        PVAC_Status {\n          isMIA\n          PVAC_Pout\n          PVAC_State\n          PVAC_Vout\n          PVAC_Fout\n        }\n        PVAC_InfoMsg {\n          PVAC_appGitHash\n        }\n        PVAC_Logging {\n          isMIA\n          PVAC_PVCurrent_A\n          PVAC_PVCurrent_B\n          PVAC_PVCurrent_C\n          PVAC_PVCurrent_D\n          PVAC_PVMeasuredVoltage_A\n          PVAC_PVMeasuredVoltage_B\n          PVAC_PVMeasuredVoltage_C\n          PVAC_PVMeasuredVoltage_D\n          PVAC_VL1Ground\n          PVAC_VL2Ground\n        }\n        alerts {\n          isComplete\n          isMIA\n          active\n        }\n      }\n      PINV {\n        PINV_Status {\n          isMIA\n          PINV_Fout\n          PINV_Pout\n          PINV_Vout\n          PINV_State\n          PINV_GridState\n        }\n        PINV_AcMeasurements {\n          isMIA\n          PINV_VSplit1\n          PINV_VSplit2\n        }\n        PINV_PowerCapability {\n          isComplete\n          isMIA\n          PINV_Pnom\n        }\n        alerts {\n          isComplete\n          isMIA\n          active\n        }\n      }\n      PVS {\n        PVS_Status {\n          isMIA\n          PVS_State\n          PVS_vLL\n          PVS_StringA_Connected\n          PVS_StringB_Connected\n          PVS_StringC_Connected\n          PVS_StringD_Connected\n          PVS_SelfTestState\n        }\n        alerts {\n          isComplete\n          isMIA\n          active\n        }\n      }\n      THC {\n        packagePartNumber\n        packageSerialNumber\n        THC_InfoMsg {\n          isComplete\n          isMIA\n          THC_appGitHash\n        }\n        THC_Logging {\n          THC_LOG_PW_2_0_EnableLineState\n        }\n      }\n      POD {\n        POD_EnergyStatus {\n          isMIA\n          POD_nom_energy_remaining\n          POD_nom_full_pack_energy\n        }\n        POD_InfoMsg {\n            POD_appGitHash\n        }\n      }\n      MSA {\n        packagePartNumber\n        packageSerialNumber\n        MSA_InfoMsg {\n          isMIA\n          MSA_appGitHash\n          MSA_assemblyId\n        }\n        METER_Z_AcMeasurements {\n          isMIA\n          lastRxTime\n          METER_Z_CTA_InstRealPower\n          METER_Z_CTA_InstReactivePower\n          METER_Z_CTA_I\n          METER_Z_VL1G\n          METER_Z_CTB_InstRealPower\n          METER_Z_CTB_InstReactivePower\n          METER_Z_CTB_I\n          METER_Z_VL2G\n        }\n        MSA_Status {\n          lastRxTime\n        }\n      }\n      SYNC {\n        packagePartNumber\n        packageSerialNumber\n        SYNC_InfoMsg {\n          isMIA\n          SYNC_appGitHash\n        }\n        METER_X_AcMeasurements {\n          isMIA\n          isComplete\n          lastRxTime\n          METER_X_CTA_InstRealPower\n          METER_X_CTA_InstReactivePower\n          METER_X_CTA_I\n          METER_X_VL1N\n          METER_X_CTB_InstRealPower\n          METER_X_CTB_InstReactivePower\n          METER_X_CTB_I\n          METER_X_VL2N\n          METER_X_CTC_InstRealPower\n          METER_X_CTC_InstReactivePower\n          METER_X_CTC_I\n          METER_X_VL3N\n        }\n        METER_Y_AcMeasurements {\n          isMIA\n          isComplete\n          lastRxTime\n          METER_Y_CTA_InstRealPower\n          METER_Y_CTA_InstReactivePower\n          METER_Y_CTA_I\n          METER_Y_VL1N\n          METER_Y_CTB_InstRealPower\n          METER_Y_CTB_InstReactivePower\n          METER_Y_CTB_I\n          METER_Y_VL2N\n          METER_Y_CTC_InstRealPower\n          METER_Y_CTC_InstReactivePower\n          METER_Y_CTC_I\n          METER_Y_VL3N\n        }\n        SYNC_Status {\n          lastRxTime\n        }\n      }\n      ISLANDER {\n        ISLAND_GridConnection {\n          ISLAND_GridConnected\n          isComplete\n        }\n        ISLAND_AcMeasurements {\n          ISLAND_VL1N_Main\n          ISLAND_FreqL1_Main\n          ISLAND_VL2N_Main\n          ISLAND_FreqL2_Main\n          ISLAND_VL3N_Main\n          ISLAND_FreqL3_Main\n          ISLAND_VL1N_Load\n          ISLAND_FreqL1_Load\n          ISLAND_VL2N_Load\n          ISLAND_FreqL2_Load\n          ISLAND_VL3N_Load\n          ISLAND_FreqL3_Load\n          ISLAND_GridState\n          lastRxTime\n          isComplete\n          isMIA\n        }\n      }\n    }\n    enumeration {\n      inProgress\n      numACPW\n      numPVI\n    }\n    firmwareUpdate {\n      isUpdating\n      powerwalls {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n      msa {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n      sync {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n      pvInverters {\n        updating\n        numSteps\n        currentStep\n        currentStepProgress\n        progress\n      }\n    }\n    phaseDetection {\n      inProgress\n      lastUpdateTimestamp\n      powerwalls {\n        din\n        progress\n        phase\n      }\n    }\n    inverterSelfTests {\n      isRunning\n      isCanceled\n      pinvSelfTestsResults {\n        din\n        overall {\n          status\n          test\n          summary\n          setMagnitude\n          setTime\n          tripMagnitude\n          tripTime\n          accuracyMagnitude\n          accuracyTime\n          currentMagnitude\n          timestamp\n          lastError\n        }\n        testResults {\n          status\n          test\n          summary\n          setMagnitude\n          setTime\n          tripMagnitude\n          tripTime\n          accuracyMagnitude\n          accuracyTime\n          currentMagnitude\n          timestamp\n          lastError\n        }\n      }\n    }\n  }\n}\n"
        pb.message.payload.send.code = b'0\201\206\002A\024\261\227\245\177\255\265\272\321r\032\250\275j\305\030\2300\266\022B\242\264pO\262\024vd\267\316\032\f\376\322V\001\f\177*\366\345\333g_/`\v\026\225_qc\023$\323\216y\276~\335A1\022x\002Ap\a_\264\037]\304>\362\356\005\245V\301\177*\b\307\016\246]\037\202\242\353I~\332\317\021\336\006\033q\317\311\264\315\374\036\365s\272\225\215#o!\315z\353\345z\226\365\341\f\265\256r\373\313/\027\037'
        pb.message.payload.send.b.value = "{}"
        pb.tail.value = 1
        url = f'https://{self.gw_ip}/tedapi/v1'
        r = requests.post(url, auth=('Tesla_Energy_Device', self.gw_pwd), verify=False,
            headers={'Content-type': 'application/octet-string'},
            data=pb.SerializeToString())
        tedapi = tedapi_pb2.ParentMessage()
        tedapi.ParseFromString(r.content)
        payload = tedapi.message.payload.recv.text
        self.status = json.loads(payload)
        self.cache["status"] = {"value": self.status, "expires": time.perf_counter() + self.pwcacheexpire}
        return self.status
    
# If this is run as a standalone script
if __name__ == "__main__":
    print("Tesla Powerwall Gateway API Decoder")
    print("")
    print("Connect to your Powerwall Gateway WiFi.")

    # Get GW_PWD from User
    gw_pwd = input("Enter Powerwall Gateway Password: ")
    print("")

    # Fetch data from Powerwall
    gw = TeslaGateway(gw_pwd)
    print("Fetching DIN...")
    print(gw.get_din())
    print("")
    print("Fetching Configuration...")
    print(gw.get_config())
    print("")
    print("Fetching Status...")
    print(gw.get_status())
    print("")
    print("Done.")
    print("")

# End of tedapi.py
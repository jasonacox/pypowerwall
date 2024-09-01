# -*- coding: utf-8 -*-
"""
 Python script to poll /tedapi/vw API for DIN and ComponentsQuery from PW3

 Requires:
  - Protobuf pip install protobuf
  - Generate tedapi_pb2.py with protoc --python_out=. tedapi.proto
"""

import tedapi_pb2 
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import json
import sys

# Globals
GW_IP = "192.168.91.1"
components = None

# Print Header
print("Tesla Powerwall 3 Gateway API Decoder")

# Test IP Connection to Powerwall Gateway
print(" - Testing Connection to Powerwall Gateway...")
url = f'https://{GW_IP}'
try:
    r = requests.get(url, verify=False, timeout=5)
except requests.exceptions.RequestException as e:
    print("ERROR: Powerwall not Found")
    print(" Use: sudo route add -host 192.168.91.1 <Powerwall_IP>")
    exit(1)

# If user specified gw_pwd on command line
if len(sys.argv) > 1:
    gw_pwd = sys.argv[1]
    print(f" - Using Powerwall Gateway Password: {gw_pwd}")
else:
    # Get GW_PWD from User
    gw_pwd = input("\nEnter Powerwall Gateway Password: ")

# Fetch DIN from Powerwall
print(" - Fetching DIN from Powerwall...")
url = f'https://{GW_IP}/tedapi/din'
r = requests.get(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False, timeout=5)
#print(f"Response: {r.status_code}")
din = r.text
print(f" - Connected: Powerwall Gateway DIN: {din}")

# Fetch Configuration from Powerwall
print(" - Fetching Configuration from Powerwall...")
# Build Protobuf to fetch config
pb = tedapi_pb2.Message()
pb.message.deliveryChannel = 1
pb.message.sender.local = 1
pb.message.recipient.din = din  # DIN of Powerwall
pb.message.config.send.num = 1
pb.message.config.send.file = "config.json"
pb.tail.value = 1
url = f'https://{GW_IP}/tedapi/v1'
r = requests.post(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False,
    headers={'Content-type': 'application/octet-string'},
    data=pb.SerializeToString(), timeout=5)
#print(f"Response Code: {r.status_code}")
# Decode response
tedapi = tedapi_pb2.Message()
tedapi.ParseFromString(r.content)
payload = tedapi.message.config.recv.file.text
config = json.loads(payload)
#print(f"Data: {tedapi}")
# Write config to file
with open("config.json", "w") as f:
    f.write(json.dumps(config,indent=4))
print(" - Config Written to config.json")
# determine the battery blocks from payload
battery_blocks = config['battery_blocks']
print(" - Battery Blocks:")
for battery in battery_blocks:
    vin = battery['vin']
    battery_type = battery['type']
    print(f"   - Battery Block: {vin} ({battery_type})")

# Fetch Firmware from Powerwall
print(f" - Fetching /tedapi/v1 PW3 Firmware from Powerwall ({din})...")
# Build Protobuf to fetch firmware
pb = tedapi_pb2.Message()
pb.message.deliveryChannel = 1
pb.message.sender.local = 1
pb.message.recipient.din = din  # DIN of Powerwall
pb.message.firmware.request = ""
pb.tail.value = 1
url = f'https://{GW_IP}/tedapi/v1'
r = requests.post(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False,
    headers={'Content-type': 'application/octet-string'},
    data=pb.SerializeToString(), timeout=5)
print(f"Response Code: {r.status_code}")
# write raw response to file
with open("firmware.raw", "wb") as f:
    f.write(r.content)
print(" - Firmware Written to firmware.raw")
# Decode response
tedapi = tedapi_pb2.Message()
tedapi.ParseFromString(r.content)
firmware_version = tedapi.message.firmware.system.version.text
print(f"Firmware version (len={len(firmware_version)}): {firmware_version}")

# Fetch ComponentsQuery from Powerwall
print(f" - Fetching /tedapi/v1 PW3 ComponentsQuery from Powerwall ({din})...")
# Build Protobuf to fetch config
pb = tedapi_pb2.Message()
pb.message.deliveryChannel = 1
pb.message.sender.local = 1
pb.message.recipient.din = din  # DIN of Powerwall
pb.message.payload.send.num = 2
pb.message.payload.send.payload.value = 1
pb.message.payload.send.payload.text = " query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n"
pb.message.payload.send.code = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
pb.message.payload.send.b.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
pb.tail.value = 1
url = f'https://{GW_IP}/tedapi/v1'
r = requests.post(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False,
    headers={'Content-type': 'application/octet-string'},
    data=pb.SerializeToString(), timeout=5)
print(f"Response Code: {r.status_code}")
# Decode response
tedapi = tedapi_pb2.Message()
tedapi.ParseFromString(r.content)
payload = tedapi.message.payload.recv.text
print(f"Payload (len={len(payload)}): {payload}")
if payload:
    components = json.loads(payload)
    # Write components to file
    with open("components.json", "w") as f:
        f.write(json.dumps(components,indent=4))
    print(" - Components Written to components.json")
else:
    print(" - No Components Found")

def get_pw3_vitals(components=None, config=None, din=None, gw_pwd=None):
    """
    Get Powerwall 3 Battery Vitals Data

    Returns:
    {
        "PVAC--{part}--{sn}" {
            "PVAC_PvState_A": "PV_Active",
            "PVAC_PVCurrent_A": 0.0,
            "PVAC_PVMeasuredVoltage_A": 0.0,
            "PVAC_PVMeasuredPower_A": 0.0,
        }.
        "PVS--{part}--{sn}" {
            "PVS_StringA_Connected": true,
        },
        "TEPOD--{part}--{sn}" {
            "alerts": [],
            "POD_nom_energy_remaining": 0.0,
            "POD_nom_full_pack_energy": 0.0,
            "POD_nom_energy_to_be_charged": 0.0,
        }
    }   
    """

    #components = self.get_components(force)
    #din = self.din
    if not components:
        print("Unable to get Powerwall 3 Components")
        return None
    response = {}

    # Get config
    #config = self.get_config(force)
    battery_blocks = config['battery_blocks']

    # Loop through all the battery blocks (Powerwalls)
    for battery in battery_blocks:
        pw_din = battery['vin'] # 1707000-11-J--TG12xxxxxx3A8Z
        pw_part, pw_serial = pw_din.split('--')
        battery_type = battery['type']
        if "Powerwall3" not in battery_type:
            print(f"Skipping {pw_din} - Not a Powerwall 3")
            continue
        # Fetch Device ComponentsQuery from Powerwall
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
        r = requests.post(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False,
                        headers={'Content-type': 'application/octet-string'},
                        data=pb.SerializeToString(), timeout=10)
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
                    for alert in components[component][0]['activeAlerts']:
                        if alert['name'] not in alerts:
                            alerts.append(alert['name'])
                bms_component = data['components']['bms'][0] # TODO: Only first BMS component
                signals = bms_component['signals']
                nom_energy_remaining = 0
                nom_full_pack_energy = 0
                for signal in signals:
                    if "BMS_nominalEnergyRemaining" == signal['name']:
                        nom_energy_remaining = signal['value']
                    elif "BMS_nominalFullPackEnergy" == signal['name']:
                        nom_full_pack_energy = signal['value']
                response[f"TEPOD--{pw_din}"] = {
                    "alerts": alerts,
                    "POD_nom_energy_remaining": nom_energy_remaining,
                    "POD_nom_energy_to_be_charged": nom_full_pack_energy - nom_energy_remaining,
                    "POD_nom_full_pack_energy": nom_full_pack_energy,
                }
                # PVAC and PVS
                response[f"PVAC--{pw_din}"] = {}
                response[f"PVS--{pw_din}"] = {}
                """
                PCH_PvState_A through F - textValue in [Pv_Active, Pv_Active_Parallel, Pv_Standby]
                PCH_PvVoltageA through F - value
                PCH_PvCurrentA through F - value
                """
                pch_components = data['components']['pch']
                # Loop through and find all the strings
                for n in ["A", "B", "C", "D", "E", "F"]:
                    pv_state = "Unknown"
                    pv_voltage = 0
                    pv_current = 0
                    for component in pch_components:
                        signals = component['signals']
                        for signal in signals:
                            if f'PCH_PvState_{n}' == signal['name']:
                                pv_state = signal['textValue']
                            elif f'PCH_PvVoltage{n}' == signal['name']:
                                pv_voltage = signal['value'] if signal['value'] > 0 else 0
                            elif f'PCH_PvCurrent{n}' == signal['name']:
                                pv_current = signal['value'] if signal['value'] > 0 else 0
                            elif f'PCH_AcFrequency' == signal['name']:
                                response[f"PVAC--{pw_din}"][f"PVAC_Fout"] = signal['value']
                            elif f'PCH_AcVoltageAN' == signal['name']:
                                response[f"PVAC--{pw_din}"][f"PVAC_VL1Ground"] = signal['value']
                            elif f'PCH_AcVoltageBN' == signal['name']:
                                response[f"PVAC--{pw_din}"][f"PVAC_VL2Ground"] = signal['value']
                            elif f'PCH_AcVoltageAB' == signal['name']:
                                response[f"PVAC--{pw_din}"][f"PVAC_Vout"] = signal['value']
                            elif f'PCH_AcRealPowerAB' == signal['name']:
                                response[f"PVAC--{pw_din}"][f"PVAC_Pout"] = signal['value']
                            elif f'PCH_AcMode' == signal['name']:
                                response[f"PVAC--{pw_din}"][f"PVAC_State"] = signal['textValue']
                    pv_power = pv_voltage * pv_current # Calculate power
                    response[f"PVAC--{pw_din}"][f"PVAC_PvState_{n}"] = pv_state
                    response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredVoltage_{n}"] = pv_voltage
                    response[f"PVAC--{pw_din}"][f"PVAC_PVCurrent_{n}"] = pv_current
                    response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredPower_{n}"] = pv_power
                    response[f"PVAC--{pw_din}"]["manufacturer"] = "TESLA"
                    response[f"PVAC--{pw_din}"]["partNumber"] = pw_part
                    response[f"PVAC--{pw_din}"]["serialNumber"] = pw_serial
                    response[f"PVS--{pw_din}"][f"PVS_String{n}_Connected"] = True if "Pv_Active" in pv_state else False
            else:
                print(f"No payload for {pw_din}")
        else:
            print(f"Error fetching components: {r.status_code}")
    return response

vitals = get_pw3_vitals(components, config, din, gw_pwd)
print(json.dumps(vitals, indent=4))

# End of Script
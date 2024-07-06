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

# Print Header
print("Tesla Powerwall Gateway API Decoder")

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
data = json.loads(payload)
#print(f"Data: {tedapi}")
# Write config to file
with open("config.json", "w") as f:
    f.write(json.dumps(data,indent=4))
print(" - Config Written to config.json")
# determine the battery blocks from payload
battery_blocks = data['battery_blocks']
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
    data = json.loads(payload)
    # Write components to file
    with open("components.json", "w") as f:
        f.write(json.dumps(data,indent=4))
    print(" - Components Written to components.json")
else:
    print(" - No Components Found")

# Need to loop through all the battery blocks (Powerwalls)
for battery in battery_blocks:
    pw_din = battery['vin']
    battery_type = battery['type']
    fname = f"pw_{pw_din}.json"
    # Fetch Device ComponentsQuery from Powerwall
    print(f" - Fetching /tedapi/device/<din>/v1 PW3 ComponentsQuery from Powerwall ({pw_din} {battery_type})...")
    # Build Protobuf to fetch config
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
        data=pb.SerializeToString(), timeout=5)
    print(f"Response Code: {r.status_code}")
    if r.status_code == 200:
        # Decode response
        tedapi = tedapi_pb2.Message()
        tedapi.ParseFromString(r.content)
        payload = tedapi.message.payload.recv.text
        print(f"Payload (len={len(payload)}): {payload}")
        if payload:
            data = json.loads(payload)
            # Write components to file
            with open(fname, "w") as f:
                f.write(json.dumps(data,indent=4))
            print(f" - Components Written to {fname}")
        else:
            print(" - No Components Found")
    else:
        print(" - No Components Found")

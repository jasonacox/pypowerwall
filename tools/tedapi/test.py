# -*- coding: utf-8 -*-
"""
 Python script to poll /tedapi API for DIN, Config and Status

 Requires:
  - Protobuf pip install protobuf
  - Generate tedapi_pb2.py with protoc --python_out=. tedapi.proto

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
"""

import tedapi_pb2 
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Globals
GW_IP = "192.168.91.1"

# Print Header
print("Tesla Powerwall Gateway API Decoder")
print("")
print("Connect to your Powerwall Gateway WiFi.")

# Get GW_PWD from User
gw_pwd = input("Enter Powerwall Gateway Password: ")

# Fetch DIN from Powerwall
print("Fetching DIN from Powerwall...")
url = f'https://{GW_IP}/tedapi/din'
r = requests.get(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False)
print(f"Response: {r.status_code}")
din = r.text
print(f"Powerwall Gateway DIN: {din}")
print("\n\n")

# Fetch Configuration from Powerwall
print("Fetching Configuration from Powerwall...")
# Build Protobuf to fetch config
pb = tedapi_pb2.ParentMessage()
pb.message.deliveryChannel = 1
pb.message.sender.local = 1
pb.message.recipient.din = din  # DIN of Powerwall
pb.message.config.send.num = 1
pb.message.config.send.file = "config.json"
pb.tail.value = 1
url = f'https://{GW_IP}/tedapi/v1'
r = requests.post(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False,
    headers={'Content-type': 'application/octet-string'},
    data=pb.SerializeToString())
print(f"Response Code: {r.status_code}")
# Decode response
tedapi = tedapi_pb2.ParentMessage()
tedapi.ParseFromString(r.content)
print(f"Data: {tedapi}")
print("\n\n")

# Fetch Current Status from Powerwall
print("Fetching Current Status from Powerwall...")
# Build Protobuf to fetch status
pb = tedapi_pb2.ParentMessage()
pb.message.deliveryChannel = 1
pb.message.sender.local = 1
pb.message.recipient.din = din  # DIN of Powerwall
pb.message.payload.send.num = 2
pb.message.payload.send.payload.value = 1
pb.message.payload.send.payload.text = " query DeviceControllerQuery " # TODO
pb.message.payload.send.code = b'0\201\210' # TODO
pb.message.payload.send.b.value = "{}"
pb.tail.value = 1
url = f'https://{GW_IP}/tedapi/v1'
r = requests.post(url, auth=('Tesla_Energy_Device', gw_pwd), verify=False,
    headers={'Content-type': 'application/octet-string'},
    data=pb.SerializeToString())
print(f"Response Code: {r.status_code}")
# Decode response
tedapi = tedapi_pb2.ParentMessage()
tedapi.ParseFromString(r.content)
print(f"Data: {tedapi}")
print("\n\n")

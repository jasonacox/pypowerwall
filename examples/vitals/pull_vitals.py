# pyPowerWall Vitals
# -*- coding: utf-8 -*-
"""
 This script pulls the Powerwall Vitals API

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
 
 * Work in Progress 
 * API Endpoing on Powerwall: /api/devices/vitals 
 * Result is a protobuf binary payload

Requires protobuf: 
    pip install protobuf
    tesla_pb2.py # tesla protobuf definition file built using:
        protoc --python_out=. tesla.proto 

Credits:
    Protobuf definition (tesla.proto) thanks to @brianhealey

Date: 27 Nov 2021
"""

import pypowerwall
import tesla_pb2
import json

# Update with your details
password='password'
email='email@example.com'
host = "10.0.1.23"
timezone = "America/LosAngeles"

# Make sure binary polling allowed
if pypowerwall.version_tuple < (0,0,3):
    print("\n*** WARNING: Minimum pypowerwall version 0.0.3 required for proper function! ***\n\n")

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Pull vitals payload - binary format in protobuf
stream = pw.poll('/api/devices/vitals')
streamsize = len(stream)
print("Size of stream = %d" % streamsize)

# Protobuf payload processing
pw = tesla_pb2.DevicesWithVitals()
pw.ParseFromString(stream)
num = len(pw.devices)
print("There are %d devices found." % num)

# List Devices
x = 0
output = {}
while(x < num):
    parent = str(pw.devices[x].device[0].device.componentParentDin.value)
    name = str(pw.devices[x].device[0].device.din.value)
    print("Device %d: %s " % (x, pw.devices[x].device[0].device.din.value))
    print("   - %s" % pw.devices[x].device[0].device.componentParentDin.value)
    print("     - %s" % pw.devices[x].device[0].device.din.value)
    for y in pw.devices[x].vitals:
        vital_name = str(y.name)
        if(y.HasField('boolValue')):
            print("       - %s = %r" % (y.name,y.boolValue))
            vital_value = y.boolValue
        if(y.HasField('stringValue')):
            print("       - %s = '%s'" % (y.name,y.stringValue))
            vital_value = y.stringValue
        if(y.HasField('floatValue')):
            print("       - %s = '%f'" % (y.name,y.floatValue))
            vital_value = y.floatValue
        # Record in output dictionary
        if name not in output.keys():
            output[name] = {}
            output[name]['Parent'] = parent
        output[name][vital_name] = vital_value
    x += 1

json_out = json.dumps(output, indent=4, sort_keys=True)
print("Resulting vitals:\n", json_out)

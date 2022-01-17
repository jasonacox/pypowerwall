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
    device = pw.devices[x].device.device
    parent = str(device.componentParentDin.value)
    vitals = pw.devices[x].vitals
    alerts = pw.devices[x].alerts

    name = str(device.din.value)
    print("Device %d: %s " % (x, name))

    # e.STSTSM = "STSTSM",
    # e.POD = "TEPOD",
    # e.PINV = "TEPINV",
    # e.PVAC = "PVAC",
    # e.PVS = "PVS",
    # e.SYNC = "TESYNC",
    # e.MSA = "TEMSA",
    # e.NEURIO = "NEURIO",
    # e.ACPW = "ACPW",
    # e.PVI = "PVI",
    # e.SPW = "SPW"

    if name.startswith("TETHC--"):
        print("   - Inverter")

    if device.HasField("partNumber"):
        print("   - Part Number: %s" % device.partNumber.value)
    if device.HasField("serialNumber"):
        print("   - Serial Number: %s" % device.serialNumber.value)
    if device.HasField("manufacturer"):
        print("   - Manufacturer: %s" % device.manufacturer.value)
    if device.HasField("siteLabel"):
        print("   - Site Label: %s" % device.siteLabel.value)
    if device.HasField("componentParentDin"):
        print("   - Parent DIN: %s" % device.componentParentDin.value)
    if device.HasField("firmwareVersion"):
        print("   - Firmware Version: %s" % device.firmwareVersion.value)
    if device.HasField("firstCommunicationTime"):
        print("   - First Communicated At: %s" % device.firstCommunicationTime.ToDatetime())
    if device.HasField("lastCommunicationTime"):
        print("   - Last Communicated At: %s" % device.lastCommunicationTime.ToDatetime())
    # if device.HasField("connectionParameters"):
    #    print("   - Connection Parameters: %s" % device.connectionParameters)

    if device.HasField("deviceAttributes"):
        attributes = device.deviceAttributes
        if attributes.HasField("teslaEnergyEcuAttributes"):
            print("   - Ecu:")
            print("       - type: %i" % attributes.teslaEnergyEcuAttributes.ecuType)
        if attributes.HasField("generatorAttributes"):
            print("   - Generator:")
            print("       - nameplateRealPowerW: %i" % attributes.generatorAttributes.nameplateRealPowerW)
            print("       - nameplateApparentPowerVa: %i" % attributes.generatorAttributes.nameplateApparentPowerVa)
        if attributes.HasField("pvInverterAttributes"):
            print("   - Inverter:")
            print("       - nameplateRealPowerW: %i" % attributes.pvInverterAttributes.nameplateRealPowerW)
        if attributes.HasField("meterAttributes"):
            print("   - Meter:")
            for location in attributes.meterAttributes.meterLocation:
                print("       - location: %i" % location)
    a = 0

    while (a < len(alerts)):
        if (a == 0):
            print("   - Alerts:")

        print("       - ALERT_%i = %s" % (a, alerts[a]) )
        a += 1

    print("   - Vitals:")

    for y in pw.devices[x].vitals:
        vital_name = str(y.name)
        if (y.HasField('intValue')):
            print("       - %s = %i" % (y.name, y.intValue))
            vital_value = y.intValue
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

    if name in output.keys() and len(alerts) > 0:
        output[name]["ALERT_Count"] = len(pw.devices[x].alerts)

    x += 1

json_out = json.dumps(output, indent=4, sort_keys=True)
print("Resulting vitals:\n", json_out)

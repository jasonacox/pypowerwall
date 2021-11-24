# pyPowerWall Vitals
# -*- coding: utf-8 -*-
"""
 This script pulls the Powerwall Vitals API

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
 
 * Work in Progress - /api/devices/vitals is a protobuf binary payload

    Protobuf Data Format:
    binary(tag1,length1,value1,tag2,length2,value2,..,tagN,lengthN,valueN)

"""
import pypowerwall
import struct

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

# Walk through payload
index = 0
skip = False
skipdata = ""
while(index < streamsize):
    key = ""
    value = ""
    meta = ""
    # check for kv signal
    if(streamsize-index > 3 and stream[index] == ord('\x12') and stream[index+2] == ord('\x0a')):
        # print skip data
        if skip:
            print(" > Skipped: %s" % skipdata)
            skip = False
            skipdata = ""
        # Parse payload
        meta=stream[index+1]
        index += 3
        # grab key starting with size value 
        size = stream[index]
        index += 1
        if(size > 0):
            key = stream[index:index+size].decode()
            index += size
        delimiter = stream[index]
        index += 1
        if(delimiter == ord('!')):
            # numerical value
            # DOUBLE
            v = stream[index:index+8]
            v = struct.unpack('<d',v)[0]
            try:
                value = "%r" % (v)
            except:
                value = "?"    
            index += 8
        if(delimiter == ord('*')):
            # string value
            size = stream[index]
            index += 1
            if(size > 0):
                value = stream[index:index+size].decode()
                index += size          
        if(delimiter == ord('0')):
            # boolean value
            if(stream[index] == 1):
                value = "TRUE"
            else:
                value = "FALSE"
            index += 1
        # Print it
        print("[%d] %s: %s" % (meta,key,value))
        continue

    skip = True
    if(chr(stream[index]).isalnum()):
        skipdata += " %c" % chr(stream[index])
    else:
        skipdata += " 0x%02d" % stream[index]
    index += 1

# end while


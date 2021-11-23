# pyPowerWall Vitals
# -*- coding: utf-8 -*-
"""
 This script pulls the Powerwall Vitals API

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
 
 * Work in Progress - this appears to be a protobuf binary payload

"""
import pypowerwall
import struct

password='password'
email='email@example.com'
host = "10.0.1.23"
timezone = "America/LosAngeles"

pw = pypowerwall.Powerwall(host,password,email,timezone)

# pull vitals binary payload
vitals = pw.poll('/api/devices/vitals')

# Convert to binary
stream = vitals.encode()
streamsize = len(stream)
print("Size of stream = %d" % streamsize)

# Walk through payload stream
index = 0

while(index < streamsize):
    key = ""
    value = ""
    # check for kv signal
    if(streamsize-index > 3 and stream[index] == ord('\x12') and stream[index+2] == ord('\x0a')):
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
            value = stream[index:index+8]
            value = struct.unpack('<d',value)[0]
            # print("     DEBUG: %r %r" % (value, type(value)))
            try:
                value = "%r" % (value)
            except:
                value = "Unknown"
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
        print("%s: %s" % (key,value))
        continue

    # print(" > Skip: %d" % (stream[index]))
    index += 1

# end while


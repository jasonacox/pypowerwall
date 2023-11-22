# -*- coding: utf-8 -*-
"""
 Python module to decode tedapi protobuf data

 Requires:
  - Protobuf pip install protobuf
  - Generate tedapi_pb2.py with protoc --python_out=. tedapi.proto

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
"""

import tedapi_pb2 
import sys

FILENAME = 'request.bin'

# Set filename from command line if specified
filename = FILENAME
if len(sys.argv) > 1:
    filename = sys.argv[1]

# Open request or response file and read data
with open(filename, 'rb') as f:
    data = f.read()

# Decode protobuf data
tedapi = tedapi_pb2.ParentMessage()
tedapi.ParseFromString(data)
print(tedapi)





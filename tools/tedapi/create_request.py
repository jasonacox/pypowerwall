#!/usr/bin/env python3
"""
create_request.py - Generate a TEDAPI protobuf request binary

This script interactively builds a TEDAPI Message protobuf for 
configuration delivery.

Features:
- Prompts for the recipient DIN (Device Identification Number)
- Uses 'config.json' as the configuration file (can be edited in the script)
- Prompts for the output binary file name (defaults to 'request.bin' if left blank)
- Fills required fields for deliveryChannel, sender, recipient, config, and tail
- Serializes the message to the specified binary file for use with TEDAPI tools

Usage:
    python3 create_request.py
    # Follow prompts for DIN and output file name

Example:
   curl -v -k -H 'Content-type: application/octet-string' -u "Tesla_Energy_Device:GW_PWD" --data-binary @request.bin https://192.168.91.1/tedapi/v1

"""

import tedapi_pb2

# Prompt for DIN and config file name
din = input("Enter DIN: ").strip()
config_file = 'config.json'
delivery_channel = 1
sender_local = 1
config_num = 1

# Build the message according to your proto
msg = tedapi_pb2.Message()

# Fill out the envelope (this mimics your example structure)
msg.message.deliveryChannel = delivery_channel

# Set sender as 'local'
msg.message.sender.local = sender_local

# Set recipient DIN
msg.message.recipient.din = din

# Set config section (as 'send' variant)
msg.message.config.send.num = config_num
msg.message.config.send.file = config_file

# Add a tail (set value to 1 as in your example)
msg.tail.value = 1

# Prompt for output file name
output_file = input("Enter output binary file name [request.bin]: ").strip() or "request.bin"

# Serialize and write to file
with open(output_file, "wb") as f:
    f.write(msg.SerializeToString())

print(f"New {output_file} created with DIN:", din)
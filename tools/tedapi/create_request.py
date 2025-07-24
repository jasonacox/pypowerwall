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
import json
import os
import logging
from . import tedapi_pb2

# Setup Logging
log = logging.getLogger(__name__)

class TEDAPIMessage:
    def __init__(self, din):
        self.din = din

class ConfigMessage(TEDAPIMessage):
    def __init__(self, din):
        self.din = din

    def getMessage(self):
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.config.send.num = 1
        pb.message.config.send.file = "config.json"
        pb.tail.value = 1
        self.pb = pb
        return self.pb
    
    def SerializeToString(self):
        return self.getMessage().SerializeToString()
    
    def ParseFromString(self, data):
        self.pb.ParseFromString(data)
        payload = self.pb.message.config.recv.file.text
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data

class GatewayStatusMessage(TEDAPIMessage):
    def __init__(self, din):
        self.din = din

    def getMessage(self): 
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        with open(os.path.join(os.path.dirname(__file__), "graphql/status_query.graphql"), "r") as file:
            pb.message.payload.send.payload.text = file.read()
        with open(os.path.join(os.path.dirname(__file__), "graphql/status_query.sig"), "rb") as sig_file:
            pb.message.payload.send.code = sig_file.read()
        
        pb.message.payload.send.b.value = "{}"
        pb.tail.value = 1
        self.pb = pb
        return self.pb
    
    def SerializeToString(self):
        return self.getMessage().SerializeToString()
    
    def ParseFromString(self, data):
        self.getMessage().ParseFromString(data)
        payload = self.pb.message.payload.recv.text

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data